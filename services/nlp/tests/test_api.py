"""HTTP endpoints, contract conformance and the Phase 2 milestone (one KNOWN + one NEW)."""
from conftest import read_fixture

DOC1 = read_fixture("doc1_jan2024.txt")
DOC2 = read_fixture("doc2_jun2024.txt")


def _errors(validator, payload):
    return [f"{list(e.path)}: {e.message}" for e in validator.iter_errors(payload)]


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "warming", "error") and body["schema_version"] == "1.1" and body["embedding_dim"] == 768
    assert isinstance(body['ready'], bool)


def test_analyze_matches_contract(client, contract):
    req = {"document_id": "doc-1", "text": DOC1, "source_name": "CISA", "source_url": "https://example.org/a",
           "published_at": "2024-01-15T00:00:00Z"}
    assert not _errors(contract("analyze_request"), req)
    r = client.post("/analyze", json=req)
    assert r.status_code == 200, r.text
    body = r.json()
    assert not _errors(contract("analyze_response"), body)
    assert len(body["document_embedding"]) == 768
    assert body["novelty"] == []
    assert body["relations"], "expected relations from the fixture"


def test_analyze_pdf_pages(client, contract):
    req = {"document_id": "pdf-1", "source_name": "upload", "pages": [
        {"page_number": 1, "text": "Threat report."},
        {"page_number": 2, "text": "APT28 used Mimikatz. It exploited CVE-2023-23397."},
    ]}
    body = client.post("/analyze", json=req).json()
    assert not _errors(contract("analyze_response"), body)
    rel = next(x for x in body["relations"] if x["object"] == "Mimikatz")
    assert rel["evidence"]["page_number"] == 2
    joined = "Threat report.\n\nAPT28 used Mimikatz. It exploited CVE-2023-23397."
    assert joined[rel["evidence"]["char_start"]:rel["evidence"]["char_end"]] == rel["evidence"]["text"]
    assert all(e["page_number"] == 2 for e in body["entities"])


def test_analyze_requires_text_or_pages(client):
    assert client.post("/analyze", json={"document_id": "x", "source_name": "s"}).status_code == 422


def test_embed(client, contract):
    r = client.post("/embed", json={"texts": ["APT28 used Mimikatz", "Fancy Bear used Mimikatz"]})
    body = r.json()
    assert not _errors(contract("embed_response"), body)
    assert body["dim"] == 768 and len(body["embeddings"]) == 2


def test_resolve(client, contract):
    req = {"mentions": [{"mention": "Fancy Bear", "type": "THREAT_ACTOR"}, {"mention": "Turla", "type": "THREAT_ACTOR"}],
           "known_entities": [{"entity_id": "e1", "canonical_name": "APT28", "type": "THREAT_ACTOR", "aliases": []}]}
    assert not _errors(contract("resolve_request"), req)
    body = client.post("/resolve", json=req).json()
    assert not _errors(contract("resolve_response"), body)
    assert body["results"][0]["entity_id"] == "e1"
    assert body["results"][1]["entity_id"] is None


def test_milestone_known_and_new(client, contract):
    """Phase 2 target: feed two CTI documents; one fact comes back KNOWN and one NEW.

    This mimics exactly what the platform service's platform does:
      1. /analyze doc 1 and store its relations as facts (here: in a list)
      2. /analyze doc 2
      3. send doc 2's relations + the stored facts as candidates to /classify_novelty
    """
    a1 = client.post("/analyze", json={"document_id": "doc-1", "text": DOC1, "source_name": "CISA",
                                       "published_at": "2024-01-15T00:00:00Z"}).json()
    stored = [
        {"fact_id": f"f{i}", "subject": r["subject"], "relation": r["relation"], "object": r["object"],
         "negated": r["negated"], "status": "ACTIVE",
         "first_seen_at": "2024-01-15T00:00:00Z", "last_seen_at": "2024-01-15T00:00:00Z", "source_name": "CISA"}
        for i, r in enumerate(a1["relations"])
    ]
    a2 = client.post("/analyze", json={"document_id": "doc-2", "text": DOC2, "source_name": "Vendor blog",
                                       "published_at": "2024-06-20T00:00:00Z"}).json()
    req = {"document_id": "doc-2", "published_at": "2024-06-20T00:00:00Z", "facts": a2["relations"], "candidates": stored}
    assert not _errors(contract("classify_novelty_request"), req)
    body = client.post("/classify_novelty", json=req).json()
    assert not _errors(contract("classify_novelty_response"), body)

    labels = {(r["fact"]["subject"], r["fact"]["relation"], r["fact"]["object"]): r for r in body["results"]}
    # Fancy Bear (doc 2) resolves to APT28 (doc 1): same fact -> KNOWN
    known = labels[("APT28", "USES", "Mimikatz")]
    assert known["status"] == "KNOWN" and known["matched_fact_id"] is not None
    # HeadLace was never seen before -> NEW
    assert labels[("APT28", "DEPLOYS", "HeadLace")]["status"] == "NEW"
    # bonus: the Snake attribution changed from Turla to APT29 in a newer report -> UPDATED
    upd = labels[("Uroburos", "ATTRIBUTED_TO", "APT29")]
    assert upd["status"] == "UPDATED" and upd["superseded_fact_ids"]
