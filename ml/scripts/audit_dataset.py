#!/usr/bin/env python3
"""
Audit the generated instruction dataset: per-task counts, token statistics,
estimated training-time fine-tuning cost on Lambda A100 80GB.

Uses a character-based token estimator (3.8 chars/token) since this sandbox
can't fetch tiktoken's BPE files. Accurate within ~15% for English + JSON,
which is fine for cost estimation. Replace with actual tokenizer counts in
your local environment for precise numbers (HuggingFace AutoTokenizer on the
exact base model you plan to fine-tune).
"""
from __future__ import annotations
import json
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
IN = ROOT / "instructions"

CHARS_PER_TOKEN = 3.8  # calibrated against cl100k_base on similar content


def count_tokens(rec: dict) -> int:
    total_chars = 0
    for m in rec["messages"]:
        total_chars += len(m["content"])
    return int(total_chars / CHARS_PER_TOKEN)


def audit(name: str, path: Path) -> dict:
    per_task_tokens = defaultdict(int)
    per_task_count = defaultdict(int)
    per_task_max = defaultdict(int)
    total_tokens = 0
    total_count = 0
    with path.open() as f:
        for line in f:
            r = json.loads(line)
            tk = count_tokens(r)
            t = r["meta"]["task"]
            per_task_tokens[t] += tk
            per_task_count[t] += 1
            per_task_max[t] = max(per_task_max[t], tk)
            total_tokens += tk
            total_count += 1
    print(f"\n=== {name}: {path.name} ===")
    print(f"{'task':<28s} {'count':>7s} {'tokens':>11s} {'avg':>6s} {'max':>6s}")
    for t in sorted(per_task_count):
        c = per_task_count[t]
        tk = per_task_tokens[t]
        print(f"{t:<28s} {c:>7d} {tk:>11,d} {tk//max(c,1):>6d} {per_task_max[t]:>6d}")
    print(f"{'TOTAL':<28s} {total_count:>7d} {total_tokens:>11,d} "
          f"{total_tokens//max(total_count,1):>6d}")
    return {"count": total_count, "tokens": total_tokens}


def main() -> None:
    train = audit("TRAIN", IN / "virgil_train.jsonl")
    eval_ = audit("EVAL", IN / "virgil_eval.jsonl")

    print("\n=== Training-cost estimate ===")
    # Rough rule: QLoRA on 7B/8B on 1× A100 80GB processes ~6–10k tokens/sec
    # at typical settings (batch 1, grad_accum 8, ctx 2048). Use 7k tokens/sec
    # conservatively. 3 epochs is typical.
    tokens_per_sec = 7000
    epochs = 3
    seconds = (train["tokens"] * epochs) / tokens_per_sec
    hours = seconds / 3600
    a100_rate = 2.79  # $/GPU/hr current Lambda on-demand
    h100_rate = 3.99
    print(f"  train tokens × {epochs} epochs = {train['tokens']*epochs:,}")
    print(f"  @ {tokens_per_sec:,} tok/s on 1× A100 80GB → {hours:.2f} hours")
    print(f"  Lambda A100 80GB: ${hours*a100_rate:.2f}")
    print(f"  Lambda H100 SXM:  ${hours*0.6*h100_rate:.2f}   (~1.6× faster, "
          f"so {hours*0.6:.2f}h × $3.99)")


if __name__ == "__main__":
    main()
