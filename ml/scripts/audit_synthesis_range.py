#!/usr/bin/env python3
"""Validate a physical line range in one VIRGIL synthesis JSONL file."""

import argparse
import json
import re
import sys
from pathlib import Path

EXPECTED_ROLES = ["system", "user", "assistant"]
REQUIRED_META_FIELDS = ["task", "source_ids", "source_book", "split", "synthesized"]
ANSWER_RE = re.compile(r"<answer>\s*(.*?)\s*</answer>", re.DOTALL)
REASONING_RE = re.compile(r"<reasoning>\s*(.*?)\s*</reasoning>", re.DOTALL)
CORE_ANSWER_KEYS = {"summary", "evidence", "hypotheses", "actions"}
FORBIDDEN_CONTENT_PHRASES = [
    "from the book",
    "book excerpt",
    "raw chunk",
    "parser output",
    "the chunk talks about",
    "the passage says",
    "page ",
    "chapter ",
    "excerpt",
]


def source_id_style_issue(source_id: str) -> str | None:
    patterns = [
        r"^owasp-\d{4}-a\d{2}$",
        r"^owasp-masvs-[a-z0-9_.+-]+$",
        r"^mitre-T\d{4}(?:\.\d{3})?$",
        r"^mitre-mobile-T\d{4}(?:\.\d{3})?$",
        r"^cisa-kev-cve-\d{4}-\d{4,7}$",
        r"^gtfobins-[a-z0-9_.+-]+$",
        r"^lolbas-[a-z0-9_.+-]+$",
        r"^sigma-[A-Za-z0-9_.:-]+$",
        r"^concept-[a-z0-9_.+-]+(?:-[a-z0-9_.+-]+)*$",
    ]
    if any(re.match(pattern, source_id) for pattern in patterns):
        return None
    return f"source_id has noncanonical style: {source_id!r}"


def validate_record(path: Path, lineno: int, line: str, args: argparse.Namespace) -> list[str]:
    location = f"{path.name}:{lineno}"
    expected_source_book = path.stem
    issues: list[str] = []

    try:
        record = json.loads(line)
    except json.JSONDecodeError as exc:
        return [f"{location}: invalid JSONL record: {exc}"]

    messages = record.get("messages")
    if not isinstance(messages, list) or len(messages) != 3:
        issues.append(f"{location}: messages must be exactly [system, user, assistant]")
        return issues

    roles = [msg.get("role") if isinstance(msg, dict) else None for msg in messages]
    if roles != EXPECTED_ROLES:
        issues.append(f"{location}: roles must be {EXPECTED_ROLES}, got {roles}")

    assistant = messages[2].get("content", "") if isinstance(messages[2], dict) else ""
    for tag in ("reasoning", "answer"):
        if f"<{tag}>" not in assistant or f"</{tag}>" not in assistant:
            issues.append(f"{location}: assistant missing complete <{tag}>...</{tag}> tags")

    answer_match = ANSWER_RE.search(assistant)
    answer_obj = None
    if answer_match:
        try:
            answer_obj = json.loads(answer_match.group(1))
        except json.JSONDecodeError as exc:
            issues.append(f"{location}: <answer> content is not valid JSON: {exc}")
    else:
        issues.append(f"{location}: cannot extract <answer>...</answer> block")

    reasoning_match = REASONING_RE.search(assistant)
    if args.min_reasoning_chars and reasoning_match:
        reasoning_text = reasoning_match.group(1).strip()
        if len(reasoning_text) < args.min_reasoning_chars:
            issues.append(
                f"{location}: <reasoning> is too short: "
                f"{len(reasoning_text)} chars < {args.min_reasoning_chars}"
            )

    if args.check_answer_schema and isinstance(answer_obj, dict):
        missing_core = sorted(CORE_ANSWER_KEYS - set(answer_obj))
        if missing_core:
            issues.append(f"{location}: <answer> JSON missing core keys: {missing_core}")

    if args.check_content_lint:
        searchable = "\n".join(
            msg.get("content", "") for msg in messages if isinstance(msg, dict)
        ).lower()
        for phrase in FORBIDDEN_CONTENT_PHRASES:
            if phrase in searchable:
                issues.append(f"{location}: forbidden/generated-content lint phrase: {phrase!r}")

    meta = record.get("meta")
    if not isinstance(meta, dict):
        issues.append(f"{location}: meta must be an object")
        return issues

    missing = [field for field in REQUIRED_META_FIELDS if field not in meta]
    if missing:
        issues.append(f"{location}: missing meta fields: {missing}")

    if meta.get("source_book") != expected_source_book:
        issues.append(
            f"{location}: meta.source_book must equal file stem {expected_source_book!r}, "
            f"got {meta.get('source_book')!r}"
        )
    if meta.get("synthesized") is not True:
        issues.append(f"{location}: meta.synthesized must be true")
    if meta.get("split") != "train":
        issues.append(f"{location}: meta.split must be 'train'")

    source_ids = meta.get("source_ids")
    if not isinstance(source_ids, list) or not source_ids:
        issues.append(f"{location}: meta.source_ids must be a non-empty list")
    elif args.check_source_ids:
        for source_id in source_ids:
            if not isinstance(source_id, str):
                issues.append(f"{location}: source_id must be a string, got {type(source_id).__name__}")
                continue
            style_issue = source_id_style_issue(source_id)
            if style_issue:
                issues.append(f"{location}: {style_issue}")

    return issues


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="JSONL file to validate")
    parser.add_argument("--start-line", type=int, required=True, help="1-based physical line to start at")
    parser.add_argument("--end-line", type=int, help="1-based physical line to stop at, inclusive")
    parser.add_argument("--check-source-ids", action="store_true")
    parser.add_argument("--check-content-lint", action="store_true")
    parser.add_argument("--check-answer-schema", action="store_true")
    parser.add_argument("--min-reasoning-chars", type=int, default=0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    path = args.path
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 2
    if args.start_line < 1:
        print("--start-line must be >= 1", file=sys.stderr)
        return 2
    if args.end_line is not None and args.end_line < args.start_line:
        print("--end-line must be >= --start-line", file=sys.stderr)
        return 2

    checked = 0
    issues: list[str] = []
    with path.open(encoding="utf-8") as f:
        for lineno, raw_line in enumerate(f, 1):
            if lineno < args.start_line:
                continue
            if args.end_line is not None and lineno > args.end_line:
                break
            line = raw_line.strip()
            if not line:
                continue
            checked += 1
            issues.extend(validate_record(path, lineno, line, args))

    print(f"{path}: checked {checked} non-empty records in physical line range")
    if issues:
        print("\nDETAILED ISSUES FOUND:\n")
        for issue in issues:
            print(f"  {issue}")
        return 1

    print("Range audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
