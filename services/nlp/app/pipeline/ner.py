"""Phase 2 rule-based NER: regex for IOCs + gazetteers + name patterns.

Phase 3 replaces `extract_entities` with a fine-tuned transformer; the output type stays the same.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from pipeline.gazetteer import get_gazetteer
from pipeline.preprocess import PreparedDocument, refang


@dataclass
class Entity:
    mention: str
    canonical_name: str
    type: str
    subtype: str | None
    confidence: float
    char_start: int
    char_end: int
    page_number: int | None = None
    attack_id: str | None = None
    priority: int = 0  # higher wins when spans overlap


_DOT = r"(?:\.|\[\.\]|\(\.\)|\{\.\}|\[dot\])"
_TLDS = (
    "com|net|org|info|biz|io|co|ru|cn|su|ir|kp|xyz|top|online|site|club|uk|de|fr|jp|kr|in|br|nl|eu|ws|"
    "ly|to|me|us|cc|pw|tk|ml|ga|cf|gq|app|dev|cloud|live|link|space|website|tech|store|shop|gov|edu|mil|"
    "int|onion|icu|vip|buzz|fun|work|tw|hk|ua|by|kz|vn|id|pk|ae|sa|il|tr|it|es|pl|ca|au"
)
_OCTET = r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"

IOC_PATTERNS: list[tuple[str, str | None, re.Pattern, float, int]] = [
    # (type, subtype, pattern, confidence, priority)
    ("VULNERABILITY", None, re.compile(r"\bCVE[-‐–]\d{4}[-‐–]\d{4,7}\b", re.I), 0.99, 100),
    ("OBSERVABLE", "url", re.compile(r"\b(?:h[tx]{2}ps?|ftp)(?:\[:\]|:)//[^\s<>\"']+", re.I), 0.95, 95),
    ("OBSERVABLE", "email", re.compile(r"\b[\w.+-]+(?:@|\[@\]|\[at\])[\w-]+(?:" + _DOT + r"[\w-]+)+\b", re.I), 0.9, 90),
    ("OBSERVABLE", "sha256", re.compile(r"\b[a-fA-F0-9]{64}\b"), 0.97, 92),
    ("OBSERVABLE", "sha1", re.compile(r"\b[a-fA-F0-9]{40}\b"), 0.95, 91),
    ("OBSERVABLE", "md5", re.compile(r"\b[a-fA-F0-9]{32}\b"), 0.93, 90),
    ("OBSERVABLE", "ipv4", re.compile(r"(?<![\w.])(?:" + _OCTET + _DOT + r"){3}" + _OCTET + r"(?![\w.]\w)"), 0.9, 85),
    (
        "OBSERVABLE",
        "domain",
        re.compile(
            r"(?<![\w@.-])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?" + _DOT + r")+(?:" + _TLDS + r")(?![\w-])",
            re.I,
        ),
        0.8,
        80,
    ),
    ("TECHNIQUE", None, re.compile(r"\bT1\d{3}(?:\.\d{3})?\b"), 0.97, 88),
]

ACTOR_PATTERNS = [
    re.compile(r"\b(?:APT|UNC|FIN|TA|DEV-|Storm-|TEMP\.)\s?-?\d{1,4}\b"),
    re.compile(
        r"\b[A-Z][a-z]+ (?:Panda|Bear|Kitten|Chollima|Spider|Jackal|Typhoon|Blizzard|Sleet|Sandstorm|"
        r"Tempest|Hail|Cyclone|Tsunami|Leopard|Tiger|Libra|Taurus|Scorpius|Ursa|Serpens|Pisces|Draco)\b"
    ),
]
_CODE_NOUNS = (r"(?:implant|malware|backdoor|trojan|RAT|ransomware|loader|dropper|stealer|infostealer|rootkit|worm|"
               r"wiper|botnet|downloader|keylogger|variant|payload|framework|toolkit|tool|beacon|web ?shell|spyware|sample|family)s?")
MALWARE_CONTEXT_AFTER = re.compile(r"^\s*(?:\w+\s+)?" + _CODE_NOUNS + r"\b", re.I)
ACTOR_CONTEXT_AFTER = re.compile(r"^\s*(?:group|actors?|threat actors?|APT|gang|operators?|hackers|crew|team|cluster)\b", re.I)
ACTOR_CONTEXT_BEFORE = re.compile(r"\b(?:group|actor|attributed to|linked to|operated by|tracked as)\s+$", re.I)

# Unknown malware names, introduced by their kind: "HeadLace, a backdoor", "the new Foo ransomware"
UNKNOWN_MALWARE = [
    re.compile(r"\b([A-Z][A-Za-z0-9._-]{2,}(?:\s[A-Z][A-Za-z0-9._-]+)?)(?=,?\s+(?:a|an)\s+(?:new\s+|novel\s+|custom\s+|previously\s+unknown\s+|\w+-based\s+)*" + _CODE_NOUNS + r"\b)"),
    re.compile(r"\b(?:the|a|new|custom|novel)\s+([A-Z][A-Za-z0-9._-]{2,})(?=\s+" + _CODE_NOUNS + r"\b)"),
]
_NOT_NAMES = {"The", "This", "That", "These", "Its", "Their", "Our", "New", "Custom", "Windows", "Linux", "Python",
              "PowerShell", "Java", "Go", "Rust", "Android", "iOS", "macOS", "Microsoft", "Google", "Russian",
              "Chinese", "Iranian", "North", "Korean", "Researchers", "Analysts"}

# "The group" / "the actor" -> the most recently named threat actor
COREFERENCE = re.compile(r"\b(?:the|this|these)\s+(?:threat\s+)?(?:group|actors?|adversary|attackers|APT|intrusion set|operators)\b", re.I)

ORG_SUFFIX = re.compile(
    r"\b(?:[A-Z][\w&'-]+ ){0,3}[A-Z][\w&'-]+,? (?:Inc\.?|Corp\.?|Corporation|Ltd\.?|LLC|GmbH|S\.A\.|plc|"
    r"University|Bank|Airlines|Hospital|Ministry)\b"
)
ORG_GOV = re.compile(r"\b(?:Ministry|Department|Embassy) of (?:the )?(?:[A-Z][a-z]+ ?){1,4}\b")


@lru_cache(maxsize=1)
def _gazetteer_regexes() -> tuple[re.Pattern | None, re.Pattern | None, re.Pattern | None]:
    gz = get_gazetteer()
    cs, ci = [], []
    for alias, items in gz.surface.items():
        (cs if all(c for _, c in items) else ci).append(alias)

    def build(names: list[str], flags: int) -> re.Pattern | None:
        if not names:
            return None
        alt = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
        return re.compile(r"(?<![\w-])(?:" + alt + r")(?![\w-])", flags)

    tech_alt = "|".join(re.escape(n) for n in sorted(gz.technique_names, key=len, reverse=True))
    tech = re.compile(r"(?<![\w-])(?:" + tech_alt + r")(?![\w-])", re.I) if tech_alt else None
    return build(cs, 0), build(ci, re.I), tech


@lru_cache(maxsize=1)
def _surface_casefold() -> dict:
    out: dict = {}
    for alias, items in get_gazetteer().surface.items():
        out.setdefault(alias.casefold(), []).extend(items)
    return out


@lru_cache(maxsize=1)
def _sector_regex() -> re.Pattern:
    sectors = sorted(get_gazetteer().sectors, key=len, reverse=True)
    alt = "|".join(re.escape(s) for s in sectors)
    return re.compile(r"\b(?:" + alt + r")\s+(?:sector|industry|organi[sz]ations|entities|companies|firms|agencies|institutions|ministries)\b", re.I)


def _canonical_ioc(etype: str, subtype: str | None, mention: str) -> str:
    if etype == "VULNERABILITY":
        return re.sub(r"[‐–]", "-", mention).upper()
    if etype == "TECHNIQUE":
        return mention.upper()
    value = refang(mention)
    if subtype in ("domain", "email", "md5", "sha1", "sha256"):
        value = value.lower()
    if subtype == "url":
        value = value.rstrip(".,;:)")
    return value


def _find_all(text: str) -> list[Entity]:
    gz = get_gazetteer()
    found: list[Entity] = []

    for etype, subtype, pattern, conf, prio in IOC_PATTERNS:
        for m in pattern.finditer(text):
            mention = m.group(0)
            if subtype == "url":
                mention = mention.rstrip(".,;:")
                while mention and mention[-1] in ")]" and mention.count(mention[-1]) > mention.count("(" if mention[-1] == ")" else "["):
                    mention = mention[:-1].rstrip(".,;:")
            if subtype in ("md5", "sha1", "sha256") and (mention.isdigit() or mention.isalpha()):
                continue
            if subtype == "ipv4" and re.search(r"(?:version|v)\s*$", text[max(0, m.start() - 9):m.start()], re.I):
                continue
            canonical = _canonical_ioc(etype, subtype, mention)
            attack_id = canonical if etype == "TECHNIQUE" else None
            if etype == "TECHNIQUE" and canonical not in gz.techniques_by_id:
                conf = 0.6
            found.append(Entity(mention, canonical, etype, subtype, conf, m.start(), m.start() + len(mention),
                                attack_id=attack_id, priority=prio))

    cs_re, ci_re, tech_re = _gazetteer_regexes()
    for regex in (cs_re, ci_re):
        if regex is None:
            continue
        for m in regex.finditer(text):
            mention = m.group(0)
            items = gz.surface.get(mention)
            if items is None:  # case-insensitive hit: find the alias it matched
                items = _surface_casefold().get(mention.casefold(), [])
            if not items:
                continue
            # prefer the entry whose canonical name is the mention itself, then actors
            # Prefer the entry whose canonical name IS the mention. If a group and a piece of software share
            # that exact name (e.g. AppleJeus), prefer the software; for alias-only hits prefer the actor.
            def _rank(it, m=mention.casefold()):
                exact = it[0].canonical.casefold() == m
                return (not exact, (it[0].type == "THREAT_ACTOR") if exact else (it[0].type != "THREAT_ACTOR"))
            items = sorted(items, key=_rank)
            entry = items[0][0]
            ctx_after = text[m.end():m.end() + 25]
            ctx_before = text[max(0, m.start() - 25):m.start()]
            code_entry = next((it[0] for it in items if it[0].type in ("MALWARE", "TOOL")), None)
            actor_entry = next((it[0] for it in items if it[0].type == "THREAT_ACTOR"), None)
            if code_entry and MALWARE_CONTEXT_AFTER.match(ctx_after):
                entry = code_entry
            elif actor_entry and (ACTOR_CONTEXT_AFTER.match(ctx_after) or ACTOR_CONTEXT_BEFORE.search(ctx_before)):
                entry = actor_entry
            conf = 0.9 if " " in mention or len(mention) >= 5 else 0.8
            found.append(Entity(mention, entry.canonical, entry.type, None, conf, m.start(), m.end(),
                                attack_id=entry.attack_id, priority=60 + len(mention)))

    if tech_re is not None:
        for m in tech_re.finditer(text):
            tid = gz.technique_names[m.group(0).casefold()]
            found.append(Entity(m.group(0), tid, "TECHNIQUE", None, 0.65, m.start(), m.end(),
                                attack_id=tid, priority=40 + len(m.group(0))))

    for pattern in ACTOR_PATTERNS:
        for m in pattern.finditer(text):
            entry = gz.lookup(m.group(0), "THREAT_ACTOR")
            canonical = entry.canonical if entry else re.sub(r"\s+", "", m.group(0)) if m.group(0)[:3].isupper() else m.group(0)
            found.append(Entity(m.group(0), canonical, "THREAT_ACTOR", None, 0.85, m.start(), m.end(),
                                attack_id=entry.attack_id if entry else None, priority=55))

    for pattern in UNKNOWN_MALWARE:
        for m in pattern.finditer(text):
            name = m.group(1)
            if name.split()[0] in _NOT_NAMES or name.isupper() and len(name) <= 3:
                continue
            entry = gz.lookup(name)
            if entry and entry.type in ("MALWARE", "TOOL"):
                continue  # the gazetteer already handles known names
            found.append(Entity(name, name, "MALWARE", None, 0.7, m.start(1), m.end(1), priority=50))

    for pattern in (ORG_SUFFIX, ORG_GOV):
        for m in pattern.finditer(text):
            mention = m.group(0).rstrip(", ")
            found.append(Entity(mention, mention, "ORGANIZATION", None, 0.7, m.start(), m.start() + len(mention), priority=30))

    for m in _sector_regex().finditer(text):
        words = m.group(0).rsplit(" ", 1)[0]
        canonical = f"{words[:1].upper()}{words[1:].lower()} sector"
        found.append(Entity(m.group(0), canonical, "ORGANIZATION", "sector", 0.7, m.start(), m.end(), priority=25))

    return found


def _resolve_overlaps(entities: list[Entity]) -> list[Entity]:
    """Keep the best non-overlapping spans: higher priority first, then longer."""
    chosen: list[Entity] = []
    taken: list[tuple[int, int]] = []
    for e in sorted(entities, key=lambda e: (-e.priority, -(e.char_end - e.char_start), e.char_start)):
        if any(e.char_start < b and a < e.char_end for a, b in taken):
            continue
        chosen.append(e)
        taken.append((e.char_start, e.char_end))
    return sorted(chosen, key=lambda e: e.char_start)


def _add_coreferences(text: str, entities: list[Entity]) -> list[Entity]:
    """Very small coreference step: 'The group exploited ...' -> the last named threat actor (max ~600 chars back)."""
    out = list(entities)
    for m in COREFERENCE.finditer(text):
        if any(e.char_start < m.end() and m.start() < e.char_end for e in entities):
            continue
        prev = [e for e in entities if e.type == "THREAT_ACTOR" and e.char_end <= m.start() and m.start() - e.char_end < 600]
        if not prev:
            continue
        actor = prev[-1]
        out.append(Entity(m.group(0), actor.canonical_name, "THREAT_ACTOR", "coreference", round(actor.confidence * 0.75, 3),
                          m.start(), m.end(), attack_id=actor.attack_id))
    return sorted(out, key=lambda e: e.char_start)


def extract_entities(doc: PreparedDocument, model=None, min_conf: float = 0.5) -> list[Entity]:
    """Rules only, or hybrid when a trained model (pipeline.models.TransformerNER) is given.

    In hybrid mode, regex IOCs (priority >= 80) always win; model spans and name-list matches
    compete by length, and the name lists win ties because they come first.
    """
    candidates = _find_all(doc.text)
    if model is not None:
        candidates += model.extract(doc, min_conf)
    entities = _add_coreferences(doc.text, _resolve_overlaps(candidates))
    for e in entities:
        e.page_number = doc.page_at(e.char_start) if doc.page_spans else None
    return entities
