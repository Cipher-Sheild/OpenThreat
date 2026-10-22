"""Temporal expression extraction (rule-based).

Finds dates in a sentence, decides what kind of event they describe from cue words
(first seen, disclosed, patched, active, retired) and links them to the nearest suitable entity.
Times are ISO 8601, possibly partial: "2024", "2024-03", "2024-03-15".
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from pipeline.ner import Entity
from pipeline.preprocess import PreparedDocument, Sentence

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10,
    "nov": 11, "dec": 12,
}
_MONTH_RE = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?"
_YEAR = r"(?:19[89]\d|20[0-4]\d)"

DATE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(" + _YEAR + r")-(\d{2})-(\d{2})\b"), "iso"),
    (re.compile(r"\b(\d{1,2})\s+(" + _MONTH_RE + r")\s+(" + _YEAR + r")\b"), "dmy"),
    (re.compile(r"\b(" + _MONTH_RE + r")\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(" + _YEAR + r")\b"), "mdy"),
    (re.compile(r"\b(" + _MONTH_RE + r")\s+(?:of\s+)?(" + _YEAR + r")\b"), "my"),
    (re.compile(r"\bQ([1-4])\s+(" + _YEAR + r")\b"), "q"),
    (re.compile(r"\b(?:(?:early|mid|late)[- ])?(" + _YEAR + r")\b"), "y"),
]

# (type, cue regex, preferred entity types) — checked in this order
CUES: list[tuple[str, re.Pattern, tuple[str, ...]]] = [
    ("PATCHED", re.compile(r"\b(?:patch\w*|fix(?:ed|es)?|remediat\w*|security update|addressed|mitigated)\b", re.I), ("VULNERABILITY",)),
    ("RETIRED", re.compile(r"\b(?:retired|shut\s+down|taken\s+down|dismantled|disrupted|ceased|discontinued|went\s+offline|seized|disbanded|no longer active)\b", re.I), ("MALWARE", "THREAT_ACTOR", "TOOL", "OBSERVABLE")),
    ("FIRST_SEEN", re.compile(r"\b(?:first\s+(?:seen|observed|detected|spotted|identified|discovered|reported)|emerged|surfaced|appeared)\b", re.I), ("MALWARE", "THREAT_ACTOR", "TOOL", "VULNERABILITY", "OBSERVABLE")),
    ("ACTIVE", re.compile(r"\b(?:active\s+(?:since|in|during|from|until)|operating\s+since|has\s+been\s+active|operational\s+since|since)\b", re.I), ("THREAT_ACTOR", "MALWARE", "TOOL")),
    ("DISCLOSED", re.compile(r"\b(?:disclos\w*|publish\w*|reported|announc\w*|reveal\w*|assigned|advisory|warned)\b", re.I), ("VULNERABILITY", "MALWARE", "THREAT_ACTOR")),
]


@dataclass
class TemporalEvent:
    event: str
    entity: str
    time: str
    type: str
    confidence: float
    sentence: Sentence


def _parse(m: re.Match, kind: str) -> tuple[str, bool]:
    """-> (iso string, is_precise)"""
    g = m.groups()
    if kind == "iso":
        return f"{g[0]}-{g[1]}-{g[2]}", True
    if kind == "dmy":
        return f"{g[2]}-{_MONTHS[g[1][:3].lower()]:02d}-{int(g[0]):02d}", True
    if kind == "mdy":
        return f"{g[2]}-{_MONTHS[g[0][:3].lower()]:02d}-{int(g[1]):02d}", True
    if kind == "my":
        return f"{g[1]}-{_MONTHS[g[0][:3].lower()]:02d}", True
    if kind == "q":
        return f"{g[1]}-{(int(g[0]) - 1) * 3 + 1:02d}", False
    return g[0], False


_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
        "ten": 10, "eleven": 11, "twelve": 12, "a": 1, "an": 1}
RELATIVE = re.compile(
    r"\b(?:(?:earlier|later|early|late)\s+)?(?P<this>this|last|past|previous)\s+(?P<unit>year|month|week)\b"
    r"|\b(?P<n>\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|a|an)\s+(?P<unit2>days?|weeks?|months?|years?)\s+ago\b"
    r"|\b(?P<day>yesterday|today)\b",
    re.I,
)


def _shift(ref: date, years: int = 0, months: int = 0, days: int = 0) -> date:
    y, m = ref.year + years, ref.month + months
    while m < 1:
        y, m = y - 1, m + 12
    while m > 12:
        y, m = y + 1, m - 12
    d = min(ref.day, 28)
    return date(y, m, d) - timedelta(days=days)


def _relative(m: re.Match, ref: date) -> tuple[str, bool]:
    if m.group("day"):
        d = ref - timedelta(days=1) if m.group("day").lower() == "yesterday" else ref
        return d.isoformat(), True
    if m.group("this"):
        back = 0 if m.group("this").lower() == "this" else 1
        unit = m.group("unit").lower()
        if unit == "year":
            return str(ref.year - back), False
        if unit == "month":
            d = _shift(ref, months=-back)
            return f"{d.year}-{d.month:02d}", True
        d = ref - timedelta(weeks=back)
        return d.isoformat(), False
    n = _NUM.get(m.group("n").lower()) or int(m.group("n"))
    unit = m.group("unit2").lower().rstrip("s")
    if unit == "year":
        return str(ref.year - n), False
    if unit == "month":
        d = _shift(ref, months=-n)
        return f"{d.year}-{d.month:02d}", True
    d = ref - timedelta(days=n * (7 if unit == "week" else 1))
    return d.isoformat(), unit == "day"


def _dates(sentence_text: str, ref: date | None = None) -> list[tuple[int, int, str, bool]]:
    found: list[tuple[int, int, str, bool]] = []
    for pattern, kind in DATE_PATTERNS:
        for m in pattern.finditer(sentence_text):
            if any(m.start() < b and a < m.end() for a, b, _, _ in found):
                continue
            # skip years that are part of IDs like CVE-2024-1234
            before = sentence_text[max(0, m.start() - 4):m.start()]
            if kind == "y" and re.search(r"[-‐–]$|CVE.?$", before, re.I):
                continue
            iso, precise = _parse(m, kind)
            found.append((m.start(), m.end(), iso, precise))
    if ref is not None:  # relative expressions need the document's publication date
        for m in RELATIVE.finditer(sentence_text):
            if any(m.start() < b and a < m.end() for a, b, _, _ in found):
                continue
            iso, precise = _relative(m, ref)
            found.append((m.start(), m.end(), iso, precise))
    return sorted(found)


def _cue_for(sentence_text: str, d_start: int, d_end: int):
    """The cue word closest to this date (so 'disclosed in Jan and patched in March' gets both right)."""
    best = None
    for order, (t, cue, pref) in enumerate(CUES):
        for cm in cue.finditer(sentence_text):
            if cm.end() <= d_start:
                side, dist = 0, d_start - cm.end()
            elif cm.start() >= d_end:
                side, dist = 1, cm.start() - d_end  # cue after the date ("In March 2024, Microsoft patched")
            else:
                side, dist = 0, 0
            if dist > 80:
                continue
            key = (side, dist, order)  # a cue before the date always wins over one after it
            if best is None or key < best[0]:
                best = (key, t, cm.group(0), pref)
    return best


def extract_temporal(doc: PreparedDocument, entities: list[Entity], published_at: str | None = None) -> list[TemporalEvent]:
    ref = None
    if published_at:
        try:
            ref = datetime.fromisoformat(published_at.replace("Z", "+00:00")).date()
        except ValueError:
            ref = None
    events: list[TemporalEvent] = []
    seen: set[tuple[str, str, str]] = set()
    for s in doc.sentences:
        ents = [e for e in entities if s.start <= e.char_start and e.char_end <= s.end and e.type != "TECHNIQUE"]
        if not ents:
            continue
        dates = _dates(s.text, ref)
        for i, (d_start, d_end, iso, precise) in enumerate(dates):
            # entity mentions that contain the date (e.g. CVE IDs) are not dates
            abs_start = s.start + d_start
            if any(e.char_start <= abs_start < e.char_end for e in ents):
                continue
            etype, cue_text, preferred = "OBSERVED", None, ("THREAT_ACTOR", "MALWARE", "TOOL", "VULNERABILITY")
            cue = _cue_for(s.text, d_start, d_end)
            if cue:
                # ignore a cue that sits on the far side of another date
                other = [d for j, d in enumerate(dates) if j != i]
                cue_pos = s.text.find(cue[2])
                blocked = any(min(cue_pos, d_start) < o[0] < max(cue_pos, d_start) for o in other)
                if not blocked:
                    _, etype, cue_text, preferred = cue
            candidates = [e for e in ents if e.type in preferred] or ents
            # preferred type first (e.g. the vulnerability for PATCHED, the actor for ACTIVE), then nearest
            target = min(candidates, key=lambda e: (preferred.index(e.type) if e.type in preferred else 99,
                                                    abs(e.char_start - abs_start)))
            key = (target.canonical_name, iso, etype)
            if key in seen:
                continue
            seen.add(key)
            conf = (0.8 if precise else 0.65) if cue_text else 0.45
            events.append(TemporalEvent(
                event=(cue_text or "mentioned") + " " + s.text[d_start:d_end],
                entity=target.canonical_name, time=iso, type=etype, confidence=conf, sentence=s,
            ))
    return events
