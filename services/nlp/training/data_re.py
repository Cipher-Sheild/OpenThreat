"""AZERG (QCRI/AZERG-Dataset, Apache-2.0) -> relation classification examples with our labels.

AZERG is stored as instruction/answer pairs for four tasks (T1 entity detection, T2 typing,
T3 "are these two entities related? YES/NO", T4 "which relation label?"). We use:
  * T4 rows -> the STIX label, mapped to our 5 relation types (or OTHER)
  * T3 rows answered NO, and T4 "is not related to" -> NONE (negative examples)
  * AZERG has (almost) no explicit negatives, so more NONE examples are generated from T1 entity
    lists: entity pairs in the same passage that are not annotated as related
Each example is the passage with the two entities wrapped in markers:
  "[E1] APT16 [/E1] ... [E2] ELMER [/E2] ..."  (E1 = source/subject, E2 = target/object)
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass

STIX_TO_OURS = {
    "uses": "USES",
    "drops": "DEPLOYS",
    "downloads": "DEPLOYS",
    "delivers": "DEPLOYS",
    "installs": "DEPLOYS",
    "exploits": "EXPLOITS",
    "targets": "TARGETS",
    "compromises": "TARGETS",
    "attributed-to": "ATTRIBUTED_TO",
    "authored-by": "ATTRIBUTED_TO",
    "is not related to": "NONE",
}
DROP_LABELS = {"not sure"}

MARKERS = ["[E1]", "[/E1]", "[E2]", "[/E2]"]

_INPUT = re.compile(
    r"###\s*Source Entity:\s*(?P<src>.*?)\s*###\s*Target Entity:\s*(?P<tgt>.*?)\s*###.*?###\s*Text Passage:\s*(?P<text>.*)",
    re.S,
)
_LABEL = re.compile(r"<label>\s*(.*?)\s*</label>", re.S)
_RELATED = re.compile(r"<related>\s*(YES|NO)\s*</related>", re.S | re.I)


@dataclass
class REExample:
    text: str  # passage with markers
    subject: str
    object: str
    label: str  # one of common.RE_LABELS
    stix_label: str


def map_label(stix: str) -> str:
    stix = stix.strip().lower()
    return STIX_TO_OURS.get(stix, "OTHER")


def _find(text: str, name: str, taken: tuple[int, int] | None = None) -> tuple[int, int] | None:
    for flags in (0, re.I):
        for m in re.finditer(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", text, flags):
            if taken and m.start() < taken[1] and taken[0] < m.end():
                continue
            return m.start(), m.end()
    return None


def mark(text: str, subj: str, obj: str) -> str | None:
    """Wrap the first mention of subject and object in markers. None if either is missing."""
    s = _find(text, subj)
    if s is None:
        return None
    o = _find(text, obj, taken=s)
    if o is None:
        return None
    spans = sorted([(s, "[E1]", "[/E1]"), (o, "[E2]", "[/E2]")], key=lambda x: x[0][0], reverse=True)
    for (a, b), open_, close in spans:
        text = text[:a] + f"{open_} {text[a:b]} {close}" + text[b:]
    return text


_PASSAGE = re.compile(r"###\s*Text Passage:\s*(?P<text>.*)", re.S)
_ENTITIES = re.compile(r"<entities>\s*(.*?)\s*</entities>", re.S)


def parse_rows(rows, neg_ratio: float = 1.0, seed: int = 42) -> tuple[list[REExample], Counter]:
    """rows: iterable of dicts with instruction/input/output.

    Positives come from T4 (relation label) rows. AZERG has no explicit negative rows, so negatives
    are generated the standard way: every ordered pair of entities listed for the same passage (T1
    rows) that is not annotated as related becomes NONE, including the reversed direction of a
    related pair. Negatives are sampled to `neg_ratio` x the number of positives.
    """
    import random

    examples: dict[tuple[str, str, str], REExample] = {}
    related_pairs: set[tuple[str, str, str]] = set()  # any annotated pair, incl. T3 YES without a label
    passage_entities: dict[str, list[str]] = {}
    skipped = Counter()
    for row in rows:
        instr, inp, outp = row["instruction"], row["input"] or "", row["output"] or ""
        m = _INPUT.search(inp)
        if not m:
            pm, em = _PASSAGE.search(inp), _ENTITIES.search(outp)
            if pm and em and "extract all" in instr.lower():  # T1: entity list for a passage
                ents = [e.strip() for e in em.group(1).split("|") if e.strip()]
                passage_entities[pm.group("text").strip()] = ents
            continue
        src, tgt, passage = m.group("src").strip(), m.group("tgt").strip(), m.group("text").strip()
        if "label of the relationship" in instr:
            lm = _LABEL.search(outp)
            if not lm:
                skipped["no_label"] += 1
                continue
            stix = lm.group(1).strip().lower()
            related_pairs.add((src, tgt, passage))
            if stix in DROP_LABELS:
                skipped["not_sure"] += 1
                continue
            label = map_label(stix)
        elif "semantically related" in instr:
            rm = _RELATED.search(outp)
            if rm and rm.group(1).upper() == "YES":
                related_pairs.add((src, tgt, passage))
                continue  # the label comes from the matching T4 row
            if not rm:
                continue
            stix, label = "no", "NONE"
        else:
            continue
        marked = mark(passage, src, tgt)
        if marked is None:
            skipped["entity_not_in_passage"] += 1
            continue
        key = (src, tgt, passage)
        if key not in examples or examples[key].label == "NONE":
            examples[key] = REExample(marked, src, tgt, label, stix)

    # ---- generated negatives
    n_pos = sum(1 for e in examples.values() if e.label != "NONE")
    candidates = []
    for passage, ents in passage_entities.items():
        uniq = list(dict.fromkeys(ents))
        for a in uniq:
            for b in uniq:
                if a == b or a.casefold() in b.casefold() or b.casefold() in a.casefold():
                    continue
                if (a, b, passage) in related_pairs or (a, b, passage) in examples:
                    continue
                candidates.append((a, b, passage))
    rng = random.Random(seed)
    rng.shuffle(candidates)
    added = 0
    for a, b, passage in candidates:
        if added >= int(neg_ratio * n_pos):
            break
        marked = mark(passage, a, b)
        if marked is None:
            continue
        examples[(a, b, passage)] = REExample(marked, a, b, "NONE", "generated-negative")
        added += 1
    skipped["generated_negatives"] = added
    skipped["negative_candidates"] = len(candidates)
    return list(examples.values()), skipped


def load_azerg(split: str, local_jsonl: str | None = None) -> tuple[list[REExample], Counter]:
    if local_jsonl:
        rows = [json.loads(l) for l in open(local_jsonl, encoding="utf-8") if l.strip()]
        rows = [r for r in rows if r.get("split", split) == split]
    else:
        from datasets import load_dataset

        rows = load_dataset("QCRI/AZERG-Dataset", split=split)
    return parse_rows(rows)
