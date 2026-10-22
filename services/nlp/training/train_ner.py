"""Fine-tune a transformer for cybersecurity NER on CyberNER (mapped to our 7 types).

    python train_ner.py --data cyberner_combined_stix.csv --model ehsanaghaei/SecureBERT \
        --out runs/ner --push_repo <hf-user>/openthreat-ner

Writes to --out: the model, metrics_ner.json, confusion_ner.png, split_ner.json (test sentence keys),
and an experiment log in --out/../experiments/.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from common import (ENTITY_TYPES, NER_LABELS, confusion, plot_confusion, set_seed, sha256_file, span_prf,
                    write_experiment_log)
from data_ner import Sentence, load_cyberner, split, stats

WINDOW = 100  # words per training window; long "sentences" (tables, lists) are cut into windows


def windows(sentences: list[Sentence], size: int = WINDOW) -> list[Sentence]:
    out = []
    for s in sentences:
        if len(s.tokens) <= size:
            out.append(s)
            continue
        i = 0
        while i < len(s.tokens):
            j = min(i + size, len(s.tokens))
            # don't cut inside an entity: move the cut back to before a B- / O boundary
            while j < len(s.tokens) and s.tags[j].startswith("I-") and j > i + size // 2:
                j -= 1
            out.append(Sentence(f"{s.key}#{i}", s.source, s.tokens[i:j], s.tags[i:j]))
            i = j
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--model", default="ehsanaghaei/SecureBERT")
    ap.add_argument("--out", default="runs/ner")
    ap.add_argument("--epochs", type=float, default=4)
    ap.add_argument("--lr", type=float, default=3e-5)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--max_len", type=int, default=256)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--limit", type=int, default=0, help="use only N training windows (smoke tests)")
    ap.add_argument("--push_repo", default="", help="Hugging Face repo id to upload the model to")
    args = ap.parse_args()

    import torch
    from transformers import (AutoModelForTokenClassification, AutoTokenizer, DataCollatorForTokenClassification,
                              Trainer, TrainingArguments)

    set_seed(args.seed)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    sentences = load_cyberner(args.data)
    parts = split(sentences, seed=args.seed)
    (out / "split_ner.json").write_text(json.dumps({k: [s.key for s in v] for k, v in parts.items()}))
    data_stats = stats(parts)
    train_w, dev_w, test_w = (windows(parts[k]) for k in ("train", "dev", "test"))
    if args.limit:
        train_w, dev_w, test_w = train_w[: args.limit], dev_w[: max(20, args.limit // 5)], test_w[: max(20, args.limit // 5)]
    print({k: len(v) for k, v in {"train": train_w, "dev": dev_w, "test": test_w}.items()})

    label2id = {l: i for i, l in enumerate(NER_LABELS)}
    id2label = {i: l for l, i in label2id.items()}
    tok_kwargs = {"add_prefix_space": True} if "roberta" in args.model.lower() or "securebert" in args.model.lower() else {}
    tokenizer = AutoTokenizer.from_pretrained(args.model, **tok_kwargs)

    def encode(items: list[Sentence]) -> list[dict]:
        encoded = []
        for s in items:
            enc = tokenizer(s.tokens, is_split_into_words=True, truncation=True, max_length=args.max_len)
            labels, prev = [], None
            for wid in enc.word_ids():
                if wid is None or wid == prev:
                    labels.append(-100)  # special tokens and non-first sub-words are ignored
                else:
                    labels.append(label2id[s.tags[wid]])
                prev = wid
            enc["labels"] = labels
            encoded.append(dict(enc))
        return encoded

    train_ds, dev_ds, test_ds = encode(train_w), encode(dev_w), encode(test_w)

    model = AutoModelForTokenClassification.from_pretrained(
        args.model, num_labels=len(NER_LABELS), id2label=id2label, label2id=label2id, ignore_mismatched_sizes=True
    )

    def to_tags(pred_ids: np.ndarray, label_ids: np.ndarray) -> tuple[list[list[str]], list[list[str]]]:
        gold, pred = [], []
        for p_row, l_row in zip(pred_ids, label_ids):
            g, p = [], []
            for p_i, l_i in zip(p_row, l_row):
                if l_i == -100:
                    continue
                g.append(id2label[int(l_i)])
                p.append(id2label[int(p_i)])
            gold.append(g)
            pred.append(p)
        return gold, pred

    def compute_metrics(eval_pred):
        logits, labels = eval_pred
        gold, pred = to_tags(np.argmax(logits, axis=-1), labels)
        m = span_prf(gold, pred)
        return {"f1": m["micro"]["f1"], "precision": m["micro"]["precision"], "recall": m["micro"]["recall"]}

    targs = TrainingArguments(
        output_dir=str(out / "checkpoints"),
        num_train_epochs=args.epochs,
        learning_rate=args.lr,
        per_device_train_batch_size=args.batch,
        per_device_eval_batch_size=args.batch * 2,
        warmup_ratio=0.1,
        weight_decay=0.01,
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=1,
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        fp16=torch.cuda.is_available(),
        logging_steps=50,
        report_to=[],
        seed=args.seed,
    )
    trainer = Trainer(model=model, args=targs, train_dataset=train_ds, eval_dataset=dev_ds,
                      data_collator=DataCollatorForTokenClassification(tokenizer), compute_metrics=compute_metrics)
    trainer.train()

    # ---- final evaluation on the held-out test set
    pred_out = trainer.predict(test_ds)
    gold, pred = to_tags(np.argmax(pred_out.predictions, axis=-1), pred_out.label_ids)
    metrics = span_prf(gold, pred)
    per_source = {}
    for src in sorted({s.source for s in test_w}):
        idx = [i for i, s in enumerate(test_w) if s.source == src]
        per_source[src] = span_prf([gold[i] for i in idx], [pred[i] for i in idx])["micro"]

    # token-level confusion over entity types (B/I merged)
    flat_g = [t[2:] if t != "O" else "O" for row in gold for t in row]
    flat_p = [t[2:] if t != "O" else "O" for row in pred for t in row]
    cm_labels = ENTITY_TYPES + ["O"]
    cm = confusion(flat_g, flat_p, cm_labels)
    plot_confusion(cm, cm_labels, "NER token confusion (test, row-normalised)", out / "confusion_ner.png")

    result = {"test": metrics, "test_per_source": per_source, "confusion_labels": cm_labels, "confusion": cm,
              "data": data_stats}
    (out / "metrics_ner.json").write_text(json.dumps(result, indent=2))

    trainer.save_model(str(out / "model"))
    tokenizer.save_pretrained(str(out / "model"))

    write_experiment_log(out.parent / "experiments", "ner_" + Path(args.model).name, {
        "task": "NER",
        "dataset": "CyberNER (cyberner_combined_stix.csv)",
        "dataset_sha256": sha256_file(args.data),
        "label_mapping": "training/data_ner.py:STIX_TO_OURS",
        "split": "per-source 80/10/10, seed-shuffled (training/data_ner.py:split)",
        "base_model": args.model,
        "hyperparameters": {k: getattr(args, k) for k in ("epochs", "lr", "batch", "max_len", "limit")},
        "seed": args.seed,
        "metrics": {"test_micro": metrics["micro"], "test_macro": metrics["macro"],
                    "per_type_f1": {t: metrics[t]["f1"] for t in ENTITY_TYPES}},
        "hf_repo": args.push_repo or None,
    })
    print(json.dumps({"micro": metrics["micro"], "macro": metrics["macro"]}, indent=2))

    if args.push_repo:
        model.push_to_hub(args.push_repo, private=False)
        tokenizer.push_to_hub(args.push_repo)
        print("pushed to https://huggingface.co/" + args.push_repo)


if __name__ == "__main__":
    main()
