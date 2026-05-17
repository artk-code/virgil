#!/usr/bin/env python3
"""
Merge step (run after scripts/synthesize_book_qa.py finishes).

Inputs:
  instructions/virgil_train.jsonl    (v0.1 templated examples)
  instructions/virgil_eval.jsonl     (v0.1 eval)
  books/qa_final/virgil_books_seed.jsonl  (hand-authored examples)
  books/qa_raw/*.jsonl               (machine-synthesized from synthesize_book_qa.py)

Outputs:
  instructions_v0.2/virgil_train.jsonl
  instructions_v0.2/virgil_eval.jsonl
  instructions_v0.2/v0.2_report.json   (counts, token estimates, cost estimate)

Eval split policy:
  - v0.1 records keep their original train/eval assignment (technique-disjoint).
  - Hand-authored seed records: deterministic ~14% holdout, hash-keyed by source_chunk.
  - Machine-synthesized records: deterministic ~10% holdout, hash-keyed by source_chunk.
  - Same source_chunk always goes to the same split — prevents leakage of paraphrased
    variants of one chunk across train/eval.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import random
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V01_TRAIN = ROOT / "instructions" / "virgil_train.jsonl"
V01_EVAL = ROOT / "instructions" / "virgil_eval.jsonl"
BOOK_SEED = ROOT / "books" / "qa_final" / "virgil_books_seed.jsonl"
BOOK_RAW = ROOT / "books" / "qa_raw"
OUT_DIR = ROOT / "instructions_v0.2"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CHARS_PER_TOKEN = 3.8  # calibrated against cl100k_base


def stable_split(key: str, eval_pct: int) -> str:
    """Deterministic split assignment from a key string."""
    h = hashlib.md5(key.encode()).digest()
    bucket = h[0] % 100
    return "eval" if bucket < eval_pct else "train"


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def token_count(rec: dict) -> int:
    total_chars = sum(len(m["content"]) for m in rec["messages"])
    return int(total_chars / CHARS_PER_TOKEN)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed-eval-pct", type=int, default=14,
                    help="Holdout percentage for hand-authored seed records")
    ap.add_argument("--synth-eval-pct", type=int, default=10,
                    help="Holdout percentage for machine-synthesized records")
    args = ap.parse_args()

    # ----- Load v0.1 -------------------------------------------------------
    v1_train = load_jsonl(V01_TRAIN)
    v1_eval = load_jsonl(V01_EVAL)
    for r in v1_train:
        r["meta"]["synthesis"] = r["meta"].get("synthesis", "templated_v0.1")
        r["meta"]["split"] = "train"
    for r in v1_eval:
        r["meta"]["synthesis"] = r["meta"].get("synthesis", "templated_v0.1")
        r["meta"]["split"] = "eval"

    # ----- Load hand-authored seed ----------------------------------------
    seed = load_jsonl(BOOK_SEED)
    seed_train, seed_eval = [], []
    for r in seed:
        r["meta"].setdefault("synthesis", "hand_authored_v0.2")
        key = r["meta"].get("source_chunk") or json.dumps(r["messages"][1])
        sp = stable_split(f"seed::{key}", args.seed_eval_pct)
        r["meta"]["split"] = sp
        (seed_train if sp == "train" else seed_eval).append(r)

    # ----- Load machine-synthesized (if any) ------------------------------
    synth_records = []
    for p in sorted(BOOK_RAW.glob("*.jsonl")):
        for r in load_jsonl(p):
            r["meta"].setdefault("synthesis", "claude_synthesized_v0.2")
            r["meta"].setdefault("source_book", p.stem)
            synth_records.append(r)

    synth_train, synth_eval = [], []
    for r in synth_records:
        chunk_key = "::".join(r["meta"].get("source_ids", [])) or r["meta"].get("source_chunk", "?")
        sp = stable_split(f"synth::{chunk_key}", args.synth_eval_pct)
        r["meta"]["split"] = sp
        (synth_train if sp == "train" else synth_eval).append(r)

    # ----- Concat & shuffle -----------------------------------------------
    all_train = v1_train + seed_train + synth_train
    all_eval = v1_eval + seed_eval + synth_eval
    random.Random(2026).shuffle(all_train)
    random.Random(2027).shuffle(all_eval)

    # ----- Write outputs --------------------------------------------------
    train_path = OUT_DIR / "virgil_train.jsonl"
    eval_path = OUT_DIR / "virgil_eval.jsonl"
    with train_path.open("w") as f:
        for r in all_train:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with eval_path.open("w") as f:
        for r in all_eval:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # ----- Build report ---------------------------------------------------
    def stats(records: list[dict]) -> dict:
        by_task = Counter()
        by_book = Counter()
        by_synthesis = Counter()
        total_tokens = 0
        for r in records:
            by_task[r["meta"].get("task", "?")] += 1
            book = r["meta"].get("source_book") or r["meta"].get("book", "(v0.1_corpus)")
            by_book[book] += 1
            by_synthesis[r["meta"].get("synthesis", "?")] += 1
            total_tokens += token_count(r)
        return {
            "count": len(records),
            "tokens": total_tokens,
            "by_task": dict(by_task.most_common()),
            "by_book": dict(by_book.most_common()),
            "by_synthesis": dict(by_synthesis.most_common()),
        }

    train_stats = stats(all_train)
    eval_stats = stats(all_eval)

    # Cost estimate for fine-tuning (3 epochs, ~7k tok/s on A100 80GB QLoRA)
    epochs = 3
    tok_per_sec = 7000
    seconds = (train_stats["tokens"] * epochs) / tok_per_sec
    hours = seconds / 3600
    cost_a100 = round(hours * 2.79, 2)
    cost_h100 = round(hours * 0.6 * 3.99, 2)

    report = {
        "version": "v0.2",
        "train": train_stats,
        "eval": eval_stats,
        "training_cost_estimate": {
            "epochs": epochs,
            "tokens_total": train_stats["tokens"] * epochs,
            "hours_a100_80gb": round(hours, 2),
            "cost_a100_80gb_usd": cost_a100,
            "hours_h100_sxm_estimated": round(hours * 0.6, 2),
            "cost_h100_sxm_usd": cost_h100,
        },
    }
    (OUT_DIR / "v0.2_report.json").write_text(json.dumps(report, indent=2))

    # ----- Pretty print ---------------------------------------------------
    print(f"=== v0.2 merge complete ===\n")
    print(f"Train: {train_stats['count']:,} records, {train_stats['tokens']:,} tokens")
    print(f"Eval:  {eval_stats['count']:,} records, {eval_stats['tokens']:,} tokens")
    print(f"\nBy synthesis source (train):")
    for k, v in train_stats["by_synthesis"].items():
        print(f"  {k:35s} {v:>6,}")
    print(f"\nBy source book (train):")
    for k, v in train_stats["by_book"].items():
        print(f"  {k:35s} {v:>6,}")
    print(f"\nTraining cost estimate (3 epochs, QLoRA):")
    print(f"  Lambda A100 80GB ({hours:.2f}h × $2.79): ${cost_a100}")
    print(f"  Lambda H100 SXM ({hours*0.6:.2f}h × $3.99): ${cost_h100}")
    print(f"\nWrote:")
    print(f"  {train_path.relative_to(ROOT)}")
    print(f"  {eval_path.relative_to(ROOT)}")
    print(f"  {(OUT_DIR/'v0.2_report.json').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
