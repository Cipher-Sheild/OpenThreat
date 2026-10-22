"""Build compact gazetteer files from the MITRE ATT&CK Enterprise STIX bundle.

Usage (from services/nlp/):
    curl -L -o /tmp/enterprise-attack.json \
        https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json
    python scripts/build_attack_resources.py /tmp/enterprise-attack.json

Writes app/resources/attack_*.json. Re-run when ATT&CK releases a new version.
ATT&CK® is © The MITRE Corporation; reproduced under the ATT&CK Terms of Use.
"""
import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "app" / "resources"


def _live(o: dict) -> bool:
    return not o.get("revoked") and not o.get("x_mitre_deprecated")


def _attack_id(o: dict) -> str | None:
    for ref in o.get("external_references", []):
        if ref.get("source_name") == "mitre-attack":
            return ref.get("external_id")
    return None


def main(bundle_path: str) -> None:
    bundle = json.loads(Path(bundle_path).read_text(encoding="utf-8"))
    objs = [o for o in bundle["objects"] if _live(o)]
    version = next(
        (o.get("x_mitre_version") for o in bundle["objects"] if o["type"] == "x-mitre-collection"), "unknown"
    )

    groups = []
    for o in objs:
        if o["type"] in ("intrusion-set",):
            names = sorted(set([o["name"], *o.get("aliases", [])]))
            groups.append({"id": _attack_id(o), "name": o["name"], "aliases": names})

    software = []
    for o in objs:
        if o["type"] in ("malware", "tool"):
            names = sorted(set([o["name"], *o.get("x_mitre_aliases", [])]))
            software.append(
                {
                    "id": _attack_id(o),
                    "name": o["name"],
                    "type": "MALWARE" if o["type"] == "malware" else "TOOL",
                    "aliases": names,
                }
            )

    techniques = []
    for o in objs:
        if o["type"] == "attack-pattern":
            tid = _attack_id(o)
            if not tid:
                continue
            desc = (o.get("description") or "").split("\n")[0]
            techniques.append({"id": tid, "name": o["name"], "description": desc[:400]})

    OUT.mkdir(parents=True, exist_ok=True)
    meta = {"source": "MITRE ATT&CK Enterprise", "attack_version": version}
    for fname, data in [
        ("attack_groups.json", groups),
        ("attack_software.json", software),
        ("attack_techniques.json", techniques),
    ]:
        (OUT / fname).write_text(json.dumps({"meta": meta, "items": data}, ensure_ascii=False, indent=0), encoding="utf-8")
        print(f"{fname}: {len(data)} items")


if __name__ == "__main__":
    main(sys.argv[1])
