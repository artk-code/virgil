#!/usr/bin/env python3
"""Run a small structural inference eval against Fireworks deployments.

The script intentionally keeps the eval simple:

- wait for one or more on-demand deployments to become READY
- sample identical held-out prompts for every deployment
- call Fireworks' OpenAI-compatible chat completions endpoint
- score VIRGIL structure: reasoning tags, answer tags, answer JSON validity
- optionally delete deployments after a successful run

It reads FIREWORKS_API_KEY from the environment and never writes secrets.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import random
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTROL_API = "https://api.fireworks.ai/v1"
INFERENCE_API = "https://api.fireworks.ai/inference/v1"
ANSWER_RE = re.compile(r"<answer>\s*(.*?)\s*</answer>", re.DOTALL)


class FireworksError(RuntimeError):
    pass


def api_key() -> str:
    key = os.environ.get("FIREWORKS_API_KEY", "").strip()
    if not key:
        raise SystemExit("FIREWORKS_API_KEY is not set.")
    return key


def control_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key()}"}


def json_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"}


def request_json(
    method: str,
    url: str,
    body: dict[str, Any] | None = None,
    timeout: int = 180,
) -> dict[str, Any]:
    data = None
    headers = control_headers()
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers = json_headers()
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise FireworksError(f"{method} {url} failed: HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise FireworksError(f"{method} {url} failed: {exc}") from exc
    if not payload:
        return {}
    return json.loads(payload.decode("utf-8"))


def deployment_id(name: str) -> str:
    if "/deployments/" in name:
        return name.rsplit("/deployments/", 1)[1]
    return name


def get_deployment(account_id: str, deployment: str) -> dict[str, Any]:
    dep_id = deployment_id(deployment)
    return request_json("GET", f"{CONTROL_API}/accounts/{account_id}/deployments/{dep_id}")


def delete_deployment(account_id: str, deployment: str) -> dict[str, Any]:
    dep_id = deployment_id(deployment)
    return request_json("DELETE", f"{CONTROL_API}/accounts/{account_id}/deployments/{dep_id}?ignoreChecks=true")


def compact_deployment(dep: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": dep.get("name"),
        "state": dep.get("state"),
        "status": dep.get("status"),
        "baseModel": dep.get("baseModel"),
        "deploymentShape": dep.get("deploymentShape"),
        "replicaCount": dep.get("replicaCount"),
        "desiredReplicaCount": dep.get("desiredReplicaCount"),
        "updateTime": dep.get("updateTime"),
    }


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def wait_ready(account_id: str, deployments: list[str], timeout_seconds: int, poll_seconds: int) -> dict[str, dict[str, Any]]:
    deadline = time.time() + timeout_seconds
    last: dict[str, dict[str, Any]] = {}
    while True:
        all_ready = True
        for dep in deployments:
            detail = get_deployment(account_id, dep)
            last[dep] = detail
            state = detail.get("state")
            if state == "FAILED":
                raise FireworksError(f"Deployment {dep} failed: {detail.get('status')}")
            if state != "READY":
                all_ready = False
        print(
            json.dumps(
                {
                    "time": datetime.now(timezone.utc).isoformat(),
                    "deployments": {dep: compact_deployment(detail) for dep, detail in last.items()},
                },
                indent=2,
            ),
            flush=True,
        )
        if all_ready:
            return last
        if time.time() >= deadline:
            raise FireworksError(f"Deployments did not become READY within {timeout_seconds}s.")
        time.sleep(poll_seconds)


def validated_message(messages: list[Any], index: int, role: str, line_number: int) -> dict[str, str]:
    try:
        message = messages[index]
    except IndexError as exc:
        raise ValueError(f"line {line_number}: missing {role!r} message at index {index}") from exc
    if not isinstance(message, dict):
        raise ValueError(f"line {line_number}: message {index} must be an object")
    if message.get("role") != role:
        raise ValueError(f"line {line_number}: message {index} must have role {role!r}")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError(f"line {line_number}: message {index} must have non-empty string content")
    return {"role": role, "content": content}


def load_cases(path: Path, limit: int, seed: int) -> list[dict[str, Any]]:
    if limit < 1:
        raise ValueError("--limit must be at least 1")

    rows = []
    with path.open(encoding="utf-8") as f:
        for line_number, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            messages = obj.get("messages", [])
            if not isinstance(messages, list):
                raise ValueError(f"line {line_number}: messages must be a list")

            prompt_messages = [
                validated_message(messages, 0, "system", line_number),
                validated_message(messages, 1, "user", line_number),
            ]
            assistant_message = validated_message(messages, 2, "assistant", line_number)
            meta = obj.get("meta") or {}
            if not isinstance(meta, dict):
                raise ValueError(f"line {line_number}: meta must be an object when present")
            case_hash = hashlib.sha256(
                json.dumps(prompt_messages, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()[:16]
            rows.append(
                {
                    "case_id": f"{path.name}:{line_number}:{case_hash}",
                    "line_number": line_number,
                    "messages": prompt_messages,
                    "target_assistant": assistant_message["content"],
                    "source_book": meta.get("source_book"),
                    "task": meta.get("task"),
                    "source_ids": meta.get("source_ids", []),
                }
            )
    if not rows:
        raise ValueError(f"No valid eval cases loaded from {path}")
    if limit >= len(rows):
        return rows
    rng = random.Random(seed)
    indexes = sorted(rng.sample(range(len(rows)), limit))
    return [rows[i] for i in indexes]


def answer_json(content: str) -> tuple[bool, Any]:
    match = ANSWER_RE.search(content)
    if not match:
        return False, None
    try:
        return True, json.loads(match.group(1))
    except json.JSONDecodeError:
        return False, None


def score_content(content: str) -> dict[str, Any]:
    has_reasoning_open = "<reasoning>" in content
    has_reasoning_close = "</reasoning>" in content
    has_answer_open = "<answer>" in content
    has_answer_close = "</answer>" in content
    answer_ok, answer_obj = answer_json(content)
    return {
        "has_reasoning_open": has_reasoning_open,
        "has_reasoning_close": has_reasoning_close,
        "has_answer_open": has_answer_open,
        "has_answer_close": has_answer_close,
        "answer_json_valid": answer_ok,
        "answer_keys": sorted(answer_obj.keys()) if isinstance(answer_obj, dict) else [],
        "char_count": len(content),
        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
    }


def chat_completion(model: str, messages: list[dict[str, str]], max_tokens: int, temperature: float, timeout: int) -> dict[str, Any]:
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    return request_json("POST", f"{INFERENCE_API}/chat/completions", body, timeout=timeout)


def eval_one_model(
    label: str,
    deployment: dict[str, Any],
    cases: list[dict[str, Any]],
    max_tokens: int,
    temperature: float,
    request_timeout: int,
) -> list[dict[str, Any]]:
    model_name = deployment["baseModel"]
    routed_model = f"{model_name}#{deployment['name']}"
    results = []
    for case_index, case in enumerate(cases, 1):
        started = time.time()
        try:
            response = chat_completion(
                routed_model,
                case["messages"],
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=request_timeout,
            )
            choices = response.get("choices") or []
            if not choices:
                raise FireworksError("chat completion response did not contain choices")
            choice = choices[0]
            if not isinstance(choice, dict):
                raise FireworksError("chat completion choice was not an object")
            content = choice.get("message", {}).get("content") or ""
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False)
            finish_reason = choice.get("finish_reason")
            response_id = response.get("id")
            response_model = response.get("model")
            error = None
        except Exception as exc:  # Keep going so one slow/failing model does not destroy the whole run.
            response = {}
            content = ""
            finish_reason = None
            response_id = None
            response_model = None
            error = str(exc)
        usage = response.get("usage", {}) if isinstance(response, dict) else {}
        results.append(
            {
                "label": label,
                "deployment": deployment["name"],
                "model": routed_model,
                "response_model": response_model,
                "response_id": response_id,
                "case_index": case_index,
                "case_id": case["case_id"],
                "eval_line_number": case["line_number"],
                "source_book": case["source_book"],
                "task": case["task"],
                "source_ids": case["source_ids"],
                "input_messages": case["messages"],
                "reference_content": case["target_assistant"],
                "reference_score": score_content(case["target_assistant"]),
                "latency_seconds": round(time.time() - started, 3),
                "usage": usage,
                "finish_reason": finish_reason,
                "error": error,
                "score": score_content(content),
                "content": content,
            }
        )
        print(
            json.dumps(
                {
                    "label": label,
                    "case": case_index,
                    "error": error,
                    "latency_seconds": results[-1]["latency_seconds"],
                    "finish_reason": finish_reason,
                    "score": results[-1]["score"],
                    "usage": usage,
                }
            ),
            flush=True,
        )
    return results


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_label: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        by_label.setdefault(result["label"], []).append(result)
    summary = {}
    for label, rows in by_label.items():
        ok_rows = [row for row in rows if not row.get("error")]
        latencies = [row["latency_seconds"] for row in ok_rows]
        prompt_tokens = sum(int(row.get("usage", {}).get("prompt_tokens", 0) or 0) for row in ok_rows)
        completion_tokens = sum(int(row.get("usage", {}).get("completion_tokens", 0) or 0) for row in ok_rows)
        total_tokens = sum(int(row.get("usage", {}).get("total_tokens", 0) or 0) for row in ok_rows)
        finish_reasons: dict[str, int] = {}
        for row in ok_rows:
            finish_reason = row.get("finish_reason") or "unknown"
            finish_reasons[finish_reason] = finish_reasons.get(finish_reason, 0) + 1
        summary[label] = {
            "cases": len(rows),
            "errors": sum(1 for row in rows if row.get("error")),
            "valid_reasoning_tags": sum(
                1
                for row in ok_rows
                if row["score"]["has_reasoning_open"] and row["score"]["has_reasoning_close"]
            ),
            "valid_answer_tags": sum(
                1 for row in ok_rows if row["score"]["has_answer_open"] and row["score"]["has_answer_close"]
            ),
            "valid_answer_json": sum(1 for row in ok_rows if row["score"]["answer_json_valid"]),
            "avg_latency_seconds": round(sum(latencies) / len(latencies), 3) if latencies else None,
            "max_latency_seconds": max(latencies) if latencies else None,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "finish_reasons": finish_reasons,
        }
    return summary


def parse_deployment_arg(raw: str) -> tuple[str, str]:
    if "=" in raw:
        label, dep = raw.split("=", 1)
        label = label.strip()
        dep = dep.strip()
        if not label or not dep:
            raise SystemExit(f"Invalid --deployment value: {raw!r}")
        return label, dep
    dep = deployment_id(raw)
    raw = raw.strip()
    if not dep or not raw:
        raise SystemExit(f"Invalid --deployment value: {raw!r}")
    return dep, raw


def validate_args(args: argparse.Namespace) -> None:
    positive_ints = {
        "--limit": args.limit,
        "--max-tokens": args.max_tokens,
        "--wait-timeout": args.wait_timeout,
        "--poll-seconds": args.poll_seconds,
        "--request-timeout": args.request_timeout,
        "--parallel-models": args.parallel_models,
    }
    for name, value in positive_ints.items():
        if value < 1:
            raise SystemExit(f"{name} must be at least 1")
    if args.temperature < 0:
        raise SystemExit("--temperature must be non-negative")


def validate_deployment_details(dep_args: list[tuple[str, str]], deployment_details: dict[str, dict[str, Any]]) -> None:
    for label, dep in dep_args:
        detail = deployment_details[dep]
        missing = [field for field in ("name", "baseModel") if not detail.get(field)]
        if missing:
            raise SystemExit(
                f"Deployment {label!r} is missing required field(s) {missing}: "
                f"{json.dumps(compact_deployment(detail), sort_keys=True)}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run VIRGIL inference eval against Fireworks deployments.")
    parser.add_argument("--account-id", default="artk011235")
    parser.add_argument("--deployment", action="append", required=True, help="label=deployment_id or deployment_id")
    parser.add_argument("--eval-file", type=Path, default=ROOT / "data/fireworks/virgil_fireworks_eval.jsonl")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/fireworks/inference_evals")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--max-tokens", type=int, default=2200)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--wait-timeout", type=int, default=1800)
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--request-timeout", type=int, default=600)
    parser.add_argument("--parallel-models", type=int, default=3)
    parser.add_argument("--delete-after", action="store_true")
    args = parser.parse_args()
    validate_args(args)

    dep_args = [parse_deployment_arg(raw) for raw in args.deployment]
    labels = [label for label, _ in dep_args]
    if len(labels) != len(set(labels)):
        raise SystemExit(f"Deployment labels must be unique: {labels}")

    eval_file = args.eval_file if args.eval_file.is_absolute() else ROOT / args.eval_file
    try:
        cases = load_cases(eval_file, args.limit, args.seed)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    if args.wait:
        deployment_details = wait_ready(
            args.account_id,
            [dep for _, dep in dep_args],
            timeout_seconds=args.wait_timeout,
            poll_seconds=args.poll_seconds,
        )
    else:
        deployment_details = {dep: get_deployment(args.account_id, dep) for _, dep in dep_args}
        not_ready = {dep: detail.get("state") for dep, detail in deployment_details.items() if detail.get("state") != "READY"}
        if not_ready:
            raise SystemExit(f"Deployments are not READY: {not_ready}")
    validate_deployment_details(dep_args, deployment_details)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results_path = args.output_dir / f"fireworks_inference_eval_{stamp}.jsonl"
    summary_path = args.output_dir / f"fireworks_inference_eval_{stamp}_summary.json"

    all_results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.parallel_models) as pool:
        futures = []
        for label, dep in dep_args:
            detail = deployment_details[dep]
            futures.append(
                pool.submit(
                    eval_one_model,
                    label,
                    detail,
                    cases,
                    args.max_tokens,
                    args.temperature,
                    args.request_timeout,
                )
            )
        for future in concurrent.futures.as_completed(futures):
            all_results.extend(future.result())

    all_results.sort(key=lambda row: (row["label"], row["case_index"]))
    with results_path.open("w", encoding="utf-8") as f:
        for result in all_results:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")

    summary = {
        "created_at": stamp,
        "eval_file": str(eval_file),
        "eval_file_sha256": file_sha256(eval_file),
        "case_count": len(cases),
        "case_ids": [case["case_id"] for case in cases],
        "max_tokens": args.max_tokens,
        "temperature": args.temperature,
        "deployments": {
            label: compact_deployment(deployment_details[dep]) for label, dep in dep_args
        },
        "summary": summarize(all_results),
        "results_path": str(results_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    deleted: dict[str, Any] = {}
    if args.delete_after:
        for label, dep in dep_args:
            try:
                deleted[label] = delete_deployment(args.account_id, dep)
            except Exception as exc:
                deleted[label] = {"error": str(exc)}
        summary["delete_after"] = deleted

    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({"summary_path": str(summary_path), **summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
