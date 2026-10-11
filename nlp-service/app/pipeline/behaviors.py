"""Behaviours mapped to MITRE ATT&CK.

Phase 2: explicit technique IDs (T1566.001) and exact technique names ("Kerberoasting",
"Spearphishing Attachment") found by NER. Phase 4 adds semantic mapping (sentence embedding vs.
technique descriptions) for behaviours that are described without naming the technique.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from pipeline.gazetteer import get_gazetteer
from pipeline.ner import Entity
from pipeline.preprocess import PreparedDocument, Sentence


@dataclass
class Behavior:
    description: str
    mitre_attack_id: str | None
    mitre_attack_name: str | None
    confidence: float
    sentence: Sentence


BEHAVIOUR_VERBS = re.compile(
    r"\b(?:dump\w*|harvest\w*|steal\w*|stole|exfiltrat\w*|encrypt\w*|inject\w*|escalat\w*|scan\w*|enumerat\w*|"
    r"persist\w*|execut\w*|launch\w*|download\w*|upload\w*|obfuscat\w*|beacon\w*|registry|scheduled task|"
    r"phish\w*|spearphish\w*|brute.?forc\w*|lateral\w*|keylog\w*|screenshot\w*|captur\w*|disabl\w*|delet\w*|"
    r"wip\w*|compress\w*|archiv\w*|tunnel\w*|proxy|masquerad\w*|sideload\w*|hijack\w*|impersonat\w*|"
    r"credential\w*|password\w*|token\w*|privilege\w*|backdoor\w*|implant\w*|shell)\b",
    re.I,
)


def extract_behaviors(doc: PreparedDocument, entities: list[Entity], mapper=None, min_similarity: float = 0.8) -> list[Behavior]:
    gz = get_gazetteer()
    out: dict[tuple[str, int], Behavior] = {}

    def add(tid, sentence, conf):
        tech = gz.techniques_by_id.get(tid)
        key = (tid, sentence.index)
        conf = conf if tech else min(conf, 0.5)
        if key not in out or out[key].confidence < conf:
            out[key] = Behavior(
                description=sentence.text if len(sentence.text) <= 400 else sentence.text[:397] + "...",
                mitre_attack_id=tid if tech else None,
                mitre_attack_name=tech["name"] if tech else None,
                confidence=round(conf, 3),
                sentence=sentence,
            )

    # 1. explicit technique IDs / exact technique names found by NER
    explicit_sentences = set()
    for e in entities:
        if e.type != "TECHNIQUE":
            continue
        sentence = next((s for s in doc.sentences if s.start <= e.char_start < s.end), None)
        if sentence is None:
            continue
        add(e.attack_id or e.canonical_name, sentence, e.confidence)
        explicit_sentences.add(sentence.index)

    # 2. semantic mapping for sentences that describe behaviour in plain words
    if mapper is not None:
        cands = []
        for s in doc.sentences:
            if s.index in explicit_sentences or len(s.text.split()) < 5:
                continue
            has_actor = any(s.start <= e.char_start < s.end and e.type in ("THREAT_ACTOR", "MALWARE", "TOOL")
                            for e in entities)
            if has_actor or BEHAVIOUR_VERBS.search(s.text):
                cands.append(s)
        if cands:
            for s, m in zip(cands, mapper.best([c.text for c in cands])):
                if m.score >= min_similarity:
                    # map similarity in [threshold, 1] to confidence in [0.5, 0.9]
                    conf = 0.5 + 0.4 * (m.score - min_similarity) / max(1e-6, 1 - min_similarity)
                    add(m.technique_id, s, conf)
    return sorted(out.values(), key=lambda b: (b.sentence.start, -b.confidence))
