"""Fine-tune a relation classifier (entity markers + sequence classification) on AZERG.

    python train_re.py --model ehsanaghaei/SecureBERT --out runs/re --push_repo <hf-user>/openthreat-re

Labels: NONE, USES, DEPLOYS, EXPLOITS, TARGETS, ATTRIBUTED_TO, OTHER (see data_re.py).
Reported metrics: per-class P/R/F1, micro/macro over the 5 relation types, confusion matrix.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

import numpy as np

from common import (RE_LABELS, RELATION_TYPES, classification_prf, confusion, plot_confusion, set_seed,
                    write_experiment_log)
from data_re import MARKERS, load_azerg


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="ehsanaghaei/SecureBERT")
    ap.add_argument("--out", default="runs/re")
    ap.add_argument("--local_jsonl", default=None, help="AZERG rows as JSONL (for offline tests)")
    ap.add_argument("--epochs", type=float, default=4)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--max_len", type=int, default=256)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--push_repo", default="")
    args = ap.parse_args()

    import torch
    from transformers import (AutoModelForSequenceClassification, AutoTokenizer, DataCollatorWithPadding, Trainer,
                              TrainingArguments)

    set_seed(args.seed)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    train_all, skipped_train = load_azerg("train", args.local_jsonl)
    test, skipped_test = load_azerg("test", args.local_jsonl)
    rng = random.Random(args.seed)
    rng.shuffle(train_all)
    n_dev = max(1, int(0.1 * len(train_all)))
    dev, train = train_all[:n_dev], train_all[n_dev:]
    if args.limit:
        train, dev, test = train[: args.limit], dev[: max(20, args.limit // 5)], test[: max(20, args.limit // 5)]
    data_stats = {name: dict(Counter(e.label for e in items)) for name, items in
                  {"train": train, "dev": dev, "test": test}.items()}
    data_stats["skipped"] = {"train": dict(skipped_train), "test": dict(skipped_test)}
    print(json.dumps(data_stats, indent=1))

    label2id = {l: i for i, l in enumerate(RE_LABELS)}
    id2label = {i: l for l, i in label2id.items()}
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    tokenizer.add_special_tokens({"additional_special_tokens": MARKERS})
    model = AutoModelForSequenceClassification.from_pretrained(
        args.model, num_labels=len(RE_LABELS), id2label=id2label, label2id=label2id, ignore_mismatched_sizes=True
    )
    model.resize_token_embeddings(len(tokenizer))

    def encode(items):
        enc = []
        for e in items:
            x = tokenizer(e.text, truncation=True, max_length=args.max_len)
            x["labels"] = label2id[e.label]
            enc.append(dict(x))
        return enc

    train_ds, dev_ds, test_ds = encode(train), encode(dev), encode(test)

    # class weights (sqrt of inverse frequency) so rare relations such as EXPLOITS are not ignored
    counts = Counter(e.label for e in train)
    weights = torch.tensor([(len(train) / max(1, counts.get(l, 0))) ** 0.5 if counts.get(l) else 0.0
                            for l in RE_LABELS], dtype=torch.float)
    weights = weights / weights[weights > 0].mean()

    class WeightedTrainer(Trainer):
        def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
            labels = inputs.pop("labels")
            outputs = model(**inputs)
            loss = torch.nn.functional.cross_entropy(outputs.logits, labels, weight=weights.to(outputs.logits.device))
            return (loss, outputs) if return_outputs else loss

    def compute_metrics(eval_pred):
        logits, labels = eval_pred
        gold = [id2label[int(i)] for i in labels]
        pred = [id2label[int(i)] for i in np.argmax(logits, axis=-1)]
        m = classification_prf(gold, pred, RE_LABELS, RELATION_TYPES)
        return {"macro_f1": m["macro"]["f1"], "micro_f1": m["micro"]["f1"], "accuracy": m["accuracy"]}

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
        metric_for_best_model="macro_f1",
        fp16=torch.cuda.is_available(),
        logging_steps=50,
        report_to=[],
        seed=args.seed,
    )
    trainer = WeightedTrainer(model=model, args=targs, train_dataset=train_ds, eval_dataset=dev_ds,
                              data_collator=DataCollatorWithPadding(tokenizer), compute_metrics=compute_metrics)
    trainer.train()

    pred_out = trainer.predict(test_ds)
    gold = [id2label[int(i)] for i in pred_out.label_ids]
    pred = [id2label[int(i)] for i in np.argmax(pred_out.predictions, axis=-1)]
    metrics = classification_prf(gold, pred, RE_LABELS, RELATION_TYPES)
    cm = confusion(gold, pred, RE_LABELS)
    plot_confusion(cm, RE_LABELS, "Relation extraction confusion (AZERG test, row-normalised)", out / "confusion_re.png")
    (out / "metrics_re.json").write_text(json.dumps(
        {"test": metrics, "confusion_labels": RE_LABELS, "confusion": cm, "data": data_stats}, indent=2))
    # keep test predictions for error analysis in the report
    with open(out / "predictions_re_test.jsonl", "w") as f:
        for e, p in zip(test, pred):
            f.write(json.dumps({"text": e.text, "gold": e.label, "pred": p, "stix": e.stix_label}) + "\n")

    trainer.save_model(str(out / "model"))
    tokenizer.save_pretrained(str(out / "model"))
    write_experiment_log(out.parent / "experiments", "re_" + Path(args.model).name, {
        "task": "RE",
        "dataset": "QCRI/AZERG-Dataset (T3 negatives + T4 labels)",
        "label_mapping": "training/data_re.py:STIX_TO_OURS",
        "split": "AZERG train (90% train / 10% dev, seed-shuffled) and AZERG test",
        "base_model": args.model,
        "hyperparameters": {k: getattr(args, k) for k in ("epochs", "lr", "batch", "max_len", "limit")},
        "class_weights": dict(zip(RE_LABELS, [round(float(w), 3) for w in weights])),
        "seed": args.seed,
        "metrics": {"test_micro": metrics["micro"], "test_macro": metrics["macro"], "accuracy": metrics["accuracy"],
                    "per_type_f1": {t: metrics[t]["f1"] for t in RELATION_TYPES}},
        "hf_repo": args.push_repo or None,
    })
    print(json.dumps({"micro": metrics["micro"], "macro": metrics["macro"]}, indent=2))

    if args.push_repo:
        model.push_to_hub(args.push_repo, private=False)
        tokenizer.push_to_hub(args.push_repo)
        print("pushed to https://huggingface.co/" + args.push_repo)


if __name__ == "__main__":
    main()
