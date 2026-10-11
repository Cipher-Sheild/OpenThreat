"""Phase 2 milestone demo: run against the live NLP service.

    python nlp-service/scripts/demo_milestone.py                    # http://localhost:8001
    python nlp-service/scripts/demo_milestone.py http://host:8001   # other address

It does what Member 2's platform will do:
  1. POST /analyze on an older report and keep its relations as "stored facts"
  2. POST /analyze on a newer report
  3. POST /classify_novelty with the new facts and the stored facts as candidates
and prints the NEW / KNOWN / UPDATED / ... label of every new fact. Uses only the standard library.
"""
import json
import sys
import urllib.request
from pathlib import Path

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8001").rstrip("/")
FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read())


def main() -> None:
    with urllib.request.urlopen(BASE + "/health", timeout=10) as resp:
        print("health:", json.loads(resp.read()))

    doc1 = (FIXTURES / "doc1_jan2024.txt").read_text(encoding="utf-8")
    doc2 = (FIXTURES / "doc2_jun2024.txt").read_text(encoding="utf-8")

    print("\nAnalyzing document 1 (Jan 2024)... (first call downloads the embedding model, can take a few minutes)")
    a1 = post("/analyze", {"document_id": "demo-1", "text": doc1, "source_name": "CISA",
                           "published_at": "2024-01-15T00:00:00Z"})
    stored = []
    for i, r in enumerate(a1["relations"]):
        print(f"  stored fact f{i}: {r['subject']} {r['relation']} {r['object']}  (conf {r['confidence']})")
        stored.append({"fact_id": f"f{i}", "subject": r["subject"], "relation": r["relation"], "object": r["object"],
                       "negated": r["negated"], "status": "ACTIVE", "first_seen_at": "2024-01-15T00:00:00Z",
                       "last_seen_at": "2024-01-15T00:00:00Z", "source_name": "CISA"})

    print("\nAnalyzing document 2 (Jun 2024)...")
    a2 = post("/analyze", {"document_id": "demo-2", "text": doc2, "source_name": "Vendor blog",
                           "published_at": "2024-06-20T00:00:00Z"})
    print(f"  {len(a2['entities'])} entities, {len(a2['relations'])} relations, "
          f"embedding dim {len(a2['document_embedding'])} ({a2['processing']['embedding_model']})")

    result = post("/classify_novelty", {"document_id": "demo-2", "published_at": "2024-06-20T00:00:00Z",
                                        "facts": a2["relations"], "candidates": stored})
    print("\nNovelty of document 2's facts:")
    for r in result["results"]:
        f = r["fact"]
        print(f"  {r['status']:<11} {f['subject']} {f['relation']} {f['object']}")
        print(f"              -> {r['reason']}")

    statuses = {r["status"] for r in result["results"]}
    ok = {"KNOWN", "NEW"} <= statuses
    print("\nMilestone (one KNOWN + one NEW):", "PASSED" if ok else "NOT MET")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
