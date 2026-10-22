"""Hybrid (trained model + rules) extraction.

1. Stub models check the merge logic exactly.
2. Tiny, randomly initialised transformer models (built locally, no download) check that loading,
   tokenisation, inference and the contract output work end to end with real Hugging Face classes.
"""
import pytest

from pipeline.analyzer import analyze
from pipeline.ner import Entity, extract_entities
from pipeline.preprocess import prepare
from pipeline.relations import extract_relations


class StubNER:
    """Pretends the model found the given (mention, type, confidence) spans."""

    def __init__(self, spans):
        self.spans = spans

    def extract(self, doc, min_conf):
        out = []
        for mention, etype, conf in self.spans:
            i = doc.text.find(mention)
            if i >= 0 and conf >= min_conf:
                out.append(Entity(mention, mention, etype, None, conf, i, i + len(mention), priority=10))
        return out


class StubRE:
    def __init__(self, decide):
        self.decide = decide  # (subject_name, object_name) -> (label, prob)

    @staticmethod
    def marked(text, s, subj, obj):
        return (subj.canonical_name, obj.canonical_name)

    def classify(self, items):
        return [self.decide(*it) for it in items]


def test_model_adds_unknown_entities_but_regex_iocs_win():
    doc = prepare("Zorbix stole data from 10.1.2.3 using Mimikatz.")
    stub = StubNER([("Zorbix", "MALWARE", 0.9), ("10.1.2.3 using", "TOOL", 0.9), ("Mimikatz", "TOOL", 0.3)])
    ents = {(e.type, e.canonical_name) for e in extract_entities(doc, stub, 0.5)}
    assert ("MALWARE", "Zorbix") in ents  # not in any name list: only the model finds it
    assert ("OBSERVABLE", "10.1.2.3") in ents  # regex IOC beats the overlapping model span
    assert ("TOOL", "Mimikatz") in ents  # still found by the name list
    assert not any(n == "10.1.2.3 using" for _, n in ents)


def test_model_relations_merge_with_rules():
    text = "APT28 used Mimikatz. Mimikatz alongside APT29 tooling was seen."
    doc = prepare(text)
    ents = extract_entities(doc)

    def decide(s, o):
        if (s, o) == ("APT28", "Mimikatz"):
            return "USES", 0.9  # rules find this too -> confidence boosted
        if (s, o) == ("APT29", "Mimikatz"):
            return "USES", 0.8  # only the model finds this one
        return "NONE", 0.95

    rules_only = {(f.subject.canonical_name, f.relation, f.object.canonical_name): f.confidence
                  for f in extract_relations(doc, ents)}
    hybrid = {(f.subject.canonical_name, f.relation, f.object.canonical_name): f.confidence
              for f in extract_relations(doc, ents, StubRE(decide), 0.5)}
    assert ("APT29", "USES", "Mimikatz") in hybrid and ("APT29", "USES", "Mimikatz") not in rules_only
    assert hybrid[("APT28", "USES", "Mimikatz")] > rules_only[("APT28", "USES", "Mimikatz")]


def test_model_relations_respect_types_and_threshold():
    doc = prepare("APT28 used Mimikatz.")
    ents = extract_entities(doc)
    # a model saying "Mimikatz TARGETS APT28" (tool targets actor) violates the type rules -> dropped
    facts = extract_relations(doc, ents, StubRE(lambda s, o: ("TARGETS", 0.99)), 0.5)
    assert all(f.relation != "TARGETS" for f in facts)
    # below the probability threshold -> ignored, only the rule fact remains
    facts = extract_relations(doc, ents, StubRE(lambda s, o: ("EXPLOITS", 0.4)), 0.5)
    assert {(f.subject.canonical_name, f.relation) for f in facts} == {("APT28", "USES")}


def test_rules_win_overlaps_and_generic_words_are_dropped():
    """Fixes found on the demo documents with the real models."""
    from pipeline.models import _GENERIC

    doc = prepare("APT28 targeted government entities. The group exploited CVE-2023-23397.")
    # the model claims "government entities" (same span as the sector rule) -> the rule's canonical name wins
    stub = StubNER([("government entities", "ORGANIZATION", 0.95)])
    ents = extract_entities(doc, stub, 0.5)
    assert ("ORGANIZATION", "Government sector") in {(e.type, e.canonical_name) for e in ents}
    # "group" is not a name: the real model output is filtered, and coreference resolves "The group"
    assert _GENERIC.match("group") and _GENERIC.match("the threat actors") and not _GENERIC.match("Lazarus Group")
    facts = {(f.subject.canonical_name, f.relation, f.object.canonical_name) for f in extract_relations(doc, ents)}
    assert ("APT28", "EXPLOITS", "CVE-2023-23397") in facts


def test_actor_preferred_over_tool_as_subject_in_hybrid():
    doc = prepare("APT28 used Mimikatz to attack a ministry network in Poland.")
    stub = StubNER([("ministry", "ORGANIZATION", 0.9)])
    ents = extract_entities(doc, stub, 0.5)
    facts = extract_relations(doc, ents, StubRE(lambda s, o: ("TARGETS", 0.9) if o == "ministry" else ("NONE", 0.9)), 0.5)
    subjects = {f.subject.canonical_name for f in facts if f.relation == "TARGETS"}
    assert subjects == {"APT28"}


# ---------------------------------------------------------------- real HF classes, tiny random models
torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")


@pytest.fixture(scope="module")
def tiny_models(tmp_path_factory):
    from transformers import (BertConfig, BertForSequenceClassification, BertForTokenClassification,
                              BertTokenizerFast)

    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "training"))
    from common import NER_LABELS, RE_LABELS

    root = tmp_path_factory.mktemp("tiny")
    words = "apt28 used mimikatz to target the energy sector cve 2023 23397 . , exploited zorbix".split()
    vocab = ["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]", "[E1]", "[/E1]", "[E2]", "[/E2]", *words]
    vocab += list("abcdefghijklmnopqrstuvwxyz0123456789") + ["##" + c for c in "abcdefghijklmnopqrstuvwxyz0123456789"]
    (root / "vocab.txt").write_text("\n".join(dict.fromkeys(vocab)))
    torch.manual_seed(0)
    paths = {}
    for kind, cls, labels in (("ner", BertForTokenClassification, NER_LABELS),
                              ("re", BertForSequenceClassification, RE_LABELS)):
        d = root / kind
        tok = BertTokenizerFast(str(root / "vocab.txt"))
        tok.save_pretrained(d)
        cfg = BertConfig(vocab_size=len(tok), hidden_size=32, num_hidden_layers=1, num_attention_heads=2,
                         intermediate_size=64, num_labels=len(labels),
                         id2label=dict(enumerate(labels)), label2id={l: i for i, l in enumerate(labels)})
        cls(cfg).save_pretrained(d)
        paths[kind] = str(d)
    return paths


def test_real_transformer_classes_end_to_end(tiny_models, contract):
    from pipeline.models import TransformerNER, TransformerRE

    ner, re_model = TransformerNER(tiny_models["ner"]), TransformerRE(tiny_models["re"])
    doc = prepare("APT28 used Mimikatz to target the energy sector. They exploited CVE-2023-23397.")
    ents = extract_entities(doc, ner, 0.0)
    for e in ents:
        assert doc.text[e.char_start:e.char_end] == e.mention
    facts = extract_relations(doc, ents, re_model, 0.0)
    assert all(f.relation in ("USES", "DEPLOYS", "EXPLOITS", "TARGETS", "ATTRIBUTED_TO") for f in facts)


def test_analyze_with_models_matches_contract(tiny_models, contract, monkeypatch):
    import pipeline.analyzer as analyzer

    monkeypatch.setattr(analyzer, "NER_MODEL", tiny_models["ner"])
    monkeypatch.setattr(analyzer, "RE_MODEL", tiny_models["re"])
    monkeypatch.setattr(analyzer, "NER_MIN_CONFIDENCE", 0.0)
    out = analyze("d", "s", "APT28 used Mimikatz to target the energy sector.")
    errors = [e.message for e in contract("analyze_response").iter_errors(out)]
    assert not errors, errors
    assert tiny_models["ner"] in out["processing"]["model_version"]
