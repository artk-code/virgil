#!/usr/bin/env python3
"""
v0.2 audit — runs after merge_v0_2.py.

Two checks:
  1. Structural validity (every assistant turn parses as reasoning+answer JSON).
  2. Verbatim-leak rate against source chunks (for examples with a source_chunk).
     Reports the fraction of examples that contain a 13+ word verbatim span from
     their source chunk. Goal: <1%.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
TRAIN = ROOT / "instructions_v0.2" / "virgil_train.jsonl"
EVAL = ROOT / "instructions_v0.2" / "virgil_eval.jsonl"
CHUNKS_DIR = ROOT / "books" / "chunks"

WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_'\-]*")


def words(s: str) -> list[str]:
    return [w.lower() for w in WORD_RE.findall(s)]


def longest_common_substring_words(a: str, b: str, max_n: int = 25) -> int:
    aw = words(a)
    bw = words(b)
    if not aw or not bw:
        return 0
    best = 0
    for n in range(4, max_n + 1):
        a_set = {tuple(aw[i:i + n]) for i in range(len(aw) - n + 1)}
        if not a_set:
            break
        b_set = {tuple(bw[i:i + n]) for i in range(len(bw) - n + 1)}
        if a_set & b_set:
            best = n
        else:
            break
    return best


def load_chunks() -> dict:
    by_id = {}
    if not CHUNKS_DIR.exists():
        return by_id
    for p in CHUNKS_DIR.glob("*.jsonl"):
        with p.open() as f:
            for line in f:
                r = json.loads(line)
                by_id[r["chunk_id"]] = r["text"]
    return by_id


def audit_file(path: Path, chunks: dict) -> dict:
    n_total = 0
    n_struct_ok = 0
    n_with_source = 0
    n_leaked = 0
    leak_examples = []
    max_lcs = 0
    leak_by_synth = Counter()
    total_by_synth = Counter()

    with path.open() as f:
        for line in f:
            r = json.loads(line)
            n_total += 1
            synth = r["meta"].get("synthesis", "?")
            total_by_synth[synth] += 1

            asst = r["messages"][2]["content"]
            if "<reasoning>" in asst and "</reasoning>" in asst and "<answer>" in asst and "</answer>" in asst:
                start = asst.index("<answer>") + len("<answer>")
                end = asst.index("</answer>")
                try:
                    json.loads(asst[start:end])
                    n_struct_ok += 1
                except json.JSONDecodeError:
                    pass

            # Verbatim check requires source_chunk
            src_ids = r["meta"].get("source_ids", []) or []
            src_chunk_id = r["meta"].get("source_chunk")
            candidates = [c for c in (src_ids + [src_chunk_id]) if c and c in chunks]
            if not candidates:
                continue
            n_with_source += 1
            joined = r["messages"][1]["content"] + " " + asst
            for cid in candidates:
                lcs = longest_common_substring_words(joined, chunks[cid])
                max_lcs = max(max_lcs, lcs)
                if lcs >= 13:
                    n_leaked += 1
                    leak_by_synth[synth] += 1
                    leak_examples.append({
                        "chunk_id": cid,
                        "synth": synth,
                        "lcs_words": lcs,
                        "user_preview": r["messages"][1]["content"][:120],
                    })
                    break  # one source is enough

    return {
        "total": n_total,
        "structurally_valid": n_struct_ok,
        "structural_validity_pct": round(100 * n_struct_ok / max(n_total, 1), 2),
        "with_source_chunk": n_with_source,
        "verbatim_leaked": n_leaked,
        "leak_rate_pct": round(100 * n_leaked / max(n_with_source, 1), 2),
        "max_lcs_words_observed": max_lcs,
        "totals_by_synthesis": dict(total_by_synth.most_common()),
        "leaks_by_synthesis": dict(leak_by_synth.most_common()),
        "leak_examples_sample": leak_examples[:5],
    }


def main() -> None:
    print("Loading source chunks for verbatim check...")
    chunks = load_chunks()
    print(f"  loaded {len(chunks)} chunks\n")

    for label, path in [("TRAIN", TRAIN), ("EVAL", EVAL)]:
        if not path.exists():
            print(f"{label}: file missing")
            continue
        print(f"=== {label}: {path.name} ===")
        rep = audit_file(path, chunks)
        print(f"  total records: {rep['total']:,}")
        print(f"  structurally valid: {rep['structurally_valid']:,} ({rep['structural_validity_pct']}%)")
        print(f"  with source chunk: {rep['with_source_chunk']:,}")
        print(f"  verbatim-leaked (13+ word span): {rep['verbatim_leaked']:,} ({rep['leak_rate_pct']}%)")
        print(f"  max LCS words observed: {rep['max_lcs_words_observed']}")
        if rep["totals_by_synthesis"]:
            print(f"  by synthesis source:")
            for k, v in rep["totals_by_synthesis"].items():
                leaks = rep["leaks_by_synthesis"].get(k, 0)
                pct = round(100 * leaks / max(v, 1), 2)
                print(f"    {k:35s} {v:>6,}  leaks={leaks} ({pct}%)")
        if rep["leak_examples_sample"]:
            print(f"  leak examples (max 5):")
            for e in rep["leak_examples_sample"]:
                print(f"    [{e['synth']}] {e['lcs_words']} words leaked from {e['chunk_id']}: \"{e['user_preview'][:80]}...\"")
        print()


if __name__ == "__main__":
    main()
