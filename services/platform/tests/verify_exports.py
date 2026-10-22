"""Read-only checks of live API exports and semantic search."""
import httpx, stix2, csv, io, time
with httpx.Client(base_url="http://platform-service:8000/api/v1/", timeout=120) as client:
    for kind in ["entities", "feed", "graph", "stix"]:
        r=client.get("exports/"+kind); r.raise_for_status()
        assert "attachment" in r.headers["content-disposition"]
        if kind == "stix":
            bundle=stix2.parse(r.text)
            print("Validated STIX bundle:", len(bundle.objects), "objects")
        elif kind=="graph":
            graph=r.json(); ids={n["id"] for n in graph["nodes"]}
            assert all(l["source"] in ids and l["target"] in ids for l in graph["links"])
        else:
            assert list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))
        print(kind, "export passed")
    r=client.get("documents",params={"query":"credential stealing malware", "limit":5});r.raise_for_status()
    assert r.json() and all("score" in item for item in r.json())
    print("Real embedding and Qdrant semantic search passed")
