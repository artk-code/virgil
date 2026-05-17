#!/usr/bin/env python3
"""
Strict audit for VIRGIL synthesis JSONL files.

This is intended as a pre-swarm gate. It validates structural correctness that
the lighter registry/audit path intentionally tolerates, including closing
reasoning/answer tags and parseable JSON inside <answer>...</answer>.
"""

import json
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYNTH_DIR = ROOT / "data" / "synthesis"

EXPECTED_ROLES = ["system", "user", "assistant"]
REQUIRED_META_FIELDS = ["task", "source_ids", "source_book", "split", "synthesized"]
ANSWER_RE = re.compile(r"<answer>\s*(.*?)\s*</answer>", re.DOTALL)
REASONING_RE = re.compile(r"<reasoning>\s*(.*?)\s*</reasoning>", re.DOTALL)
FORBIDDEN_CONTENT_PHRASES = [
    "from the book",
    "book excerpt",
    "raw chunk",
    "parser output",
    "the chunk talks about",
    "the passage says",
]
CORE_ANSWER_KEYS = {"summary", "evidence", "hypotheses", "actions"}


def source_id_style_issue(source_id: str) -> str | None:
    """Return an issue string when a source_id does not match current conventions."""
    patterns = [
        r"^owasp-\d{4}-a\d{2}$",
        r"^mitre-T\d{4}(?:\.\d{3})?$",
        r"^cve-\d{4}-\d{4,7}$",
        r"^ghsa-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}$",
        r"^cisa-kev-cve-\d{4}-\d{4,7}$",
        r"^gtfobins-[a-z0-9_.+-]+$",
        r"^lolbas-[a-z0-9_.+-]+$",
        r"^sigma-[A-Za-z0-9_.:-]+$",
        r"^concept-[a-z0-9_.+-]+(?:-[a-z0-9_.+-]+)*$",
    ]
    if any(re.match(pattern, source_id) for pattern in patterns):
        return None
    return f"source_id has noncanonical style: {source_id!r}"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def audit_file(
    path: Path,
    check_source_ids: bool,
    check_duplicates: bool,
    min_reasoning_chars: int,
    check_answer_schema: bool,
    check_content_lint: bool,
    seen_user_prompts: dict[str, str],
    seen_answer_json: dict[str, str],
    seen_task_sources: dict[str, str],
) -> tuple[int, list[str]]:
    expected_source_book = path.stem
    valid_records = 0
    issues: list[str] = []

    with path.open(encoding="utf-8") as f:
        for lineno, raw_line in enumerate(f, 1):
            line = raw_line.strip()
            if not line:
                continue

            location = f"{path.name}:{lineno}"

            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                issues.append(f"{location}: invalid JSONL record: {exc}")
                continue

            messages = record.get("messages")
            if not isinstance(messages, list) or len(messages) != 3:
                issues.append(f"{location}: messages must be exactly [system, user, assistant]")
                continue

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
            if min_reasoning_chars and reasoning_match:
                reasoning_text = reasoning_match.group(1).strip()
                if len(reasoning_text) < min_reasoning_chars:
                    issues.append(
                        f"{location}: <reasoning> is too short: "
                        f"{len(reasoning_text)} chars < {min_reasoning_chars}"
                    )

            if check_answer_schema and isinstance(answer_obj, dict):
                missing_core = sorted(CORE_ANSWER_KEYS - set(answer_obj))
                if missing_core:
                    issues.append(f"{location}: <answer> JSON missing core keys: {missing_core}")

            if check_content_lint:
                searchable_parts = [msg.get("content", "") for msg in messages if isinstance(msg, dict)]
                searchable = "\n".join(searchable_parts).lower()
                for phrase in FORBIDDEN_CONTENT_PHRASES:
                    if phrase in searchable:
                        issues.append(f"{location}: forbidden/generated-content lint phrase: {phrase!r}")

            meta = record.get("meta")
            if not isinstance(meta, dict):
                issues.append(f"{location}: meta must be an object")
                continue

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
            elif check_source_ids:
                for source_id in source_ids:
                    if not isinstance(source_id, str):
                        issues.append(f"{location}: source_id must be a string, got {type(source_id).__name__}")
                        continue
                    style_issue = source_id_style_issue(source_id)
                    if style_issue:
                        issues.append(f"{location}: {style_issue}")

            if check_duplicates:
                user_content = messages[1].get("content", "") if isinstance(messages[1], dict) else ""
                user_hash = sha256_text(user_content)
                if user_hash in seen_user_prompts:
                    issues.append(f"{location}: duplicate user prompt also seen at {seen_user_prompts[user_hash]}")
                else:
                    seen_user_prompts[user_hash] = location

                if answer_match:
                    answer_hash = sha256_text(answer_match.group(1).strip())
                    if answer_hash in seen_answer_json:
                        issues.append(f"{location}: duplicate <answer> JSON also seen at {seen_answer_json[answer_hash]}")
                    else:
                        seen_answer_json[answer_hash] = location

                if isinstance(source_ids, list):
                    task_sources_key = json.dumps(
                        [meta.get("task"), sorted(str(source_id) for source_id in source_ids)],
                        sort_keys=True,
                    )
                    if task_sources_key in seen_task_sources:
                        issues.append(
                            f"{location}: duplicate meta.task + source_ids also seen at "
                            f"{seen_task_sources[task_sources_key]}"
                        )
                    else:
                        seen_task_sources[task_sources_key] = location

            valid_records += 1

    return valid_records, issues


def main() -> int:
    check_source_ids = "--check-source-ids" in sys.argv
    check_duplicates = "--check-duplicates" in sys.argv
    check_answer_schema = "--check-answer-schema" in sys.argv
    check_content_lint = "--check-content-lint" in sys.argv
    min_reasoning_chars = 0
    if "--min-reasoning-chars" in sys.argv:
        try:
            min_reasoning_chars = int(sys.argv[sys.argv.index("--min-reasoning-chars") + 1])
        except (IndexError, ValueError):
            print("--min-reasoning-chars requires an integer value", file=sys.stderr)
            return 2

    files = sorted(SYNTH_DIR.glob("*.jsonl"))
    all_issues: list[str] = []
    total_records = 0
    seen_user_prompts: dict[str, str] = {}
    seen_answer_json: dict[str, str] = {}
    seen_task_sources: dict[str, str] = {}

    print("=== VIRGIL Strict Synthesis Audit ===\n")
    for path in files:
        if path.stem.startswith(("phi1_fragment", "temp", "fragment")):
            print(f"Skipping junk file: {path.name}")
            continue

        records, issues = audit_file(
            path,
            check_source_ids,
            check_duplicates,
            min_reasoning_chars,
            check_answer_schema,
            check_content_lint,
            seen_user_prompts,
            seen_answer_json,
            seen_task_sources,
        )
        total_records += records
        all_issues.extend(issues)
        status = "OK" if not issues else f"{len(issues)} issues"
        print(f"{path.stem:32s} {records:4d} records  {status}")

    print("\n" + "=" * 70)
    print(f"TOTAL: {total_records} non-empty records checked")

    if all_issues:
        print("\nDETAILED ISSUES FOUND:\n")
        for issue in all_issues[:100]:
            print(f"  {issue}")
        if len(all_issues) > 100:
            print(f"  ... and {len(all_issues) - 100} more issues")
        return 1

    print("\nStrict audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
