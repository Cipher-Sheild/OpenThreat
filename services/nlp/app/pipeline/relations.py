"""Phase 2 rule-based relation extraction.

For every ordered pair of entities in a sentence, look at the words between them for a trigger
verb ("used", "deployed", "exploited", "targeted", "attributed to", passive "used by", ...),
check the entity types fit the relation, detect negation, and emit a fact with its evidence.

Phase 3 replaces `extract_relations` with a trained model; the output type stays the same.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from config import REL_MAX_GAP_CHARS
from pipeline.ner import Entity
from pipeline.preprocess import PreparedDocument, Sentence

ACTORS = {"THREAT_ACTOR"}
CODE = {"MALWARE", "TOOL"}

# relation -> (allowed subject types, allowed object types)
TYPE_RULES: dict[str, tuple[set[str], set[str]]] = {
    "USES": (ACTORS | CODE, CODE | {"TECHNIQUE", "OBSERVABLE"}),
    "DEPLOYS": (ACTORS | CODE, CODE),
    "EXPLOITS": (ACTORS | CODE, {"VULNERABILITY"}),
    "TARGETS": (ACTORS | CODE, {"ORGANIZATION"}),
    "ATTRIBUTED_TO": (ACTORS | CODE, ACTORS),
}

# (relation, trigger regex, base confidence). Active voice: left entity = subject.
ACTIVE_TRIGGERS: list[tuple[str, re.Pattern, float]] = [
    ("ATTRIBUTED_TO", re.compile(r"\b(?:(?:has been|have been|was|were|is|are|being)\s+)?(?:attributed|attribute[sd]?)\s+to\b", re.I), 0.8),
    ("ATTRIBUTED_TO", re.compile(r"\b(?:linked|tied|connected|traced)\s+(?:back\s+)?to\b", re.I), 0.65),
    ("ATTRIBUTED_TO", re.compile(r"\b(?:belong(?:s|ed|ing)? to|part of the (?:arsenal|toolset|toolkit) of|exclusive to)\b", re.I), 0.65),
    ("ATTRIBUTED_TO", re.compile(r"\b(?:associated|affiliated)\s+with\b", re.I), 0.55),
    ("EXPLOITS", re.compile(r"\b(?:exploit\w*|weaponi[sz]\w*|(?:took|taking|takes) advantage of)\b", re.I), 0.8),
    ("DEPLOYS", re.compile(r"\b(?:deploy\w*|drop(?:s|ped|ping)?|install\w*|deliver\w*|distribut\w*|load(?:s|ed|ing)?|launch\w*|push(?:es|ed|ing)?|download(?:s|ed|ing)?|execut\w*|ran|runs?)\b", re.I), 0.7),
    ("USES", re.compile(r"\b(?:use[sd]?|using|utili[sz]\w*|leverag\w*|employ\w*|rel(?:y|ies|ied|ying)\s+(?:up)?on|abus\w*|wield\w*|(?:equipped|armed)\s+with|adopted|turned to|switched to|moved to)\b", re.I), 0.75),
    ("TARGETS", re.compile(r"\b(?:target\w*|attack\w*|compromis\w*|breach\w*|infiltrat\w*|hit|struck|went after|go(?:es)? after|focus\w*\s+on|aimed at|victimi[sz]\w*|infect\w*|against)\b", re.I), 0.7),
]

# Passive "<object> was <verb> by <subject>" -> subject is the RIGHT entity
PASSIVE_TRIGGERS: list[tuple[str, re.Pattern, float, bool]] = [
    # (relation, regex, conf, swap) ; swap=False means left entity stays subject (e.g. "malware developed by actor")
    ("USES", re.compile(r"\b(?:used|utili[sz]ed|leveraged|employed|wielded|abused)\s+(?:\w+\s+){0,2}by\b", re.I), 0.75, True),
    ("DEPLOYS", re.compile(r"\b(?:deployed|dropped|installed|delivered|distributed|loaded|launched|pushed|downloaded|executed)\s+(?:\w+\s+){0,2}by\b", re.I), 0.7, True),
    ("EXPLOITS", re.compile(r"\b(?:exploited|weaponi[sz]ed)\s+(?:\w+\s+){0,2}by\b", re.I), 0.8, True),
    ("TARGETS", re.compile(r"\b(?:targeted|attacked|compromised|breached|infiltrated|hit|infected)\s+(?:\w+\s+){0,2}by\b", re.I), 0.7, True),
    ("ATTRIBUTED_TO", re.compile(r"\b(?:developed|operated|created|authored|written|maintained|run|controlled|built|owned)\s+(?:\w+\s+){0,2}by\b", re.I), 0.7, False),
]

# "<actor> is behind <malware>" -> ATTRIBUTED_TO(malware, actor)
REVERSE_ATTRIBUTION = re.compile(r"\b(?:is|are|was|were|being)\s+(?:(?:likely|probably|reportedly|allegedly)\s+)?behind\b|\b(?:developed|created|authored|operates|operated|controls|maintains|built)\b", re.I)

ATTRIBUTE_X_TO = re.compile(r"\battribut(?:e|es|ed|ing)\s+(?:the\s+|this\s+|these\s+)?$", re.I)
ATTRIBUTE_GAP = re.compile(r"^\s*(?:[\w-]+\s+){0,3}to\s*$", re.I)

CLAUSE_BREAK = re.compile(r";|\bwhile\b|\bwhereas\b|\bbut\b|\bhowever\b|\balthough\b|\bthough\b|\bmeanwhile\b", re.I)
COORDINATION = re.compile(
    r"^\s*(?:,|and|or|&|as well as|along with|together with|,\s*and|,\s*or|"
    r",?\s*(?:also\s+)?(?:known|tracked|referred to)\s+as|,?\s*a\.?k\.?a\.?|,?\s*dubbed|,?\s*\(|\)\s*,?)\s*$",
    re.I,
)
INFINITIVE = re.compile(r"^(?:,\s*)?(?:to|in order to|so as to)\b", re.I)

NEGATION = re.compile(
    r"\b(?:not|never|no longer|no evidence|ceased|stopped|denied|denies|falsely|incorrectly|mistakenly|"
    r"ruled out|disputes?|disputed|refuted|abandoned|retired|discontinued|without)\b|n't\b",
    re.I,
)


@dataclass
class RelationFact:
    subject: Entity
    relation: str
    object: Entity
    negated: bool
    confidence: float
    sentence: Sentence


def _type_ok(relation: str, subj: Entity, obj: Entity) -> bool:
    subj_ok, obj_ok = TYPE_RULES[relation]
    return subj.type in subj_ok and obj.type in obj_ok and subj.canonical_name != obj.canonical_name


def _adjust_relation(relation: str, obj: Entity) -> str:
    # "used CVE-2023-1234" / "leveraged CVE-..." means exploited
    if obj.type == "VULNERABILITY" and relation in ("USES", "DEPLOYS"):
        return "EXPLOITS"
    # "deployed T1059" / "used spearphishing" -> USES technique
    if obj.type == "TECHNIQUE" and relation == "DEPLOYS":
        return "USES"
    return relation


def _blocked_by_intermediate_subject(text: str, left: Entity, trigger_abs: int, between_entities: list[Entity]) -> bool:
    """Is there a closer subject for this trigger than `left`?

    'A used X and B deployed Y'   -> A->Y blocked (B is right before "deployed")
    'A and B used Y'              -> allowed (B is coordinated with A)
    'A, aka C, used X and Z to target O' -> A->O allowed ("to target" is A's purpose)
    """
    prev_end, in_subject_chain, blocker = left.char_end, True, None
    for e in between_entities:
        if e.char_start >= trigger_abs:
            break
        if e.type not in ACTORS | CODE:
            continue
        if not COORDINATION.match(text[prev_end:e.char_start]):
            in_subject_chain = False
        if not in_subject_chain:
            blocker = e
        prev_end = e.char_end
    if blocker is None:
        return False
    gap = text[blocker.char_end:trigger_abs].strip()
    return len(gap.split()) <= 3 and not INFINITIVE.match(gap)


def _pair_relation(text: str, a: Entity, b: Entity, between_entities: list[Entity]) -> tuple[str, Entity, Entity, float, int] | None:
    between = text[a.char_end:b.char_start]
    if len(between) > REL_MAX_GAP_CHARS or CLAUSE_BREAK.search(between):
        return None

    best = None  # (relation, subj, obj, conf, trigger_end_rel)
    for relation, pattern, conf, swap in PASSIVE_TRIGGERS:
        for m in pattern.finditer(between):
            subj, obj = (b, a) if swap else (a, b)
            rel = _adjust_relation(relation, obj)
            if _type_ok(rel, subj, obj) and (best is None or m.end() > best[4]):
                best = (rel, subj, obj, conf, m.end(), m.start())
    if best is None:
        for relation, pattern, conf in ACTIVE_TRIGGERS:
            for m in pattern.finditer(between):
                rel = _adjust_relation(relation, b)
                if _type_ok(rel, a, b) and (best is None or m.end() > best[4]):
                    best = (rel, a, b, conf, m.end(), m.start())
    if best is None and ATTRIBUTE_X_TO.search(text[max(0, a.char_start - 30):a.char_start]) and ATTRIBUTE_GAP.match(between):
        # "researchers attribute the Snake implant to APT29"
        if _type_ok("ATTRIBUTED_TO", a, b):
            best = ("ATTRIBUTED_TO", a, b, 0.75, len(between), 0)
    if best is None:
        m = REVERSE_ATTRIBUTION.search(between)
        if m and a.type in ACTORS and b.type in CODE:
            best = ("ATTRIBUTED_TO", b, a, 0.7, m.end(), m.start())
    if best is None:
        return None

    rel, subj, obj, conf, _, trig_start = best
    if _blocked_by_intermediate_subject(text, a, a.char_end + trig_start, between_entities):
        return None
    # long gaps are less reliable
    if len(between) > 80:
        conf -= 0.1
    conf *= min(subj.confidence, obj.confidence) ** 0.5
    return rel, subj, obj, round(max(0.05, min(conf, 0.99)), 3), a.char_end + trig_start


def _negated(text: str, sentence: Sentence, trigger_abs: int, obj: Entity) -> bool:
    window = text[sentence.start:max(trigger_abs, obj.char_start)]
    # only look at the clause containing the trigger
    window = re.split(r"[;,]\s*(?:but|while|whereas|however)\b", window)[-1]
    return bool(NEGATION.search(window))


def _model_relations(doc: PreparedDocument, entities: list[Entity], model, min_prob: float, max_pairs: int) -> list[RelationFact]:
    """Classify every plausible (subject, object) pair in each sentence with the trained RE model."""
    text = doc.text
    jobs: list[tuple[Sentence, Entity, Entity]] = []
    for sentence in doc.sentences:
        ents = [e for e in entities if sentence.start <= e.char_start and e.char_end <= sentence.end]
        pairs = []
        for a in ents:
            for b in ents:
                if a is b or a.canonical_name == b.canonical_name:
                    continue
                gap = max(a.char_start, b.char_start) - min(a.char_end, b.char_end)
                if gap > REL_MAX_GAP_CHARS:
                    continue
                if not any(a.type in s_ok and b.type in o_ok for s_ok, o_ok in TYPE_RULES.values()):
                    continue
                pairs.append((gap, a, b))
        for _, a, b in sorted(pairs, key=lambda x: x[0])[:max_pairs]:
            jobs.append((sentence, a, b))
    if not jobs:
        return []
    preds = model.classify([model.marked(text, s, a, b) for s, a, b in jobs])
    facts = []
    for (sentence, subj, obj), (label, prob) in zip(jobs, preds):
        if label not in TYPE_RULES or prob < min_prob:
            continue
        rel = _adjust_relation(label, obj)
        if not _type_ok(rel, subj, obj):
            continue
        conf = round(min(0.99, prob * min(subj.confidence, obj.confidence) ** 0.5), 3)
        neg = _negated(text, sentence, min(subj.char_end, obj.char_end), obj)
        facts.append(RelationFact(subj, rel, obj, neg, conf, sentence))
    return facts


def _prefer_actor_subjects(facts: list[RelationFact]) -> list[RelationFact]:
    """If an actor and a tool/malware both get the same relation to the same object in one sentence,
    the actor is the real subject ("APT28 used Mimikatz to target X" -> APT28 TARGETS X only)."""
    return [f for f in facts if f.subject.type in ACTORS or not any(
        g.subject.type in ACTORS and g.relation == f.relation and g.object.canonical_name == f.object.canonical_name
        and g.sentence.index == f.sentence.index for g in facts)]


def extract_relations(doc: PreparedDocument, entities: list[Entity], model=None, min_prob: float = 0.5,
                      max_pairs: int = 60) -> list[RelationFact]:
    rule_facts = _rule_relations(doc, entities)
    if model is None:
        return rule_facts
    merged = {(f.subject.canonical_name, f.relation, f.object.canonical_name, f.negated): f for f in rule_facts}
    for f in _model_relations(doc, entities, model, min_prob, max_pairs):
        key = (f.subject.canonical_name, f.relation, f.object.canonical_name, f.negated)
        if key in merged:  # found by rules AND model: more confident
            old = merged[key]
            old.confidence = round(min(0.99, 1 - (1 - old.confidence) * (1 - f.confidence)), 3)
        else:
            merged[key] = f
    return sorted(_prefer_actor_subjects(list(merged.values())),
                  key=lambda f: (f.sentence.start, f.subject.char_start, f.object.char_start))


def _rule_relations(doc: PreparedDocument, entities: list[Entity]) -> list[RelationFact]:
    facts: dict[tuple[str, str, str, bool], RelationFact] = {}
    text = doc.text
    for sentence in doc.sentences:
        ents = [e for e in entities if sentence.start <= e.char_start and e.char_end <= sentence.end]
        sentence_hits = []
        for i, a in enumerate(ents):
            for j in range(i + 1, len(ents)):
                b = ents[j]
                found = _pair_relation(text, a, b, ents[i + 1:j])
                if not found:
                    continue
                rel, subj, obj, conf, trigger_abs = found
                sentence_hits.append((rel, subj, obj, conf, trigger_abs))
        # If an actor and a tool both look like the subject of the same trigger + object,
        # the actor is the real subject ("APT28 used Mimikatz to target X" -> APT28 TARGETS X).
        for rel, subj, obj, conf, trigger_abs in sentence_hits:
            if subj.type not in ACTORS and any(
                o is obj and t == trigger_abs and s.type in ACTORS for _, s, o, _, t in sentence_hits
            ):
                continue
            neg = _negated(text, sentence, trigger_abs, obj)
            key = (subj.canonical_name, rel, obj.canonical_name, neg)
            if key not in facts or facts[key].confidence < conf:
                facts[key] = RelationFact(subj, rel, obj, neg, conf, sentence)
    return sorted(facts.values(), key=lambda f: (f.sentence.start, f.subject.char_start, f.object.char_start))
