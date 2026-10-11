"""Name lists (gazetteers) used by the rule-based NER and by entity resolution.

Built from MITRE ATT&CK (groups, malware, tools, techniques) plus resources/extra_entities.json.
Every alias points to one canonical name, e.g. "Fancy Bear" -> ("APT28", THREAT_ACTOR).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache

from config import RESOURCES_DIR

# Single words that are also ordinary English / too generic to tag without a model.
AMBIGUOUS = {
    "at", "net", "page", "play", "epic", "cuba", "ping", "route", "expand", "reg", "ftp", "cmd",
    "mori", "dok", "zox", "orz", "yty", "lv", "abk", "bbk", "tvt", "skid", "naid", "kaba", "doki",
    "get2", "ps1", "out1", "zlib", "arp", "meek", "page", "tor", "pony", "maze", "ryuk", "trap",
    "empire", "sogu", "hello", "cobalt", "net crawler", "kido", "kwampirs", "matryoshka", "machete",
    "pegasus", "remsec", "dust", "shark", "nightdragon", "inception",
}
# Short or common names that are fine when written in their exact case
CASE_SENSITIVE_OK = {"Ryuk", "Maze", "Tor", "Empire", "Sandworm Team", "Pegasus", "Machete", "Sandworm"}

TECHNIQUE_SINGLE_WORD_OK = {
    "Phishing", "Kerberoasting", "Keylogging", "Masquerading", "Timestomp", "DCSync", "Steganography",
    "Malvertising", "Bootkit", "Rootkit", "Defacement", "Adversary-in-the-Middle", "Rundll32",
    "Regsvr32", "Mshta", "InstallUtil", "CMSTP",
}


def norm_key(name: str) -> str:
    """'APT 28' / 'apt-28' / 'APT28' -> 'apt28'."""
    return re.sub(r"[^0-9a-z]", "", name.casefold())


@dataclass
class Entry:
    canonical: str
    type: str
    aliases: set[str] = field(default_factory=set)
    attack_id: str | None = None


@dataclass
class Gazetteer:
    entries: list[Entry]
    by_key: dict[str, list[Entry]]  # norm_key(alias) -> entries
    surface: dict[str, list[tuple[Entry, bool]]]  # exact surface alias -> (entry, case_sensitive)
    techniques_by_id: dict[str, dict]
    technique_names: dict[str, str]  # lowercase name -> technique id (only unambiguous names)
    sectors: list[str]

    def lookup(self, name: str, type_hint: str | None = None) -> Entry | None:
        cands = self.by_key.get(norm_key(name), [])
        if type_hint:
            typed = [e for e in cands if e.type == type_hint]
            cands = typed or cands
        if not cands:
            return None
        # prefer an entry whose canonical name equals the query
        for e in cands:
            if norm_key(e.canonical) == norm_key(name):
                return e
        return cands[0]


def _load(name: str) -> dict:
    return json.loads((RESOURCES_DIR / name).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def get_gazetteer() -> Gazetteer:
    entries: list[Entry] = []
    for g in _load("attack_groups.json")["items"]:
        entries.append(Entry(g["name"], "THREAT_ACTOR", set(g["aliases"]), g["id"]))
    for s in _load("attack_software.json")["items"]:
        entries.append(Entry(s["name"], s["type"], set(s["aliases"]), s["id"]))

    extra = _load("extra_entities.json")
    for etype in ("ORGANIZATION", "THREAT_ACTOR", "MALWARE", "TOOL"):
        for canonical, aliases in extra.get(etype, {}).items():
            existing = next((e for e in entries if norm_key(e.canonical) == norm_key(canonical)), None)
            if existing:
                existing.aliases.update([canonical, *aliases])
                existing.type = etype  # our hand-maintained list overrides ATT&CK's type
            else:
                entries.append(Entry(canonical, etype, {canonical, *aliases}))

    by_key: dict[str, list[Entry]] = {}
    surface: dict[str, list[tuple[Entry, bool]]] = {}
    for e in entries:
        e.aliases.add(e.canonical)
        for alias in e.aliases:
            key = norm_key(alias)
            if not key:
                continue
            by_key.setdefault(key, []).append(e)
            low = alias.casefold()
            if alias in CASE_SENSITIVE_OK:
                surface.setdefault(alias, []).append((e, True))
                continue
            if low in AMBIGUOUS or len(key) <= 2:
                continue
            # single-token names are matched case-sensitively; multi-word names case-insensitively
            case_sensitive = " " not in alias.strip() and len(alias) < 8
            surface.setdefault(alias, []).append((e, case_sensitive))

    techniques_by_id, name_to_ids = {}, {}
    for t in _load("attack_techniques.json")["items"]:
        techniques_by_id[t["id"]] = t
        name_to_ids.setdefault(t["name"].casefold(), []).append(t["id"])
    technique_names = {}
    for low, ids in name_to_ids.items():
        if len(ids) != 1:
            continue  # same sub-technique name under several parents: ambiguous without a model
        original = techniques_by_id[ids[0]]["name"]
        if " " not in original and original not in TECHNIQUE_SINGLE_WORD_OK:
            continue
        technique_names[low] = ids[0]

    return Gazetteer(entries, by_key, surface, techniques_by_id, technique_names, extra.get("SECTORS", []))
