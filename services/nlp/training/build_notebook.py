"""Generate train_models_colab.ipynb from the training scripts (so the notebook never drifts from them).

    python training/build_notebook.py
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILES = ["common.py", "data_ner.py", "data_re.py", "train_ner.py", "train_re.py"]


def md(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n").splitlines(keepends=True)}


def code(text):
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
            "source": text.strip("\n").splitlines(keepends=True)}


cells = [
    md("""
# OpenThreat NLP: train the real NER and relation models (Phase 3)

**Before you start:** `Runtime â†’ Change runtime type â†’ T4 GPU`, then `Runtime â†’ Run all`.

What this does (about 30â€“40 minutes on a free T4):
1. Trains a **NER model** (SecureBERT) on **CyberNER**, mapped to our 7 entity types.
2. Trains a **relation model** on **AZERG**, mapped to our 5 relation types.
3. Evaluates both on held-out test sets (Precision / Recall / F1 + confusion matrices).
4. Uploads both models to your Hugging Face account, so the NLP service can download them.
5. Downloads `openthreat_results.zip` (metrics, plots, experiment logs). **Send that zip to Claude.**

You will be asked once for a Hugging Face **write token** (huggingface.co â†’ Settings â†’ Access Tokens â†’ New token â†’ type *Write*).
"""),
    code("""
# 1. Check the GPU
!nvidia-smi --query-gpu=name,memory.total --format=csv
import torch
assert torch.cuda.is_available(), "No GPU! Runtime -> Change runtime type -> T4 GPU, then run again."
"""),
    code("""
# 2. Install libraries (Colab already has torch)
!pip -q install "transformers==4.46.3" "accelerate>=0.34" "datasets>=2.20" matplotlib
"""),
    code("""
# 3. Settings â€” CHANGE HF_USER to your Hugging Face username
HF_USER = "your-hf-username"   # your Hugging Face username
BASE_MODEL = "ehsanaghaei/SecureBERT"   # RoBERTa pre-trained on cybersecurity text; fallback: "roberta-base"
NER_REPO = f"{HF_USER}/openthreat-ner"
RE_REPO = f"{HF_USER}/openthreat-re"
assert HF_USER != "your-hf-username", "Set HF_USER first"

from huggingface_hub import login, whoami, create_repo, upload_file
login()   # log in (or paste a WRITE token) when asked
print("Logged in as:", whoami()["name"])
# Check we can WRITE to both repos now, not after 40 minutes of training
for repo in (NER_REPO, RE_REPO):
    create_repo(repo, private=False, exist_ok=True)
    upload_file(path_or_fileobj=b"OpenThreat NLP model (training in progress)", path_in_repo="README.md", repo_id=repo)
    print("Write access OK:", "https://huggingface.co/" + repo)
"""),
    md("## 4. Training code (same files as `services/nlp/training/` in the repo)"),
]
for name in FILES:
    cells.append(code(f"%%writefile {name}\n" + (HERE / name).read_text()))

cells += [
    code("""
# 5. Get the CyberNER dataset
!git clone -q --depth 1 https://github.com/yasirech-chammakhy/CyberNER.git
!ls -la CyberNER/dataset
"""),
    code("""
# 6. Check the base model downloads; fall back to roberta-base if it doesn't
from transformers import AutoTokenizer
try:
    AutoTokenizer.from_pretrained(BASE_MODEL, add_prefix_space=True)
except Exception as e:
    print("Could not load", BASE_MODEL, "->", e, "\\nFalling back to roberta-base")
    BASE_MODEL = "roberta-base"
print("Base model:", BASE_MODEL)
"""),
    code("""
# 7. Train + evaluate NER (~15-20 min)
import subprocess, sys
subprocess.run([sys.executable, "train_ner.py", "--data", "CyberNER/dataset/cyberner_combined_stix.csv",
                "--model", BASE_MODEL, "--out", "runs/ner", "--push_repo", NER_REPO], check=True)  # stops on any error
"""),
    code("""
# 8. Train + evaluate relation extraction (~10-15 min)
import subprocess, sys
subprocess.run([sys.executable, "train_re.py", "--model", BASE_MODEL, "--out", "runs/re",
                "--push_repo", RE_REPO], check=True)  # stops on any error
"""),
    code("""
# 9. Results
import json
from IPython.display import Image, display
ner = json.load(open("runs/ner/metrics_ner.json"))["test"]
re_ = json.load(open("runs/re/metrics_re.json"))["test"]
print("NER test  micro F1:", ner["micro"]["f1"], " macro F1:", ner["macro"]["f1"])
for t in ["THREAT_ACTOR","MALWARE","TOOL","VULNERABILITY","TECHNIQUE","ORGANIZATION","OBSERVABLE"]:
    print(f"  {t:<14} P={ner[t]['precision']:.3f} R={ner[t]['recall']:.3f} F1={ner[t]['f1']:.3f} (n={ner[t]['support']})")
print("RE test   micro F1:", re_["micro"]["f1"], " macro F1:", re_["macro"]["f1"], " accuracy:", re_["accuracy"])
for t in ["USES","DEPLOYS","EXPLOITS","TARGETS","ATTRIBUTED_TO"]:
    print(f"  {t:<14} P={re_[t]['precision']:.3f} R={re_[t]['recall']:.3f} F1={re_[t]['f1']:.3f} (n={re_[t]['support']})")
display(Image("runs/ner/confusion_ner.png"))
display(Image("runs/re/confusion_re.png"))
"""),
    code("""
# Verify the models are really on Hugging Face
from huggingface_hub import HfApi
for repo in (NER_REPO, RE_REPO):
    files = [f.rfilename for f in HfApi().model_info(repo).siblings]
    assert any(f.endswith((".safetensors", ".bin")) for f in files), f"{repo}: weights missing! {files}"
    print("VERIFIED on Hugging Face:", "https://huggingface.co/" + repo, "|", len(files), "files")
"""),
    code("""
# 10. Download the results zip -> send it to Claude
!cd runs && zip -q -r ../openthreat_results.zip ner/metrics_ner.json ner/confusion_ner.png ner/split_ner.json re/metrics_re.json re/confusion_re.png re/predictions_re_test.jsonl experiments
from google.colab import files
files.download("openthreat_results.zip")
print("Models: https://huggingface.co/" + NER_REPO, " https://huggingface.co/" + RE_REPO)
"""),
]

nb = {"cells": cells, "metadata": {"accelerator": "GPU", "colab": {"gpuType": "T4", "provenance": []},
                                   "kernelspec": {"display_name": "Python 3", "name": "python3"},
                                   "language_info": {"name": "python"}},
      "nbformat": 4, "nbformat_minor": 0}
out = HERE / "train_models_colab.ipynb"
out.write_text(json.dumps(nb, indent=1))
print("wrote", out)

# ---------------------------------------------------------------- relation model only (retraining)
re_cells = [
    md("""
# OpenThreat NLP: retrain the relation model only (~10-15 min)

Same as the full notebook but only the relation-extraction part. It now also learns
**"no relation"** (NONE) from generated negative pairs. It uploads to the same Hugging Face repo,
so nothing else needs to change.

**Before you start:** `Runtime â†’ Change runtime type â†’ T4 GPU`, set `HF_USER` in cell 3, then
`Runtime â†’ Run all`. At the end it downloads `openthreat_re_results.zip`. **Send that to Claude.**
"""),
    cells[1], cells[2], cells[3],
]
for name in ["common.py", "data_re.py", "train_re.py"]:
    re_cells.append(code(f"%%writefile {name}\n" + (HERE / name).read_text()))
re_cells += [
    next(c for c in cells if "Check the base model" in "".join(c["source"])),
    next(c for c in cells if "train_re.py" in "".join(c["source"]) and "%%writefile" not in "".join(c["source"])),
    code("""
# Results
import json
from IPython.display import Image, display
m = json.load(open("runs/re/metrics_re.json"))
re_ = m["test"]
print("Test label counts:", m["data"]["test"])
print("RE test  micro F1:", re_["micro"]["f1"], " macro F1:", re_["macro"]["f1"], " accuracy:", re_["accuracy"])
for t in ["NONE","USES","DEPLOYS","EXPLOITS","TARGETS","ATTRIBUTED_TO","OTHER"]:
    print(f"  {t:<14} P={re_[t]['precision']:.3f} R={re_[t]['recall']:.3f} F1={re_[t]['f1']:.3f} (n={re_[t]['support']})")
display(Image("runs/re/confusion_re.png"))
"""),
    code("""
# Verify the model is really on Hugging Face
from huggingface_hub import HfApi
files = [f.rfilename for f in HfApi().model_info(RE_REPO).siblings]
assert any(f.endswith((".safetensors", ".bin")) for f in files), f"weights missing! {files}"
print("VERIFIED on Hugging Face:", "https://huggingface.co/" + RE_REPO, "|", len(files), "files")
"""),
    code("""
# Download the results zip -> send it to Claude
!cd runs && zip -q -r ../openthreat_re_results.zip re/metrics_re.json re/confusion_re.png re/predictions_re_test.jsonl experiments
from google.colab import files
files.download("openthreat_re_results.zip")
print("Model: https://huggingface.co/" + RE_REPO)
"""),
]
nb_re = {**nb, "cells": re_cells}
out = HERE / "retrain_re_colab.ipynb"
out.write_text(json.dumps(nb_re, indent=1))
print("wrote", out)
