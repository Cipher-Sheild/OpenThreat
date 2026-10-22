"""Run every Phase 4/5 evaluation with the REAL models and collect the results.

Run inside the NLP container (it has the embedding model and downloads the trained models):

    docker compose run --rm -v "$PWD/services/nlp:/work" -w /work nlp-service python evaluation/run_all.py

It evaluates the rule-based pipeline and, if NER_MODEL / RE_MODEL are set in .env, the hybrid
pipeline too, then writes everything to services/nlp/evaluation/results/ and results.zip.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "evaluation" / "results"
CYBERNER = ROOT / "evaluation" / "data" / "cyberner_combined_stix.csv"
CYBERNER_URL = "https://raw.githubusercontent.com/yasirech-chammakhy/CyberNER/main/dataset/cyberner_combined_stix.csv"


def sh(args: list[str], env: dict | None = None) -> None:
    print("\n$", " ".join(args), flush=True)
    subprocess.run(args, check=True, env={**os.environ, **(env or {})}, cwd=ROOT)


def main() -> None:
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        sh([sys.executable, "-m", "pip", "install", "-q", "matplotlib"])
    if not CYBERNER.exists():
        print("downloading CyberNER test data ...")
        CYBERNER.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(CYBERNER_URL, CYBERNER)

    ner_model, re_model = os.getenv("NER_MODEL", ""), os.getenv("RE_MODEL", "")
    rules_env = {"NER_MODEL": "", "RE_MODEL": ""}
    py = sys.executable

    if RESULTS.exists():
        shutil.rmtree(RESULTS)
    (RESULTS / "rules").mkdir(parents=True)

    # Phase 4
    sh([py, "evaluation/eval_attack.py", "--out", str(RESULTS)], rules_env)
    sh([py, "evaluation/eval_temporal.py", "--out", str(RESULTS)], rules_env)
    # Phase 3 vs 2: NER on CyberNER test
    sh([py, "evaluation/eval_ner.py", "--data", str(CYBERNER), "--out", str(RESULTS), "--tag", "rules"], rules_env)
    if ner_model:
        sh([py, "evaluation/eval_ner.py", "--data", str(CYBERNER), "--out", str(RESULTS), "--tag", "hybrid",
            "--ner_model", ner_model])
    # Phase 5: novelty benchmark, baselines, ablations
    sh([py, "evaluation/eval_novelty.py", "--out", str(RESULTS / "rules")], rules_env)
    if ner_model or re_model:
        (RESULTS / "hybrid").mkdir(exist_ok=True)
        sh([py, "evaluation/eval_novelty.py", "--out", str(RESULTS / "hybrid")])

    summary = {"ner_model": ner_model or None, "re_model": re_model or None}
    for f in sorted(RESULTS.rglob("*.json")):
        if f.name.endswith("_errors.json"):
            continue
        data = json.loads(f.read_text())
        summary[str(f.relative_to(RESULTS))] = {k: v for k, v in data.items()
                                                if k not in ("details", "threshold_curve", "confusion", "test_per_source")}
    (RESULTS / "summary.json").write_text(json.dumps(summary, indent=2))
    shutil.make_archive(str(ROOT / "results"), "zip", RESULTS)
    print("\nDone. Send services/nlp/results.zip to Claude.")


if __name__ == "__main__":
    main()
