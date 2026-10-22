"""Phase 4: semantic ATT&CK mapping and relative / multi-date temporal extraction."""
from pipeline.analyzer import analyze
from pipeline.attack_mapper import AttackMapper
from pipeline.behaviors import extract_behaviors
from pipeline.ner import extract_entities
from pipeline.preprocess import prepare


def test_mapper_ranks_techniques(tmp_path):
    m = AttackMapper(cache_dir=str(tmp_path))
    best = m.best(["The malware dumped credentials from LSASS memory.",
                   "The actor downloaded additional payloads to the host."])
    assert best[0].technique_id.startswith("T1003")
    assert best[1].technique_id == "T1105"
    # cached anchors are reused
    assert list(tmp_path.glob("attack_anchors_*.npy"))


def test_semantic_behaviors_only_above_threshold(tmp_path):
    m = AttackMapper(cache_dir=str(tmp_path))
    doc = prepare("APT28 dumped passwords from the memory of the authentication process. The weather was nice today.")
    ents = extract_entities(doc)
    got = extract_behaviors(doc, ents, m, min_similarity=0.3)
    # mechanics only (mapping quality is measured by evaluation/eval_attack.py with the real model)
    assert any(b.mitre_attack_id and "APT28" in b.description for b in got)
    assert not any("weather" in b.description for b in got)
    assert extract_behaviors(doc, ents, m, min_similarity=0.999) == []


def test_explicit_id_wins_over_semantic(tmp_path):
    m = AttackMapper(cache_dir=str(tmp_path))
    doc = prepare("APT28 used T1059.001 to dump passwords from process memory.")
    got = extract_behaviors(doc, extract_entities(doc), m, min_similarity=0.0)
    assert [b.mitre_attack_id for b in got] == ["T1059.001"]


def _events(text, pub="2024-06-20T00:00:00Z"):
    return {(e["entity"], e["type"], e["time"]) for e in analyze("t", "s", text, published_at=pub)["temporal_events"]}


def test_relative_dates_use_publication_date():
    assert ("LockBit", "RETIRED", "2024-05") in _events("LockBit was taken down last month.")
    assert ("APT29", "FIRST_SEEN", "2024-03") in _events("APT29 was first observed three months ago.")
    assert ("Emotet", "RETIRED", "2024") in _events("The Emotet botnet was disrupted earlier this year.")
    # without a publication date, relative expressions are not guessed
    assert _events("LockBit was taken down last month.", pub=None) == set()


def test_each_date_gets_its_own_cue():
    ev = _events("Microsoft disclosed CVE-2024-21412 in January 2024 and patched CVE-2024-21412 in March 2024.")
    assert ("CVE-2024-21412", "DISCLOSED", "2024-01") in ev
    assert ("CVE-2024-21412", "PATCHED", "2024-03") in ev
    assert ("CVE-2024-21412", "PATCHED", "2024-03") in _events("In March 2024, Microsoft patched CVE-2024-21412.")
