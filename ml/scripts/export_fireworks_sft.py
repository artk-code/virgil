#!/usr/bin/env python3
"""
Export VIRGIL synthesis records to Fireworks SFT JSONL.

Fireworks SFT uses OpenAI-compatible chat-completion JSONL:
one JSON object per line, each with a messages array. This exporter keeps the
training files Fireworks-clean by omitting VIRGIL repo metadata from each row
and writing split/source details into a sidecar manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = ROOT / "data" / "synthesis"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "fireworks"

EXPECTED_ROLES = ["system", "user", "assistant"]
CHARS_PER_TOKEN = 3.85
ANSWER_RE = re.compile(r"<answer>\s*(.*?)\s*</answer>", re.DOTALL)
REASONING_RE = re.compile(r"<reasoning>\s*(.*?)\s*</reasoning>", re.DOTALL)
SKIP_STEMS = ("fragment", "phi1_fragment", "temp")


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def approx_tokens_from_messages(messages: list[dict[str, Any]]) -> int:
    total_chars = sum(len(str(message.get("content", ""))) for message in messages)
    total_chars += sum(len(str(message.get("reasoning_content", ""))) for message in messages)
    return int(total_chars / CHARS_PER_TOKEN)


def source_files(input_dir: Path, explicit_files: list[str] | None) -> list[Path]:
    if explicit_files:
        files = [Path(path) for path in explicit_files]
    else:
        if not input_dir.is_absolute():
            input_dir = ROOT / input_dir
        files = sorted(input_dir.glob("*.jsonl"))

    clean_files = []
    for path in files:
        if not path.is_absolute():
            path = ROOT / path
        if path.stem.startswith(SKIP_STEMS):
            continue
        clean_files.append(path)
    return sorted(clean_files)


def extract_answer_json(assistant_content: str, location: str) -> str:
    match = ANSWER_RE.search(assistant_content)
    if not match:
        raise ValueError(f"{location}: missing <answer>...</answer> block")
    answer_json = match.group(1).strip()
    json.loads(answer_json)
    return answer_json


def extract_reasoning(assistant_content: str, location: str) -> str:
    match = REASONING_RE.search(assistant_content)
    if not match:
        raise ValueError(f"{location}: missing <reasoning>...</reasoning> block")
    reasoning = match.group(1).strip()
    if not reasoning:
        raise ValueError(f"{location}: empty <reasoning> block")
    return reasoning


def validate_virgil_record(record: dict[str, Any], path: Path, line_number: int) -> None:
    location = f"{path.name}:{line_number}"
    messages = record.get("messages")
    if not isinstance(messages, list) or len(messages) != 3:
        raise ValueError(f"{location}: messages must be exactly [system, user, assistant]")

    roles = [message.get("role") if isinstance(message, dict) else None for message in messages]
    if roles != EXPECTED_ROLES:
        raise ValueError(f"{location}: roles must be {EXPECTED_ROLES}, got {roles}")

    for index, message in enumerate(messages):
        if not isinstance(message.get("content"), str) or not message["content"].strip():
            raise ValueError(f"{location}: message {index} has empty or non-string content")

    assistant_content = messages[2]["content"]
    extract_reasoning(assistant_content, location)
    extract_answer_json(assistant_content, location)

    meta = record.get("meta")
    if not isinstance(meta, dict):
        raise ValueError(f"{location}: meta must be an object")
    if meta.get("source_book") != path.stem:
        raise ValueError(f"{location}: meta.source_book must equal {path.stem!r}")
    if meta.get("synthesized") is not True:
        raise ValueError(f"{location}: meta.synthesized must be true")
    if meta.get("split") != "train":
        raise ValueError(f"{location}: meta.split must be 'train'")
    source_ids = meta.get("source_ids")
    if not isinstance(source_ids, list) or not source_ids:
        raise ValueError(f"{location}: meta.source_ids must be a non-empty list")


def to_fireworks_messages(record: dict[str, Any], assistant_mode: str, location: str) -> list[dict[str, Any]]:
    source_messages = record["messages"]
    messages = [
        {"role": "system", "content": source_messages[0]["content"]},
        {"role": "user", "content": source_messages[1]["content"]},
    ]

    assistant_content = source_messages[2]["content"]
    if assistant_mode == "tags":
        messages.append({"role": "assistant", "content": assistant_content})
    elif assistant_mode == "reasoning_content":
        reasoning = extract_reasoning(assistant_content, location)
        answer_json = extract_answer_json(assistant_content, location)
        messages.append(
            {
                "role": "assistant",
                "content": f"<answer>{answer_json}</answer>",
                "reasoning_content": reasoning,
            }
        )
    elif assistant_mode == "answer_only":
        answer_json = extract_answer_json(assistant_content, location)
        messages.append({"role": "assistant", "content": f"<answer>{answer_json}</answer>"})
    else:
        raise ValueError(f"Unsupported assistant mode: {assistant_mode}")

    return messages


def load_examples(files: list[Path], assistant_mode: str) -> list[dict[str, Any]]:
    examples = []
    for path in files:
        with path.open(encoding="utf-8") as f:
            for line_number, raw_line in enumerate(f, 1):
                line = raw_line.strip()
                if not line:
                    continue
                location = f"{path.name}:{line_number}"
                record = json.loads(line)
                validate_virgil_record(record, path, line_number)
                messages = to_fireworks_messages(record, assistant_mode, location)
                meta = record["meta"]
                record_id = sha256_text(
                    json_dumps(
                        {
                            "source_file": path.name,
                            "line_number": line_number,
                            "messages": messages,
                        }
                    )
                )[:20]
                examples.append(
                    {
                        "id": record_id,
                        "source_file": path.name,
                        "source_book": meta.get("source_book", path.stem),
                        "line_number": line_number,
                        "task": meta.get("task", "unknown"),
                        "source_ids": list(meta.get("source_ids", [])),
                        "messages": messages,
                        "approx_tokens": approx_tokens_from_messages(messages),
                    }
                )
    return examples


def allocate_eval_counts(group_sizes: dict[str, int], eval_count: int, min_per_group: int) -> dict[str, int]:
    total = sum(group_sizes.values())
    if eval_count <= 0 or total <= 0:
        return {group: 0 for group in group_sizes}

    max_eval = sum(max(0, size - 1) for size in group_sizes.values())
    eval_count = min(eval_count, max_eval)

    raw = {group: eval_count * size / total for group, size in group_sizes.items()}
    counts = {
        group: min(max(0, size - 1), max(min_per_group if size > 1 else 0, math.floor(value)))
        for group, (size, value) in ((group, (group_sizes[group], raw[group])) for group in group_sizes)
    }

    while sum(counts.values()) > eval_count:
        candidates = [group for group, count in counts.items() if count > 0]
        group = min(candidates, key=lambda item: (raw[item] - math.floor(raw[item]), counts[item]))
        counts[group] -= 1

    while sum(counts.values()) < eval_count:
        candidates = [group for group, size in group_sizes.items() if counts[group] < size - 1]
        if not candidates:
            break
        group = max(candidates, key=lambda item: (raw[item] - counts[item], group_sizes[item]))
        counts[group] += 1

    return counts


def stratified_split(
    examples: list[dict[str, Any]],
    eval_ratio: float,
    eval_count: int | None,
    min_eval_per_category: int,
    seed: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    if eval_count is None:
        eval_count = round(len(examples) * eval_ratio)
    eval_count = max(0, min(eval_count, len(examples)))

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for example in examples:
        groups[example["source_book"]].append(example)

    rng = random.Random(seed)
    for group_examples in groups.values():
        rng.shuffle(group_examples)

    group_sizes = {group: len(group_examples) for group, group_examples in groups.items()}
    eval_counts = allocate_eval_counts(group_sizes, eval_count, min_eval_per_category)

    eval_ids = set()
    for group, count in eval_counts.items():
        eval_ids.update(example["id"] for example in groups[group][:count])

    train_examples = [example for example in examples if example["id"] not in eval_ids]
    eval_examples = [example for example in examples if example["id"] in eval_ids]
    rng.shuffle(train_examples)
    rng.shuffle(eval_examples)
    return train_examples, eval_examples, eval_counts


def write_jsonl(path: Path, examples: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for example in examples:
            f.write(json_dumps({"messages": example["messages"]}) + "\n")


def count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(item.get(key, "unknown")) for item in items).items()))


def task_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(str(item.get("task", "unknown")) for item in items).items()))


def file_info(path: Path, examples: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(ROOT)),
        "records": len(examples),
        "approx_tokens": sum(example["approx_tokens"] for example in examples),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def write_manifest(
    manifest_path: Path,
    source_paths: list[Path],
    train_path: Path,
    eval_path: Path,
    train_examples: list[dict[str, Any]],
    eval_examples: list[dict[str, Any]],
    eval_counts: dict[str, int],
    args: argparse.Namespace,
) -> None:
    all_examples = train_examples + eval_examples
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "format": "fireworks_openai_chat_sft_jsonl",
        "assistant_mode": args.assistant_mode,
        "source": {
            "input_files": [str(path.relative_to(ROOT)) for path in source_paths],
            "records": len(all_examples),
            "approx_tokens": sum(example["approx_tokens"] for example in all_examples),
        },
        "split": {
            "seed": args.seed,
            "eval_ratio": args.eval_ratio,
            "requested_eval_count": args.eval_count,
            "actual_eval_count": len(eval_examples),
            "stratified_by": "meta.source_book",
            "eval_counts_by_source_book": dict(sorted(eval_counts.items())),
        },
        "files": {
            "train": file_info(train_path, train_examples),
            "eval": file_info(eval_path, eval_examples),
        },
        "coverage": {
            "all_by_source_book": count_by(all_examples, "source_book"),
            "train_by_source_book": count_by(train_examples, "source_book"),
            "eval_by_source_book": count_by(eval_examples, "source_book"),
            "all_by_task": task_counts(all_examples),
            "train_by_task": task_counts(train_examples),
            "eval_by_task": task_counts(eval_examples),
        },
        "fireworks_docs_checked": [
            "https://docs.fireworks.ai/fine-tuning/fine-tuning-models",
            "https://docs.fireworks.ai/fine-tuning/training-prerequisites",
            "https://docs.fireworks.ai/fine-tuning/fine-tuning-via-api",
        ],
        "notes": [
            "Rows intentionally contain only Fireworks-compatible messages arrays.",
            "VIRGIL meta fields are summarized in this manifest and not embedded in training rows.",
            "Default assistant_mode=tags preserves <reasoning> and <answer> tags inside assistant content.",
            "Run scripts/validate_fireworks_sft.py before upload.",
        ],
    }
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export VIRGIL synthesis data to Fireworks SFT JSONL.")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--input-files", nargs="+", default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--train-file", default="virgil_fireworks_train.jsonl")
    parser.add_argument("--eval-file", default="virgil_fireworks_eval.jsonl")
    parser.add_argument("--manifest-file", default="manifest.json")
    parser.add_argument("--eval-ratio", type=float, default=0.05)
    parser.add_argument("--eval-count", type=int, default=None)
    parser.add_argument("--min-eval-per-category", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--assistant-mode",
        choices=["tags", "reasoning_content", "answer_only"],
        default="tags",
        help="How to represent VIRGIL reasoning in the assistant message.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    source_paths = source_files(args.input_dir, args.input_files)
    if not source_paths:
        raise SystemExit("No source JSONL files found.")

    examples = load_examples(source_paths, args.assistant_mode)
    train_examples, eval_examples, eval_counts = stratified_split(
        examples,
        eval_ratio=args.eval_ratio,
        eval_count=args.eval_count,
        min_eval_per_category=args.min_eval_per_category,
        seed=args.seed,
    )

    train_path = output_dir / args.train_file
    eval_path = output_dir / args.eval_file
    manifest_path = output_dir / args.manifest_file

    write_jsonl(train_path, train_examples)
    write_jsonl(eval_path, eval_examples)
    write_manifest(manifest_path, source_paths, train_path, eval_path, train_examples, eval_examples, eval_counts, args)

    print("Exported Fireworks SFT files:")
    print(f"  train:    {train_path.relative_to(ROOT)} ({len(train_examples)} records)")
    print(f"  eval:     {eval_path.relative_to(ROOT)} ({len(eval_examples)} records)")
    print(f"  manifest: {manifest_path.relative_to(ROOT)}")
    print(f"  approx tokens: {sum(example['approx_tokens'] for example in examples):,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
