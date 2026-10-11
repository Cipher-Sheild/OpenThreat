"""Novelty classification — implements the agreed labelling policy (v1.1).

Member 2 sends the new facts plus candidate existing facts from Postgres. For each new fact:

  UNCERTAIN    fact confidence too low, or the subject/object match is not confident enough   (rule 5)
  KNOWN        same resolved subject + relation + object as an existing fact                  (rule 2)
  NEW          nothing on record for this subject + relation, or a multi-valued relation      (rule 1)
               (USES/DEPLOYS/EXPLOITS/TARGETS) gains another object. Old facts stay ACTIVE.
  UPDATED      the new fact SUPERSEDES an old one -> old fact becomes HISTORICAL                (rule 3)
                 - single-valued relation (ATTRIBUTED_TO) with a different object, and the new
                   source is newer than the old fact or explicitly revises it ("now attributed to")
                 - "no longer uses X" (temporal negation) about an ACTIVE "uses X"
  CONFLICTING  the new fact contradicts an old one and does not clearly supersede it            (rule 4)
                 - single-valued relation, different object, not newer / no revision wording
                 - denial ("is not attributed to", "falsely linked") of an ACTIVE fact
               Both facts stay ACTIVE and are flagged for analyst review.

Nothing is ever deleted; Member 2 applies the status changes in Postgres.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from config import NOVELTY_MIN_FACT_CONFIDENCE, RESOLVE_CONFIDENT, SINGLE_VALUED_RELATIONS
from pipeline.resolution import name_match_score

TEMPORAL_NEGATION = re.compile(
    r"\b(?:no longer|stopped|ceased|abandoned|retired|discontinued|phased out|moved away from|"
    r"replaced|switched (?:from|away)|has not been seen|not (?:been )?(?:seen|observed) since)\b",
    re.I,
)
REVISION = re.compile(
    r"\b(?:now (?:attribut\w*|believed|assess\w*|linked|tracked)|re-?attribut\w*|previously (?:attributed|believed|thought|linked)|"
    r"originally (?:attributed|believed|thought)|has since been|updated (?:assessment|attribution)|"
    r"new evidence|actually|in fact|instead|rather than)\b",
    re.I,
)


@dataclass
class Fact:
    subject: str
    relation: str
    object: str
    confidence: float
    negated: bool = False
    subject_type: str | None = None
    object_type: str | None = None
    evidence: dict | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class Candidate:
    fact_id: str
    subject: str
    relation: str
    object: str
    status: str
    negated: bool = False
    subject_aliases: list[str] = field(default_factory=list)
    object_aliases: list[str] = field(default_factory=list)
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    source_name: str | None = None


@dataclass
class NoveltyResult:
    fact: dict
    status: str
    confidence: float
    matched_fact_id: str | None = None
    superseded_fact_ids: list[str] = field(default_factory=list)
    conflicting_fact_ids: list[str] = field(default_factory=list)
    reason: str = ""


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _latest(c: Candidate) -> datetime | None:
    dates = [d for d in (_parse_dt(c.last_seen_at), _parse_dt(c.first_seen_at)) if d]
    return max(dates) if dates else None


def _evidence_text(f: Fact) -> str:
    return (f.evidence or {}).get("text", "") if isinstance(f.evidence, dict) else ""


def classify_one(f: Fact, candidates: list[Candidate], published_at: str | None) -> NoveltyResult:
    fact_dict = f.raw or {"subject": f.subject, "relation": f.relation, "object": f.object}
    relation = f.relation.upper()

    if f.confidence < NOVELTY_MIN_FACT_CONFIDENCE:
        return NoveltyResult(fact_dict, "UNCERTAIN", round(1 - f.confidence, 3),
                             reason=f"Extraction confidence {f.confidence:.2f} is below {NOVELTY_MIN_FACT_CONFIDENCE:.2f}.")

    # candidates with the same subject (after resolution) and the same relation
    same_sr: list[tuple[Candidate, float]] = []
    for c in candidates:
        if c.relation.upper() != relation:
            continue
        s = name_match_score(f.subject, c.subject, c.subject_aliases, f.subject_type)
        if s > 0:
            same_sr.append((c, s))

    if not same_sr:
        return NoveltyResult(fact_dict, "NEW", round(f.confidence, 3),
                             reason=f"No existing {relation} fact for '{f.subject}'.")

    # split into same-object vs different-object
    same_obj: list[tuple[Candidate, float]] = []
    diff_obj: list[tuple[Candidate, float]] = []
    for c, s_score in same_sr:
        o = name_match_score(f.object, c.object, c.object_aliases, f.object_type)
        if o > 0:
            same_obj.append((c, min(s_score, o)))
        else:
            diff_obj.append((c, s_score))

    weakest = min(score for _, score in same_obj or same_sr)
    if weakest < RESOLVE_CONFIDENT:
        ids = [c.fact_id for c, _ in (same_obj or same_sr)]
        return NoveltyResult(fact_dict, "UNCERTAIN", round(weakest, 3),
                             reason=f"Entity resolution against facts {ids} is not confident enough ({weakest:.2f}).")

    new_dt, text = _parse_dt(published_at), _evidence_text(f)

    if same_obj:
        same_polarity = [(c, s) for c, s in same_obj if c.negated == f.negated]
        opposite = [(c, s) for c, s in same_obj if c.negated != f.negated and c.status == "ACTIVE"]

        active_same = [(c, s) for c, s in same_polarity if c.status == "ACTIVE"]
        if active_same and not opposite:
            c, s = max(active_same, key=lambda x: x[1])
            return NoveltyResult(fact_dict, "KNOWN", round(f.confidence * s, 3), matched_fact_id=c.fact_id,
                                 reason=f"Same fact already on record ({c.fact_id}).")
        if opposite:
            ids = [c.fact_id for c, _ in opposite]
            newer = all(new_dt and _latest(c) and new_dt > _latest(c) for c, _ in opposite)
            if f.negated and (TEMPORAL_NEGATION.search(text) or newer):
                return NoveltyResult(fact_dict, "UPDATED", round(f.confidence, 3), superseded_fact_ids=ids,
                                     reason="The new source says this no longer holds; the old fact becomes HISTORICAL.")
            if not f.negated and newer:
                return NoveltyResult(fact_dict, "UPDATED", round(f.confidence, 3), superseded_fact_ids=ids,
                                     reason="A newer source re-affirms a fact that was recorded as negated.")
            return NoveltyResult(fact_dict, "CONFLICTING", round(f.confidence, 3), conflicting_fact_ids=ids,
                                 reason="The new fact contradicts an ACTIVE fact without clearly superseding it.")
        # only HISTORICAL matches with the same polarity: the fact is seen again
        if not same_polarity:
            return NoveltyResult(fact_dict, "NEW", round(f.confidence, 3),
                                 reason="Only an opposite-polarity HISTORICAL fact exists; no active contradiction.")
        c, s = max(same_polarity, key=lambda x: x[1])
        return NoveltyResult(fact_dict, "KNOWN", round(f.confidence * s, 3), matched_fact_id=c.fact_id,
                             reason=f"Matches HISTORICAL fact {c.fact_id}; it is being reported again.")

    # different object
    if relation not in SINGLE_VALUED_RELATIONS or f.negated:
        return NoveltyResult(fact_dict, "NEW", round(f.confidence, 3),
                             reason=f"'{f.subject}' {relation} a new object; existing facts stay ACTIVE.")

    rivals = [c for c, _ in diff_obj if c.status == "ACTIVE" and not c.negated]
    if not rivals:
        return NoveltyResult(fact_dict, "NEW", round(f.confidence, 3),
                             reason=f"No ACTIVE {relation} fact for '{f.subject}'.")
    ids = [c.fact_id for c in rivals]
    newer = all(new_dt and _latest(c) and new_dt > _latest(c) for c in rivals)
    if newer or REVISION.search(text):
        why = "newer source" if newer else "the text explicitly revises the earlier assessment"
        return NoveltyResult(fact_dict, "UPDATED", round(f.confidence, 3), superseded_fact_ids=ids,
                             reason=f"{relation} is single-valued and {why}; old fact(s) become HISTORICAL.")
    return NoveltyResult(fact_dict, "CONFLICTING", round(f.confidence, 3), conflicting_fact_ids=ids,
                         reason=f"{relation} is single-valued and sources disagree with no clear order; both stay ACTIVE.")


def classify(facts: list[Fact], candidates: list[Candidate], published_at: str | None) -> list[NoveltyResult]:
    return [classify_one(f, candidates, published_at) for f in facts]
