"""Phase 3: trained transformer models for NER and relation extraction.

Used in "hybrid" mode together with the rules:
  * NER: the model finds entities (good recall on names it has never seen); regex keeps IOCs exact
    (CVE IDs, IPs, hashes, defanged domains); the ATT&CK/alias lists give canonical names.
  * RE: the model classifies every plausible entity pair in a sentence; rule-based facts are kept
    too, and a fact found by both gets a higher confidence.
Models are loaded once, from a Hugging Face repo id or a local folder (NER_MODEL / RE_MODEL).
"""
from __future__ import annotations

import re
import threading

import numpy as np

from pipeline.gazetteer import get_gazetteer
from pipeline.ner import Entity
from pipeline.preprocess import PreparedDocument, Sentence, refang

# Word tokenisation close to CyberNER's (punctuation split off), but IOCs kept whole
_WORD = re.compile(r"(?:https?|hxxps?)://\S+|\w+(?:[-.@/:\\]\w+)*|[^\w\s]")
_WINDOW = 100
MARKERS = ["[E1]", "[/E1]", "[E2]", "[/E2]"]
# Generic nouns the model sometimes tags as names; "the group" is resolved by the coreference rule instead
_GENERIC = re.compile(
    r"^(?:the\s+|this\s+|these\s+|a\s+|an\s+)?(?:threat\s+)?(?:group|groups|actor|actors|attacker|attackers|"
    r"adversary|adversaries|operators?|hackers?|malware|backdoor|tool|tools|ransomware|campaign|victims?|"
    r"organi[sz]ations?|company|companies|researchers?|vendor|vendors)$",
    re.I,
)


def _load(kind: str, name: str):
    import torch  # noqa: F401  (fail early with a clear error if torch is missing)
    from transformers import AutoModelForSequenceClassification, AutoModelForTokenClassification, AutoTokenizer

    kwargs = {}
    tok_probe = AutoTokenizer.from_pretrained(name)
    if getattr(tok_probe, "add_prefix_space", None) is not None or "roberta" in type(tok_probe).__name__.lower():
        kwargs["add_prefix_space"] = True
    tokenizer = AutoTokenizer.from_pretrained(name, **kwargs) if kwargs else tok_probe
    cls = AutoModelForTokenClassification if kind == "ner" else AutoModelForSequenceClassification
    model = cls.from_pretrained(name)
    model.eval()
    return tokenizer, model


class TransformerNER:
    def __init__(self, name: str):
        self.name = name
        self.tokenizer, self.model = _load("ner", name)
        self.id2label = self.model.config.id2label
        self._lock = threading.Lock()

    def _predict_words(self, words: list[str]) -> list[tuple[str, float]]:
        import torch

        out: list[tuple[str, float]] = []
        for i in range(0, len(words), _WINDOW):
            chunk = words[i:i + _WINDOW]
            enc = self.tokenizer(chunk, is_split_into_words=True, truncation=True, max_length=512, return_tensors="pt")
            with self._lock, torch.no_grad():
                probs = torch.softmax(self.model(**enc).logits[0], dim=-1).numpy()
            labels = [("O", 1.0)] * len(chunk)
            seen = set()
            for pos, wid in enumerate(enc.word_ids()):
                if wid is None or wid in seen:
                    continue
                seen.add(wid)
                k = int(np.argmax(probs[pos]))
                labels[wid] = (self.id2label[k], float(probs[pos][k]))
            out.extend(labels)
        return out

    def extract(self, doc: PreparedDocument, min_conf: float) -> list[Entity]:
        gz = get_gazetteer()
        entities: list[Entity] = []
        for s in doc.sentences:
            words = [(m.group(0), s.start + m.start(), s.start + m.end()) for m in _WORD.finditer(s.text)]
            if not words:
                continue
            labels = self._predict_words([w for w, _, _ in words])
            span = None  # [type, start_idx, end_idx, [probs]]
            for i, (lab, p) in enumerate([*labels, ("O", 1.0)]):
                starts_new = lab.startswith("B-") or (lab.startswith("I-") and (span is None or span[0] != lab[2:]))
                if span is not None and (lab == "O" or starts_new):
                    entities.append(self._make(doc, words, span, gz))
                    span = None
                if lab != "O" and starts_new:
                    span = [lab[2:], i, i + 1, [p]]
                elif lab.startswith("I-") and span is not None:
                    span[2] = i + 1
                    span[3].append(p)
        return [e for e in entities if e.confidence >= min_conf and not _GENERIC.match(e.mention)]

    @staticmethod
    def _make(doc, words, span, gz) -> Entity:
        etype, a, b, probs = span
        start, end = words[a][1], words[b - 1][2]
        mention = doc.text[start:end]
        canonical, attack_id = mention, None
        if etype == "OBSERVABLE":
            canonical = refang(mention).lower() if not re.match(r"https?|hxxp", mention, re.I) else refang(mention)
        else:
            entry = gz.lookup(mention, etype)
            if entry is None and etype in ("MALWARE", "TOOL"):
                entry = gz.lookup(mention)
                entry = entry if entry and entry.type in ("MALWARE", "TOOL") else None
            if entry is not None:
                canonical, attack_id = entry.canonical, entry.attack_id
                if etype != entry.type and {etype, entry.type} <= {"MALWARE", "TOOL"}:
                    etype = entry.type  # trust the curated list for malware-vs-tool
            if etype == "VULNERABILITY" and re.match(r"cve", mention, re.I):
                canonical = mention.upper()
            if etype == "TECHNIQUE":
                tid = gz.technique_names.get(mention.casefold())
                if tid:
                    canonical, attack_id = tid, tid
        conf = round(float(np.mean(probs)), 3)
        return Entity(mention, canonical, etype, None, conf, start, end, attack_id=attack_id,
                      priority=10, page_number=None)  # below every rule: rules win overlaps, model fills gaps


class TransformerRE:
    def __init__(self, name: str):
        self.name = name
        self.tokenizer, self.model = _load("re", name)
        self.id2label = self.model.config.id2label
        self._lock = threading.Lock()

    @staticmethod
    def marked(text: str, s: Sentence, subj: Entity, obj: Entity) -> str:
        sent = text[s.start:s.end]
        spans = sorted([(subj, "[E1]", "[/E1]"), (obj, "[E2]", "[/E2]")], key=lambda x: x[0].char_start, reverse=True)
        for e, open_, close in spans:
            a, b = e.char_start - s.start, e.char_end - s.start
            sent = sent[:a] + f"{open_} {sent[a:b]} {close}" + sent[b:]
        return sent

    def classify(self, texts: list[str]) -> list[tuple[str, float]]:
        import torch

        out = []
        for i in range(0, len(texts), 32):
            enc = self.tokenizer(texts[i:i + 32], truncation=True, max_length=256, padding=True, return_tensors="pt")
            with self._lock, torch.no_grad():
                probs = torch.softmax(self.model(**enc).logits, dim=-1).numpy()
            for row in probs:
                k = int(np.argmax(row))
                out.append((self.id2label[k], float(row[k])))
        return out


_ner = _re = None
_load_lock = threading.Lock()


def get_ner_model(name: str) -> TransformerNER | None:
    global _ner
    if not name:
        return None
    with _load_lock:
        if _ner is None or _ner.name != name:
            _ner = TransformerNER(name)
    return _ner


def get_re_model(name: str) -> TransformerRE | None:
    global _re
    if not name:
        return None
    with _load_lock:
        if _re is None or _re.name != name:
            _re = TransformerRE(name)
    return _re
