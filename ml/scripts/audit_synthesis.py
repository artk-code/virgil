#!/usr/bin/env python3
"""
Audit all VIRGIL synthesis JSONL files for regressions, dangling records,
incomplete generations, missing metadata, and other issues.

Run this after killing subagents and before starting a new swarm wave.

Usage:
    python scripts/audit_synthesis.py
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
SYNTH_DIR = ROOT / "data" / "synthesis"

REQUIRED_META_FIELDS = ["task", "source_ids", "source_book", "split", "synthesized"]

def audit_file(path: Path) -> dict:
    """Audit a single synthesis JSONL file."""
    name = path.stem
    issues = []
    record_count = 0
    valid_records = 0
    task_counts = defaultdict(int)
    source_book_counts = defaultdict(int)

    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            record_count += 1

            try:
                ex = json.loads(line)
            except json.JSONDecodeError as e:
                issues.append(f"Line {lineno}: Invalid JSON - {e}")
                continue

            # Check messages structure
            messages = ex.get("messages", [])
            if not isinstance(messages, list) or len(messages) != 3:
                issues.append(f"Line {lineno}: messages must have exactly 3 entries (system + user + assistant)")
                continue

            roles = [m.get("role") for m in messages]
            if roles != ["system", "user", "assistant"]:
                issues.append(f"Line {lineno}: roles must be [system, user, assistant], got {roles}")
                continue

            # Check assistant content has <reasoning> and <answer>
            assistant_content = messages[2].get("content", "")
            if "<reasoning>" not in assistant_content or "<answer>" not in assistant_content:
                issues.append(f"Line {lineno}: assistant content missing <reasoning> or <answer> tags")

            # Check meta
            meta = ex.get("meta", {})
            if not isinstance(meta, dict):
                issues.append(f"Line {lineno}: meta must be an object")
                continue

            missing_fields = [f for f in REQUIRED_META_FIELDS if f not in meta]
            if missing_fields:
                issues.append(f"Line {lineno}: missing meta fields: {missing_fields}")

            if meta.get("synthesized") is not True:
                issues.append(f"Line {lineno}: synthesized should be true")

            source_book = meta.get("source_book")
            if source_book:
                source_book_counts[source_book] += 1

            task = meta.get("task")
            if task:
                task_counts[task] += 1

            valid_records += 1

    return {
        "file": name,
        "total_lines": record_count,
        "valid_records": valid_records,
        "issues": issues,
        "task_counts": dict(task_counts),
        "source_book_counts": dict(source_book_counts),
    }


def main():
    print("=== VIRGIL Synthesis Audit ===\n")

    files = sorted(SYNTH_DIR.glob("*.jsonl"))
    all_issues = []
    total_valid = 0
    total_records = 0

    per_file_summary = []

    for path in files:
        if "fragment" in path.name or "temp" in path.name:
            print(f"Skipping junk file: {path.name}")
            continue

        result = audit_file(path)
        per_file_summary.append(result)

        total_records += result["total_lines"]
        total_valid += result["valid_records"]

        status = "✅ OK" if not result["issues"] else f"⚠️  {len(result['issues'])} issues"
        print(f"{result['file']:32s} {result['valid_records']:4d} valid / {result['total_lines']:4d}  {status}")

        if result["issues"]:
            all_issues.extend([(result['file'], i) for i in result["issues"]])

    print("\n" + "=" * 70)
    print(f"TOTAL: {total_valid} valid records out of {total_records} lines\n")

    if all_issues:
        print("DETAILED ISSUES FOUND:\n")
        for fname, issue in all_issues[:50]:  # cap output
            print(f"  [{fname}] {issue}")
        if len(all_issues) > 50:
            print(f"  ... and {len(all_issues) - 50} more issues")
        print()
    else:
        print("✅ No issues found. All records look clean.\n")

    # Summary by source_book (should only be generalized topic names)
    print("=== Source Book Distribution (should be generalized topic names only) ===")
    source_totals = defaultdict(int)
    for r in per_file_summary:
        for sb, count in r["source_book_counts"].items():
            source_totals[sb] += count

    for sb, count in sorted(source_totals.items(), key=lambda x: -x[1]):
        print(f"  {sb:30s} {count:4d}")

    print("\nAudit complete.")
    return len(all_issues) == 0


if __name__ == "__main__":
    clean = main()
    sys.exit(0 if clean else 1)
