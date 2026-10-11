# Models and data

## Configure inference

The default environment configures the existing public trained checkpoints:

- [OpenThreat NER](https://huggingface.co/alialtam/openthreat-ner): `NER_MODEL=alialtam/openthreat-ner`, with 15 BIO token labels.
- [OpenThreat relations](https://huggingface.co/alialtam/openthreat-re): `RE_MODEL=alialtam/openthreat-re`, with seven sequence-classification labels.
- [BGE base English v1.5](https://huggingface.co/BAAI/bge-base-en-v1.5): normalized 768-dimensional embeddings.

The startup scripts create `.env` from these defaults. Model libraries download the required files at first launch and cache them under `nlp-service/model_cache`, mounted as `/models` in Docker. The two trained model configuration files were verified publicly accessible without authentication on 11 October 2026. Complete first-launch weight download and startup timing were not rerun for this package.

The Hugging Face account namespace is intentionally visible in checkpoint URLs so users can obtain the exact models. Student names, PRNs and academic cover pages remain excluded.

Both model settings also accept compatible alternative checkpoint IDs or local folders. To use authorized local copies, place them under `nlp-service/model_cache/openthreat-ner` and `nlp-service/model_cache/openthreat-re`, and set `/models/openthreat-ner` and `/models/openthreat-re` in `.env`. Folders need configuration, tokenizer files and weights. Relation inference uses the marked-pair tokenization and label mapping in the training code.

Clearing `NER_MODEL` and `RE_MODEL` selects rule-only entity/relation extraction; BGE inference remains real. Hybrid benchmark scores require the trained models. Weights and corpora retain upstream terms and are excluded from Git. Training source and scripts are included.

## Training

Open the notebooks in `nlp-service/training/` on a GPU runtime. Set the Hugging Face namespace placeholder before running. Code cells that log in or upload models perform external writes when you execute them. Outputs and execution metadata have been cleared from the distributed notebooks.

The base encoder is identified in the training code so the workflow is reproducible. The project uses SecureBERT fine-tuning rather than training a transformer from scratch. Final training logs are in `nlp-service/experiments/`; namespace fields are replaced with a placeholder for publication. Other recorded settings and metrics are preserved.

## Dataset sources

| Resource | Use | Acquisition |
|---|---|---|
| CyberNER | English entity training and evaluation | https://github.com/yasirech-chammakhy/CyberNER |
| AZERG | Entity-pair relationship learning | https://huggingface.co/datasets/QCRI/AZERG-Dataset |
| TRAM | Technique retrieval anchors and held-out mapping | https://github.com/center-for-threat-informed-defense/tram |
| CTI-HAL | Out-of-domain behavior evaluation | https://arxiv.org/abs/2504.05866 |
| Project novelty cases | Constructed policy evaluation | `nlp-service/evaluation/data/novelty_benchmark.jsonl` |

Large corpora, source report collections, CTI-HAL passages and TRAM negative passages are excluded. `evaluation/run_all.py` downloads CyberNER if missing; other external evaluation inputs must be acquired and prepared in the filenames expected by the evaluators. The authored novelty cases and held-out TRAM document split are included. Dataset and model licenses must be checked before use or redistribution; source access alone does not transfer ownership.

The runtime MITRE dictionaries and TRAM anchors are included with retained notices. They are reference resources, not mock data. Source collectors do not create a human-annotated accuracy dataset.
