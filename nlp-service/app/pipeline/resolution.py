"""Entity resolution: decide whether a mention is an entity we already know.

Order (cheapest and most reliable first, as agreed in the starter guide):
  1. exact        - same normalised name ("APT 28" == "apt28")
  2. alias        - matches one of the entity's aliases stored in Postgres
  3. builtin_alias- our ATT&CK/extra alias lists say they are the same ("Fancy Bear" -> APT28)
  4. string_similarity  - fuzzy match (typos, spacing), never across different numbers
  5. semantic_similarity- embedding similarity of names
  "context" is applied throughout as a type filter: a MALWARE mention never resolves to a TOOL.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
from rapidfuzz import fuzz

from config import RESOLVE_FUZZY_ACCEPT, RESOLVE_SEMANTIC_ACCEPT
from pipeline.embeddings import get_embedder
from pipeline.gazetteer import get_gazetteer, norm_key

# Types where only an exact (normalised) match counts: IDs, hashes, IPs, domains
EXACT_ONLY_TYPES = {"VULNERABILITY", "OBSERVABLE", "TECHNIQUE"}
# Types that can stand in for each other (NER often confuses malware and tools)
COMPATIBLE = {
    "MALWARE": {"MALWARE", "TOOL"},
    "TOOL": {"TOOL", "MALWARE"},
}


@dataclass
class KnownEntity:
    entity_id: str
    canonical_name: str
    type: str | None = None
    aliases: list[str] = field(default_factory=list)

    def names(self) -> list[str]:
        return [self.canonical_name, *self.aliases]


@dataclass
class Resolution:
    mention: str
    entity_id: str | None
    canonical_name: str
    method: str
    score: float
    new_aliases: list[str]


def _types_compatible(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return True
    return b in COMPATIBLE.get(a, {a})


def _digits(s: str) -> list[str]:
    return re.findall(r"\d+", s)


def builtin_canonical(mention: str, type_hint: str | None = None) -> str | None:
    entry = get_gazetteer().lookup(mention, type_hint)
    if entry and _types_compatible(type_hint, entry.type):
        return entry.canonical
    return None


def _new_aliases(mention: str, known: KnownEntity) -> list[str]:
    keys = {norm_key(n) for n in known.names()}
    return [] if norm_key(mention) in keys else [mention]


def resolve(mention: str, type_hint: str | None, known: list[KnownEntity], use_semantic: bool = True) -> Resolution:
    key = norm_key(mention)
    pool = [k for k in known if _types_compatible(type_hint, k.type)]
    exact_only = type_hint in EXACT_ONLY_TYPES

    # 1. exact canonical
    for k in pool:
        if norm_key(k.canonical_name) == key:
            return Resolution(mention, k.entity_id, k.canonical_name, "exact", 1.0, [])
    # 2. stored alias
    for k in pool:
        if any(norm_key(a) == key for a in k.aliases):
            return Resolution(mention, k.entity_id, k.canonical_name, "alias", 0.98, _new_aliases(mention, k))
    # 3. built-in alias knowledge (ATT&CK + extra list)
    if not exact_only:
        canon = builtin_canonical(mention, type_hint)
        if canon:
            ckey = norm_key(canon)
            entry = get_gazetteer().lookup(canon, type_hint)
            entry_keys = {norm_key(a) for a in entry.aliases} if entry else {ckey}
            for k in pool:
                if any(norm_key(n) in entry_keys for n in k.names()):
                    return Resolution(mention, k.entity_id, k.canonical_name, "builtin_alias", 0.95, _new_aliases(mention, k))

    fallback_name = (builtin_canonical(mention, type_hint) if not exact_only else None) or mention
    if exact_only or not pool:
        return Resolution(mention, None, fallback_name, "none", 0.0, [])

    # 4. string similarity
    best: tuple[float, KnownEntity | None] = (0.0, None)
    for k in pool:
        for n in k.names():
            if _digits(n) != _digits(mention):  # APT28 vs APT29, CVE-...-1 vs -2
                continue
            score = fuzz.ratio(key, norm_key(n)) / 100.0
            if min(len(key), len(norm_key(n))) < 4:
                score *= 0.8  # very short names: fuzzy matches are unreliable
            if score > best[0]:
                best = (score, k)
    if best[1] is not None and best[0] >= RESOLVE_FUZZY_ACCEPT:
        k = best[1]
        return Resolution(mention, k.entity_id, k.canonical_name, "string_similarity", round(best[0], 3), _new_aliases(mention, k))

    # 5. semantic similarity of names
    if use_semantic:
        names, owners = [], []
        for k in pool:
            for n in k.names():
                if _digits(n) == _digits(mention):
                    names.append(n)
                    owners.append(k)
        if names:
            vecs = get_embedder().encode([mention, *names])
            sims = vecs[1:] @ vecs[0]
            i = int(np.argmax(sims))
            if float(sims[i]) >= RESOLVE_SEMANTIC_ACCEPT:
                k = owners[i]
                return Resolution(mention, k.entity_id, k.canonical_name, "semantic_similarity",
                                  round(float(sims[i]), 3), _new_aliases(mention, k))

    return Resolution(mention, None, fallback_name, "none", 0.0, [])


def name_match_score(name: str, other: str, other_aliases: list[str], type_hint: str | None = None) -> float:
    """How sure are we that `name` and `other` are the same entity? 0 = different."""
    r = resolve(name, type_hint, [KnownEntity("x", other, None, list(other_aliases or []))], use_semantic=False)
    return r.score if r.entity_id else 0.0
