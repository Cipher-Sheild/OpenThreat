"""IOC-safe preprocessing.

The analyzed text is NEVER rewritten: every offset we return points into exactly the text
Member 2 sent (or, for PDFs, the pages joined with "\\n\\n"). IOCs like CVE IDs, IPs, hashes and
(defanged) domains are therefore never stripped or altered; extractors read them in place.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

PAGE_SEPARATOR = "\n\n"


@dataclass
class Sentence:
    index: int
    start: int
    end: int
    text: str
    page_number: int | None


@dataclass
class PreparedDocument:
    text: str
    sentences: list[Sentence]
    page_spans: list[tuple[int, int, int]]  # (page_number, start, end)

    def page_at(self, offset: int) -> int | None:
        for page, start, end in self.page_spans:
            if start <= offset < end or (offset == end and start == end):
                return page
        return None


_ABBREVIATIONS = {
    "e.g", "i.e", "etc", "vs", "inc", "ltd", "corp", "co", "mr", "mrs", "dr", "u.s", "u.k",
    "no", "fig", "al", "approx", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept",
    "oct", "nov", "dec", "st", "jr", "sr", "v", "ver",
}

# Candidate boundary: ., ! or ? (optionally followed by a closing quote/bracket) then whitespace
_BOUNDARY = re.compile(r"[.!?][\"')\]]*\s+")
_PARAGRAPH = re.compile(r"\n\s*\n|\n(?=\s*(?:[-*•▪]|\d+[.)])\s)")


def join_pages(pages: list[tuple[int, str]]) -> tuple[str, list[tuple[int, int, int]]]:
    parts, spans, pos = [], [], 0
    for i, (page_number, page_text) in enumerate(pages):
        if i:
            parts.append(PAGE_SEPARATOR)
            pos += len(PAGE_SEPARATOR)
        parts.append(page_text)
        spans.append((page_number, pos, pos + len(page_text)))
        pos += len(page_text)
    return "".join(parts), spans


def _is_real_boundary(text: str, dot_pos: int, next_pos: int) -> bool:
    if text[dot_pos] != ".":
        return True
    # word before the dot
    m = re.search(r"([A-Za-z.]+)$", text[max(0, dot_pos - 12):dot_pos])
    if m and m.group(1).lower().rstrip(".") in _ABBREVIATIONS:
        return False
    # single capital initial ("J. Smith")
    if m and len(m.group(1)) == 1 and m.group(1).isupper():
        return False
    # next sentence should start with an uppercase letter, digit, quote or bracket
    nxt = text[next_pos:next_pos + 1]
    return bool(nxt) and (nxt.isupper() or nxt.isdigit() or nxt in "\"'([“")


def split_sentences(text: str, page_spans: list[tuple[int, int, int]] | None = None) -> list[Sentence]:
    cut_points = {0, len(text)}
    for m in _PARAGRAPH.finditer(text):
        cut_points.add(m.end())
    for m in _BOUNDARY.finditer(text):
        if _is_real_boundary(text, m.start(), m.end()):
            cut_points.add(m.end())
    if page_spans:
        for _, start, end in page_spans:
            cut_points.update((start, end))

    doc = PreparedDocument(text, [], page_spans or [])
    sentences: list[Sentence] = []
    cuts = sorted(cut_points)
    for a, b in zip(cuts, cuts[1:]):
        seg = text[a:b]
        lstrip = len(seg) - len(seg.lstrip())
        rstrip = len(seg) - len(seg.rstrip())
        start, end = a + lstrip, b - rstrip
        if end <= start:
            continue
        sentences.append(
            Sentence(len(sentences), start, end, text[start:end], doc.page_at(start) if page_spans else None)
        )
    return sentences


def prepare(text: str | None = None, pages: list[tuple[int, str]] | None = None) -> PreparedDocument:
    if pages:
        full, spans = join_pages(pages)
    else:
        full, spans = text or "", []
    return PreparedDocument(full, split_sentences(full, spans), spans)


_REFANG = [
    (re.compile(r"h[xX]{2}p(s?)", re.I), r"http\1"),
    (re.compile(r"\[\.\]|\(\.\)|\{\.\}|\[dot\]|\(dot\)", re.I), "."),
    (re.compile(r"\[:\]"), ":"),
    (re.compile(r"\[@\]|\[at\]|\(at\)", re.I), "@"),
]


def refang(value: str) -> str:
    """Turn a defanged IOC (hxxp://evil[.]com) into its real form, for canonical names only."""
    for pattern, repl in _REFANG:
        value = pattern.sub(repl, value)
    return value
