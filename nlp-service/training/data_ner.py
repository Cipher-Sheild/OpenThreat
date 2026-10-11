"""CyberNER (harmonised CyNER + DNRTI + APTNER + Attacker, STIX labels) -> our 7 entity types.

Split: deterministic 80/10/10 per source dataset (seed 42), so every source is represented in
train/dev/test. The same function is used by the Colab training and by the local rule-based
baseline, so both are evaluated on exactly the same test sentences.
"""
from __future__ import annotations

import csv
import random
from collections import defaultdict
from dataclasses import dataclass

# STIX label (CyberNER) -> our type. Anything not listed becomes O.
STIX_TO_OURS = {
    "Threat-Actor": "THREAT_ACTOR",
    "Intrusion-Set": "THREAT_ACTOR",
    "Campaign": "THREAT_ACTOR",
    "Malware": "MALWARE",
    "Tool": "TOOL",
    "Software": "TOOL",
    "Vulnerability": "VULNERABILITY",
    "Attack-Pattern": "TECHNIQUE",
    "Identity": "ORGANIZATION",
    "Indicator": "OBSERVABLE",
    "File": "OBSERVABLE",
    "Domain-Name": "OBSERVABLE",
    "IPv4-Addr": "OBSERVABLE",
    "URL": "OBSERVABLE",
    "Email-Addr": "OBSERVABLE",
}
# Dropped to O for v1: Location, Malware-Analysis, Infrastructure, Observed-Data, Network-Traffic, Course-of-Action


@dataclass
class Sentence:
    key: str  # "<source>:<sentence_id>"
    source: str
    tokens: list[str]
    tags: list[str]


def map_tag(stix_tag: str) -> str:
    if stix_tag in ("O", "", None):
        return "O"
    prefix, _, label = stix_tag.partition("-")
    ours = STIX_TO_OURS.get(label)
    return f"{prefix}-{ours}" if ours else "O"


def _repair_bio(tags: list[str]) -> list[str]:
    """After mapping, 'I-X' may follow O or another type (e.g. merged labels); make it 'B-X'."""
    out, prev = [], "O"
    for t in tags:
        if t.startswith("I-") and (prev == "O" or prev[2:] != t[2:]):
            t = "B-" + t[2:]
        out.append(t)
        prev = t
    return out


def load_cyberner(csv_path: str) -> list[Sentence]:
    groups: dict[str, Sentence] = {}
    order: list[str] = []
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = f"{row['Source']}:{row['Sentence_ID']}"
            if key not in groups:
                groups[key] = Sentence(key, row["Source"], [], [])
                order.append(key)
            word = row["Word"]
            if word is None or word == "":
                continue
            groups[key].tokens.append(word)
            groups[key].tags.append(map_tag(row["STIX_Tag"]))
    sentences = [groups[k] for k in order if groups[k].tokens]
    for s in sentences:
        s.tags = _repair_bio(s.tags)
    return sentences


def split(sentences: list[Sentence], seed: int = 42, dev: float = 0.1, test: float = 0.1) -> dict[str, list[Sentence]]:
    by_source = defaultdict(list)
    for s in sentences:
        by_source[s.source].append(s)
    parts = {"train": [], "dev": [], "test": []}
    for source in sorted(by_source):
        items = sorted(by_source[source], key=lambda s: s.key)
        random.Random(f"{seed}-{source}").shuffle(items)
        n_test, n_dev = int(len(items) * test), int(len(items) * dev)
        parts["test"] += items[:n_test]
        parts["dev"] += items[n_test:n_test + n_dev]
        parts["train"] += items[n_test + n_dev:]
    return parts


def stats(parts: dict[str, list[Sentence]]) -> dict:
    out = {}
    for name, items in parts.items():
        counts = defaultdict(int)
        for s in items:
            for t in s.tags:
                if t.startswith("B-"):
                    counts[t[2:]] += 1
        out[name] = {"sentences": len(items), "tokens": sum(len(s.tokens) for s in items), "entities": dict(counts)}
    return out
