"""Entity resolution and the novelty labelling policy (all five labels)."""
from pipeline.novelty import Candidate, Fact, classify_one
from pipeline.resolution import KnownEntity, resolve

KNOWN = [
    KnownEntity("e1", "APT28", "THREAT_ACTOR", ["Sofacy"]),
    KnownEntity("e2", "Cobalt Strike", "TOOL", []),
    KnownEntity("e3", "CVE-2023-23397", "VULNERABILITY", []),
    KnownEntity("e4", "APT29", "THREAT_ACTOR", []),
]


# ---------- resolution ----------
def test_resolution_steps():
    assert resolve("apt 28", "THREAT_ACTOR", KNOWN).method == "exact"
    r = resolve("Sofacy", "THREAT_ACTOR", KNOWN)
    assert (r.entity_id, r.method) == ("e1", "alias")
    r = resolve("Fancy Bear", "THREAT_ACTOR", KNOWN)  # not stored in DB, known from ATT&CK
    assert (r.entity_id, r.method, r.new_aliases) == ("e1", "builtin_alias", ["Fancy Bear"])
    r = resolve("Cobalt Strik", "TOOL", KNOWN)
    assert (r.entity_id, r.method) == ("e2", "string_similarity")


def test_resolution_never_merges_different_numbers_or_types():
    assert resolve("APT27", "THREAT_ACTOR", KNOWN).entity_id is None
    assert resolve("CVE-2023-23398", "VULNERABILITY", KNOWN).entity_id is None
    assert resolve("Cobalt Strike", "THREAT_ACTOR", KNOWN).entity_id is None  # type filter


def test_unmatched_mention_gets_builtin_canonical_name():
    r = resolve("Cozy Bear", "THREAT_ACTOR", [KNOWN[0]])
    assert r.entity_id is None and r.canonical_name == "APT29"


# ---------- novelty ----------
def cand(fid, s, rel, o, status="ACTIVE", negated=False, seen="2024-01-15T00:00:00Z", **kw):
    return Candidate(fid, s, rel, o, status, negated, first_seen_at=seen, last_seen_at=seen, **kw)


def fact(s, rel, o, conf=0.8, negated=False, text=""):
    return Fact(s, rel, o, conf, negated, evidence={"text": text})


NEWER, OLDER = "2024-06-20T00:00:00Z", "2023-06-01T00:00:00Z"


def test_new_when_nothing_on_record():
    r = classify_one(fact("APT28", "USES", "Mimikatz"), [cand("f1", "APT29", "USES", "Mimikatz")], NEWER)
    assert r.status == "NEW"


def test_known_same_fact_via_alias():
    r = classify_one(fact("Fancy Bear", "USES", "Mimikatz"), [cand("f1", "APT28", "USES", "Mimikatz")], NEWER)
    assert (r.status, r.matched_fact_id) == ("KNOWN", "f1")


def test_multi_valued_relation_new_object_is_new_not_updated():
    r = classify_one(fact("APT28", "USES", "Cobalt Strike"), [cand("f1", "APT28", "USES", "Mimikatz")], NEWER)
    assert r.status == "NEW" and r.superseded_fact_ids == []


def test_single_valued_newer_source_is_updated():
    r = classify_one(fact("Uroburos", "ATTRIBUTED_TO", "APT29"), [cand("f1", "Uroburos", "ATTRIBUTED_TO", "Turla")], NEWER)
    assert (r.status, r.superseded_fact_ids) == ("UPDATED", ["f1"])


def test_single_valued_explicit_revision_is_updated_even_without_dates():
    f = fact("Uroburos", "ATTRIBUTED_TO", "APT29", text="Researchers now attribute the Snake implant to APT29.")
    assert classify_one(f, [cand("f1", "Uroburos", "ATTRIBUTED_TO", "Turla", seen=None)], None).status == "UPDATED"


def test_single_valued_older_or_undated_disagreement_is_conflicting():
    c = [cand("f1", "Uroburos", "ATTRIBUTED_TO", "Turla")]
    r = classify_one(fact("Uroburos", "ATTRIBUTED_TO", "APT29"), c, OLDER)
    assert (r.status, r.conflicting_fact_ids) == ("CONFLICTING", ["f1"])
    assert classify_one(fact("Uroburos", "ATTRIBUTED_TO", "APT29"), c, None).status == "CONFLICTING"


def test_no_longer_uses_is_updated():
    f = fact("APT29", "USES", "WellMess", negated=True, text="APT29 no longer uses WellMess.")
    r = classify_one(f, [cand("f1", "APT29", "USES", "WellMess")], NEWER)
    assert (r.status, r.superseded_fact_ids) == ("UPDATED", ["f1"])


def test_denial_of_active_fact_is_conflicting():
    f = fact("APT29", "USES", "WellMess", negated=True, text="APT29 did not use WellMess.")
    r = classify_one(f, [cand("f1", "APT29", "USES", "WellMess")], OLDER)
    assert r.status == "CONFLICTING"


def test_low_confidence_fact_is_uncertain():
    r = classify_one(fact("APT28", "USES", "Mimikatz", conf=0.3), [cand("f1", "APT28", "USES", "Mimikatz")], NEWER)
    assert r.status == "UNCERTAIN"


def test_weak_entity_match_is_uncertain():
    # "Mimikats" vs stored "Mimikatz": similarity 0.875 -> accepted as a match but below the
    # 0.90 confidence bar, so policy rule 5 applies
    r = classify_one(fact("APT28", "USES", "Mimikats"), [cand("f1", "APT28", "USES", "Mimikatz")], NEWER)
    assert r.status == "UNCERTAIN"
    # a small typo with high similarity is still KNOWN
    r = classify_one(fact("APT28", "USES", "Mimkatz"), [cand("f1", "APT28", "USES", "Mimikatz")], NEWER)
    assert r.status == "KNOWN"


def test_historical_fact_seen_again_is_known():
    r = classify_one(fact("APT28", "USES", "Mimikatz"), [cand("f1", "APT28", "USES", "Mimikatz", status="HISTORICAL")], NEWER)
    assert (r.status, r.matched_fact_id) == ("KNOWN", "f1")


def test_opposite_historical_polarity_does_not_crash():
    old = cand('f1', 'APT28', 'USES', 'Mimikatz', status='HISTORICAL')
    old.negated = True
    result = classify_one(fact('APT28', 'USES', 'Mimikatz'), [old], NEWER)
    assert result.status == 'NEW'
