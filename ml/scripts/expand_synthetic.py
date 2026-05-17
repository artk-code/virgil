#!/usr/bin/env python3
"""
Synthetic expansion: use a strong teacher LLM (Claude) to take the deterministic
seed examples in instructions/virgil_train.jsonl and produce N additional
paraphrased / harder variants per seed.

This implements the "Synthetic data from a strong teacher" pattern in the
CyberLLM-FINDS paper and the 2026 hjLabs fine-tuning playbook. The seed
examples here are *correct* (anchored to MITRE STIX, Sigma, sysmon-config);
the teacher's job is to rephrase the user turn into more natural / varied
analyst language, sometimes ADD adversarial noise (irrelevant log fields,
red herrings, partial info), and re-derive the same reasoning chain.

Usage:
    export ANTHROPIC_API_KEY=sk-...
    python3 scripts/expand_synthetic.py \\
        --seeds 200 \\
        --variants 3 \\
        --tasks event_to_technique,sigma_to_technique \\
        --out instructions/virgil_train_synthetic.jsonl

The script writes the same messages-JSONL format. Run with --dry-run first
to see prompts before burning tokens. Budget hint: ~$0.50–$2 per 1000
variants on Claude Haiku, ~$5–$15 on Sonnet.

NOT IMPLEMENTED IN-LINE: the actual API call is left as a stub so this can
be reviewed before spending money. Fill in EXPAND_PROMPT and the call site.
"""
from __future__ import annotations
import argparse
import json
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEEDS = ROOT / "instructions" / "virgil_train.jsonl"


EXPAND_PROMPT = """You are augmenting a fine-tuning dataset for a cybersecurity LLM
that classifies endpoint telemetry against MITRE ATT&CK.

Below is a SEED example (user turn + correct assistant turn with chain-of-thought).

Your job: produce {n} VARIANTS of the user turn that:
1. Preserve the underlying technical content and ground-truth answer.
2. Use different phrasing, vocabulary, level of formality.
3. About half should add realistic noise: irrelevant fields, slightly
   different timestamps, decoy processes, or partial information that a
   real SOC analyst might paste in.
4. The assistant response stays the same — do not modify it.

Output strictly as JSON: a list of {n} objects, each {{"user": "...", "assistant": "..."}}.
The "assistant" field must be IDENTICAL to the seed assistant turn.

SEED EXAMPLE:
USER:
{user}

ASSISTANT:
{assistant}
"""


def load_seeds(path: Path, tasks: set[str] | None, n: int, seed: int = 1234):
    rows = []
    with path.open() as f:
        for line in f:
            r = json.loads(line)
            if tasks and r["meta"]["task"] not in tasks:
                continue
            rows.append(r)
    random.Random(seed).shuffle(rows)
    return rows[:n]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=200, help="Seed examples to expand")
    ap.add_argument("--variants", type=int, default=3, help="Variants per seed")
    ap.add_argument("--tasks", type=str, default="event_to_technique,sigma_to_technique,procedure_to_technique",
                    help="Comma-separated task types to target")
    ap.add_argument("--out", type=str, default="instructions/virgil_train_synthetic.jsonl")
    ap.add_argument("--model", type=str, default="claude-haiku-4-5-20251001")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    tasks = {t.strip() for t in args.tasks.split(",") if t.strip()}
    seeds = load_seeds(SEEDS, tasks, args.seeds)
    print(f"Loaded {len(seeds)} seed examples across tasks: {sorted(tasks)}")

    if args.dry_run:
        print("\n--- Example prompt that would be sent ---\n")
        s = seeds[0]
        print(EXPAND_PROMPT.format(
            n=args.variants,
            user=s["messages"][1]["content"][:600],
            assistant=s["messages"][2]["content"][:600],
        ))
        return

    # ----- Live API path (uncomment to use) ----------------------------------
    # Fail loud if no key — we don't want a silent partial run.
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY not set. Use --dry-run to preview prompts.")

    try:
        import anthropic
    except ImportError:
        sys.exit("pip install anthropic")

    client = anthropic.Anthropic()
    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n_written = 0
    with out_path.open("w") as out_f:
        for i, seed in enumerate(seeds):
            prompt = EXPAND_PROMPT.format(
                n=args.variants,
                user=seed["messages"][1]["content"],
                assistant=seed["messages"][2]["content"],
            )
            try:
                resp = client.messages.create(
                    model=args.model,
                    max_tokens=4000,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = resp.content[0].text  # type: ignore[attr-defined]
                # Strip code fences if present
                text = text.strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[1].rsplit("```", 1)[0]
                variants = json.loads(text)
            except Exception as e:
                print(f"[{i}] ERROR: {e}", file=sys.stderr)
                continue

            for v in variants:
                rec = {
                    "messages": [
                        seed["messages"][0],  # system
                        {"role": "user", "content": v["user"]},
                        {"role": "assistant", "content": v["assistant"]},
                    ],
                    "meta": {
                        **seed["meta"],
                        "synthetic": True,
                        "teacher_model": args.model,
                        "from_seed_idx": i,
                    },
                }
                out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n_written += 1
            if (i + 1) % 25 == 0:
                print(f"  [{i+1}/{len(seeds)}] {n_written} variants written")

    print(f"\nDone. {n_written} synthetic variants -> {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
