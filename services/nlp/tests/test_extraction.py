"""NER, relation, behaviour and temporal extraction (rule-based Phase 2 pipeline)."""
import pytest

from pipeline.analyzer import analyze
from pipeline.ner import extract_entities
from pipeline.preprocess import prepare, split_sentences


def ents(text):
    return {(e.type, e.canonical_name) for e in extract_entities(prepare(text))}


def rels(text):
    r = analyze("t", "test", text)["relations"]
    return {(x["subject"], x["relation"], x["object"], x["negated"]) for x in r}


# ---------- preprocessing ----------
def test_sentence_split_keeps_iocs_and_abbreviations():
    text = "The U.S. Department of Justice seized evil[.]com. APT28 used 10.0.0.1, e.g. for C2. Next."
    sents = [s.text for s in split_sentences(text)]
    assert sents == [
        "The U.S. Department of Justice seized evil[.]com.",
        "APT28 used 10.0.0.1, e.g. for C2.",
        "Next.",
    ]


def test_offsets_point_into_original_text():
    text = "Intro.\n\nAPT28 used hxxp://bad[.]example[.]com/x and CVE-2024-3400."
    doc = prepare(text)
    for e in extract_entities(doc):
        assert text[e.char_start:e.char_end] == e.mention


# ---------- NER ----------
def test_iocs_including_defanged():
    found = ents(
        "C2 at 185.220.101[.]4 and update-check[.]com via hxxps://update-check[.]com/a.php "
        "hash 44d88612fea8a8f36de82e1278abb02f and e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 "
        "exploiting cve-2024-3400 and T1059.001"
    )
    assert ("OBSERVABLE", "185.220.101.4") in found
    assert ("OBSERVABLE", "update-check.com") in found
    assert ("OBSERVABLE", "https://update-check.com/a.php") in found
    assert ("OBSERVABLE", "44d88612fea8a8f36de82e1278abb02f") in found
    assert ("OBSERVABLE", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855") in found
    assert ("VULNERABILITY", "CVE-2024-3400") in found
    assert ("TECHNIQUE", "T1059.001") in found


def test_aliases_map_to_canonical_names():
    found = ents("Fancy Bear and Cozy Bear were joined by Hidden Cobra.")
    assert ("THREAT_ACTOR", "APT28") in found
    assert ("THREAT_ACTOR", "APT29") in found
    assert ("THREAT_ACTOR", "Lazarus Group") in found


def test_context_decides_malware_vs_actor():
    assert ("MALWARE", "Uroburos") in ents("The Snake implant was found on the server.")
    assert ("THREAT_ACTOR", "Turla") in ents("The Snake group returned in 2023.")


def test_unknown_malware_introduced_by_kind():
    assert ("MALWARE", "HeadLace") in ents("The group deployed HeadLace, a backdoor written in Python.")


def test_common_words_are_not_entities():
    found = ents("At the page you can play the net game and ping the route.")
    assert found == set()


def test_version_numbers_are_not_ips():
    assert ("OBSERVABLE", "10.0.0.1") not in ents("Upgrade to version 10.0.0.1 now.")


def test_coreference_the_group():
    doc = prepare("APT28 is active. The group exploited CVE-2023-23397.")
    coref = [e for e in extract_entities(doc) if e.subtype == "coreference"]
    assert coref and coref[0].canonical_name == "APT28"


# ---------- relations ----------
@pytest.mark.parametrize(
    "text,expected",
    [
        ("APT28 used Mimikatz.", ("APT28", "USES", "Mimikatz", False)),
        ("Mimikatz was used by APT28.", ("APT28", "USES", "Mimikatz", False)),
        ("Lazarus Group deployed AppleJeus.", ("Lazarus Group", "DEPLOYS", "AppleJeus", False)),
        ("FIN7 exploited CVE-2021-44228.", ("FIN7", "EXPLOITS", "CVE-2021-44228", False)),
        ("FIN7 leveraged CVE-2021-44228.", ("FIN7", "EXPLOITS", "CVE-2021-44228", False)),
        ("APT28 targeted the energy sector.", ("APT28", "TARGETS", "Energy sector", False)),
        ("The Snake implant is attributed to Turla.", ("Uroburos", "ATTRIBUTED_TO", "Turla", False)),
        ("Researchers attribute the Snake implant to APT29.", ("Uroburos", "ATTRIBUTED_TO", "APT29", False)),
        ("Sandworm Team is behind NotPetya.", ("NotPetya", "ATTRIBUTED_TO", "Sandworm Team", False)),
        ("APT29 no longer uses WellMess.", ("APT29", "USES", "WellMess", True)),
        ("There is no evidence that Turla used Mimikatz.", ("Turla", "USES", "Mimikatz", True)),
    ],
)
def test_relation_patterns(text, expected):
    assert expected in rels(text)


def test_coordinated_subjects_and_objects():
    r = rels("APT41 and APT28 used PlugX and Mimikatz.")
    for s in ("APT41", "APT28"):
        for o in ("PlugX", "Mimikatz"):
            assert (s, "USES", o, False) in r


def test_no_cross_clause_relations():
    r = rels("APT28 used Mimikatz and APT29 deployed SUNBURST.")
    assert ("APT28", "DEPLOYS", "SUNBURST", False) not in r
    assert ("APT29", "DEPLOYS", "SUNBURST", False) in r
    r = rels("APT28 used Mimikatz, while APT29 used SUNBURST.")
    assert ("APT28", "USES", "SUNBURST", False) not in r


def test_actor_is_subject_of_purpose_clause():
    r = rels("APT28, also known as Fancy Bear, used Mimikatz and Cobalt Strike to target the energy sector.")
    assert ("APT28", "TARGETS", "Energy sector", False) in r
    assert not any(s == "Mimikatz" and rel == "TARGETS" for s, rel, _, _ in r)


def test_every_relation_has_evidence_inside_the_text():
    text = (open(__file__.replace("test_extraction.py", "fixtures/doc1_jan2024.txt"), encoding="utf-8").read())
    for r in analyze("d", "s", text)["relations"]:
        ev = r["evidence"]
        assert text[ev["char_start"]:ev["char_end"]] == ev["text"]
        assert 0 < r["confidence"] <= 1


# ---------- behaviours & temporal ----------
def test_behaviors_map_to_attack():
    out = analyze("t", "s", "They used T1566.001 lures. Kerberoasting was also seen.")["behaviors"]
    ids = {b["mitre_attack_id"] for b in out}
    assert {"T1566.001", "T1558.003"} <= ids
    assert all(b["evidence"]["text"] for b in out)


def test_temporal_events():
    out = analyze(
        "t", "s",
        "Microsoft patched CVE-2023-23397 in March 2023. HeadLace, a backdoor, was first observed on 5 September 2023. "
        "APT28 has been active since 2004.",
    )["temporal_events"]
    got = {(t["entity"], t["type"], t["time"]) for t in out}
    assert ("CVE-2023-23397", "PATCHED", "2023-03") in got
    assert ("HeadLace", "FIRST_SEEN", "2023-09-05") in got
    assert ("APT28", "ACTIVE", "2004") in got
    # the year inside a CVE ID is not a date
    assert not any(t["time"] == "2023" and t["entity"] == "CVE-2023-23397" for t in out)
