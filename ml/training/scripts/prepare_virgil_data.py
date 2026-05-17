#!/usr/bin/env python3
"""
Prepare VIRGIL training data for fine-tuning.

This script converts the various VIRGIL JSONL sources (android_app_re, red_team_engineering,
investigative_osint, soc_training, etc.) into the format expected by Llama-Factory or Unsloth.

It supports:
- Creating train / eval splits
- Filtering by task type (for VIRGIL-PHI1 vs VIRGIL-MINI-1)
- Converting to ShareGPT / Alpaca / Phi format
"""

import argparse
import json
import random
from pathlib import Path
from typing import List, Dict


def load_virgil_jsonl(path: str) -> List[Dict]:
    """Load VIRGIL-style JSONL (messages + meta)."""
    data = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            ex = json.loads(line)
            data.append(ex)
    return data


def convert_to_llamafactory_format(example: Dict, system_prompt: str) -> Dict:
    """Convert VIRGIL format to Llama-Factory ShareGPT format."""
    messages = example["messages"]
    return {
        "conversations": [
            {"from": "system", "value": system_prompt},
            {"from": "human", "value": messages[1]["content"]},
            {"from": "gpt", "value": messages[2]["content"]},
        ]
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_files", nargs="+", required=True, help="List of VIRGIL JSONL files")
    parser.add_argument("--output_dir", type=str, default="data/virgil_phi1")
    parser.add_argument("--eval_ratio", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    all_examples = []
    for f in args.input_files:
        all_examples.extend(load_virgil_jsonl(f))

    random.shuffle(all_examples)
    split_idx = int(len(all_examples) * (1 - args.eval_ratio))

    train_data = all_examples[:split_idx]
    eval_data = all_examples[split_idx:]

    system_prompt = (
        "You are VIRGIL-Advisor, the endpoint-detection assistant inside the VIRGIL security platform. "
        "You reason about MITRE ATT&CK techniques, detection logic, and host telemetry. "
        "Wrap your step-by-step reasoning in <reasoning>...</reasoning> tags, then give the final "
        "structured response in <answer>...</answer> tags. Be precise; cite ATT&CK IDs in the form Txxxx or Txxxx.yyy."
    )

    train_formatted = [convert_to_llamafactory_format(ex, system_prompt) for ex in train_data]
    eval_formatted = [convert_to_llamafactory_format(ex, system_prompt) for ex in eval_data]

    with open(Path(args.output_dir) / "train.json", "w") as f:
        json.dump(train_formatted, f, indent=2)

    with open(Path(args.output_dir) / "eval.json", "w") as f:
        json.dump(eval_formatted, f, indent=2)

    print(f"Prepared {len(train_formatted)} train and {len(eval_formatted)} eval examples.")
    print(f"Saved to {args.output_dir}")


if __name__ == "__main__":
    main()
