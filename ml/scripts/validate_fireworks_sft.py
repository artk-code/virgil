#!/usr/bin/env python3
"""
Validate Fireworks SFT JSONL exports for VIRGIL.

This checks the Fireworks chat-message shape plus VIRGIL-specific assistant
contract: complete reasoning/answer tags or Fireworks reasoning_content, and
parseable JSON inside <answer>...</answer>.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIREWORKS_DIR = ROOT / "data" / "fireworks"
DEFAULT_FILES = [
    DEFAULT_FIREWORKS_DIR / "virgil_fireworks_train.jsonl",
    DEFAULT_FIREWORKS_DIR / "virgil_fireworks_eval.jsonl",
]

ALLOWED_ROOT_KEYS = {"messages", "weight", "tools"}
ALLOWED_ROLES = {"system", "user", "assistant"}
ANSWER_RE = re.compile(r"<answer>\s*(.*?)\s*</answer>", re.DOTALL)
REASONING_RE = re.compile(r"<reasoning>\s*(.*?)\s*</reasoning>", re.DOTALL)
CHARS_PER_TOKEN = 3.85


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def approx_tokens(messages: list[dict[str, Any]]) -> int:
    total_chars = 0
    for message in messages:
        total_chars += len(str(message.get("content", "")))
        total_chars += len(str(message.get("reasoning_content", "")))
    return int(total_chars / CHARS_PER_TOKEN)


def extract_answer(content: str) -> str | None:
    match = ANSWER_RE.search(content)
    if not match:
        return None
    return match.group(1).strip()


def validate_messages(
    row: dict[str, Any],
    location: str,
    expect_virgil_tags: bool,
    min_reasoning_chars: int,
) -> tuple[int, list[str]]:
    issues: list[str] = []
    messages = row.get("messages")
    if not isinstance(messages, list) or not messages:
        return 0, [f"{location}: missing or empty messages array"]

    roles = []
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            issues.append(f"{location}: message {index} is not an object")
            continue

        role = message.get("role")
        roles.append(role)
        if role not in ALLOWED_ROLES:
            issues.append(f"{location}: message {index} has invalid role {role!r}")

        content = message.get("content")
        if not isinstance(content, str):
            issues.append(f"{location}: message {index} content must be a string")

        if "weight" in message and message["weight"] not in (0, 1):
            issues.append(f"{location}: message {index} weight must be 0 or 1 when present")

        if "reasoning_content" in message and not isinstance(message["reasoning_content"], str):
            issues.append(f"{location}: message {index} reasoning_content must be a string")

    if "system" in roles and roles[0] != "system":
        issues.append(f"{location}: system message must be first when present")

    if not any(role == "user" for role in roles):
        issues.append(f"{location}: at least one user message is required")
    if not any(role == "assistant" for role in roles):
        issues.append(f"{location}: at least one assistant message is required")

    if expect_virgil_tags:
        assistant_messages = [message for message in messages if isinstance(message, dict) and message.get("role") == "assistant"]
        if not assistant_messages:
            return approx_tokens(messages), issues

        assistant = assistant_messages[-1]
        content = assistant.get("content", "")
        reasoning_content = assistant.get("reasoning_content")

        reasoning_match = REASONING_RE.search(content)
        if reasoning_match:
            reasoning_text = reasoning_match.group(1).strip()
        elif isinstance(reasoning_content, str):
            reasoning_text = reasoning_content.strip()
        else:
            reasoning_text = ""
            issues.append(f"{location}: assistant missing <reasoning> tags or reasoning_content")

        if min_reasoning_chars and len(reasoning_text) < min_reasoning_chars:
            issues.append(
                f"{location}: reasoning is too short: {len(reasoning_text)} chars < {min_reasoning_chars}"
            )

        answer_json = extract_answer(content)
        if answer_json is None:
            issues.append(f"{location}: assistant missing <answer>...</answer> block")
        else:
            try:
                parsed_answer = json.loads(answer_json)
            except json.JSONDecodeError as exc:
                issues.append(f"{location}: <answer> JSON does not parse: {exc}")
            else:
                if not isinstance(parsed_answer, dict):
                    issues.append(f"{location}: <answer> JSON must be an object")

    return approx_tokens(messages), issues


def validate_file(path: Path, expect_virgil_tags: bool, min_reasoning_chars: int) -> dict[str, Any]:
    issues: list[str] = []
    records = 0
    tokens = 0
    role_counter: Counter[str] = Counter()

    with path.open(encoding="utf-8") as f:
        for line_number, raw_line in enumerate(f, 1):
            line = raw_line.strip()
            if not line:
                continue

            location = f"{path.name}:{line_number}"
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                issues.append(f"{location}: invalid JSONL row: {exc}")
                continue

            if not isinstance(row, dict):
                issues.append(f"{location}: row must be a JSON object")
                continue

            extra_keys = set(row) - ALLOWED_ROOT_KEYS
            if extra_keys:
                issues.append(f"{location}: Fireworks export row has non-schema root keys: {sorted(extra_keys)}")

            if "weight" in row and not isinstance(row["weight"], (int, float)):
                issues.append(f"{location}: root weight must be numeric")

            row_tokens, row_issues = validate_messages(row, location, expect_virgil_tags, min_reasoning_chars)
            issues.extend(row_issues)
            tokens += row_tokens
            records += 1
            for message in row.get("messages", []):
                if isinstance(message, dict) and isinstance(message.get("role"), str):
                    role_counter[message["role"]] += 1

    return {
        "path": path,
        "records": records,
        "approx_tokens": tokens,
        "sha256": sha256_file(path),
        "roles": dict(sorted(role_counter.items())),
        "issues": issues,
    }


def load_manifest(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def check_manifest(manifest: dict[str, Any], results: list[dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    files = manifest.get("files", {})
    by_name = {result["path"].name: result for result in results}

    for split_name, file_meta in files.items():
        manifest_path = Path(file_meta.get("path", ""))
        result = by_name.get(manifest_path.name)
        if result is None:
            issues.append(f"manifest:{split_name}: exported file {manifest_path} was not validated")
            continue
        if file_meta.get("records") != result["records"]:
            issues.append(
                f"manifest:{split_name}: record count mismatch: "
                f"{file_meta.get('records')} != {result['records']}"
            )
        if file_meta.get("sha256") != result["sha256"]:
            issues.append(f"manifest:{split_name}: sha256 mismatch for {manifest_path}")

    coverage = manifest.get("coverage", {})
    eval_by_source = coverage.get("eval_by_source_book", {})
    if isinstance(eval_by_source, dict):
        empty_categories = [category for category, count in eval_by_source.items() if count <= 0]
        if empty_categories:
            issues.append(f"manifest: eval split missing categories: {empty_categories}")

    return issues


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate VIRGIL Fireworks SFT JSONL exports.")
    parser.add_argument("files", nargs="*", type=Path, default=DEFAULT_FILES)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_FIREWORKS_DIR / "manifest.json")
    parser.add_argument("--no-manifest", action="store_true")
    parser.add_argument("--no-virgil-tags", action="store_true")
    parser.add_argument("--min-reasoning-chars", type=int, default=200)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = [path if path.is_absolute() else ROOT / path for path in args.files]
    manifest_path = None if args.no_manifest else args.manifest
    if manifest_path is not None and not manifest_path.is_absolute():
        manifest_path = ROOT / manifest_path

    all_issues: list[str] = []
    results = []
    for path in paths:
        if not path.exists():
            all_issues.append(f"{path}: file does not exist")
            continue
        result = validate_file(
            path,
            expect_virgil_tags=not args.no_virgil_tags,
            min_reasoning_chars=args.min_reasoning_chars,
        )
        results.append(result)
        all_issues.extend(result["issues"])

    manifest = None
    if manifest_path is not None:
        if manifest_path.exists():
            manifest = load_manifest(manifest_path)
            all_issues.extend(check_manifest(manifest, results))
        else:
            all_issues.append(f"{manifest_path}: manifest file does not exist")

    print("=== Fireworks SFT Export Validation ===\n")
    for result in results:
        status = "OK" if not result["issues"] else f"{len(result['issues'])} issues"
        print(
            f"{result['path'].relative_to(ROOT)}  "
            f"{result['records']:5d} records  ~{result['approx_tokens']:7,d} tokens  {status}"
        )

    if manifest:
        coverage = manifest.get("coverage", {})
        eval_by_source = coverage.get("eval_by_source_book", {})
        print("\nEval coverage by source_book:")
        for source_book, count in sorted(eval_by_source.items()):
            print(f"  {source_book:32s} {count:4d}")

    if all_issues:
        print("\nIssues:")
        for issue in all_issues[:100]:
            print(f"  {issue}")
        if len(all_issues) > 100:
            print(f"  ... and {len(all_issues) - 100} more issues")
        return 1

    print("\nFireworks export validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
