#!/usr/bin/env python3
"""
Minimal Fireworks SFT REST helper for VIRGIL.

This is a fallback for environments where firectl is unavailable. It reads
FIREWORKS_API_KEY from the environment and supports:

- listing accessible accounts
- creating/uploading/validating JSONL datasets
- creating and checking supervised fine-tuning jobs

The API key is never written to disk by this script.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = "https://api.fireworks.ai/v1"


class FireworksApiError(RuntimeError):
    pass


def api_key() -> str:
    key = os.environ.get("FIREWORKS_API_KEY", "").strip()
    if not key:
        raise SystemExit("FIREWORKS_API_KEY is not set.")
    return key


def normalize_account_id(account_id: str) -> str:
    account_id = account_id.strip()
    if account_id.startswith("accounts/"):
        return account_id.split("/", 1)[1]
    return account_id


def auth_headers(content_type: str | None = "application/json") -> dict[str, str]:
    headers = {"Authorization": f"Bearer {api_key()}"}
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def request_json(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{API_ROOT}{path}",
        data=data,
        method=method,
        headers=headers or auth_headers(),
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise FireworksApiError(f"{method} {path} failed: HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise FireworksApiError(f"{method} {path} failed: {exc}") from exc

    if not payload:
        return {}
    return json.loads(payload.decode("utf-8"))


def multipart_upload(path: str, file_path: Path) -> dict[str, Any]:
    boundary = f"----virgil-fireworks-{uuid.uuid4().hex}"
    filename = file_path.name
    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    file_bytes = file_path.read_bytes()

    prefix = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {mime_type}\r\n\r\n"
    ).encode("utf-8")
    suffix = f"\r\n--{boundary}--\r\n".encode("utf-8")
    data = prefix + file_bytes + suffix

    headers = auth_headers(content_type=f"multipart/form-data; boundary={boundary}")
    headers["Content-Length"] = str(len(data))
    req = urllib.request.Request(
        f"{API_ROOT}{path}",
        data=data,
        method="POST",
        headers=headers,
    )

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            payload = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise FireworksApiError(f"POST {path} upload failed: HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise FireworksApiError(f"POST {path} upload failed: {exc}") from exc

    if not payload:
        return {}
    return json.loads(payload.decode("utf-8"))


def count_jsonl_records(file_path: Path) -> int:
    records = 0
    with file_path.open(encoding="utf-8") as f:
        for raw_line in f:
            if raw_line.strip():
                records += 1
    return records


def compact_account(account: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": account.get("name"),
        "displayName": account.get("displayName"),
        "state": account.get("state"),
        "suspendState": account.get("suspendState"),
        "status": account.get("status", {}),
    }


def list_accounts(_args: argparse.Namespace) -> int:
    response = request_json("GET", "/accounts")
    accounts = [compact_account(account) for account in response.get("accounts", [])]
    print(json.dumps({"accounts": accounts, "totalSize": response.get("totalSize")}, indent=2))
    return 0


def get_dataset(args: argparse.Namespace) -> int:
    account_id = normalize_account_id(args.account_id)
    dataset_id = args.dataset_id
    response = request_json("GET", f"/accounts/{account_id}/datasets/{dataset_id}")
    print(json.dumps(response, indent=2))
    return 0


def create_upload_dataset(args: argparse.Namespace) -> int:
    account_id = normalize_account_id(args.account_id)
    file_path = args.file if args.file.is_absolute() else ROOT / args.file
    if not file_path.exists():
        raise SystemExit(f"Dataset file does not exist: {file_path}")

    example_count = count_jsonl_records(file_path)
    dataset_id = args.dataset_id
    display_name = args.display_name or dataset_id
    create_body = {
        "datasetId": dataset_id,
        "dataset": {
            "displayName": display_name,
            "exampleCount": str(example_count),
            "userUploaded": {},
            "format": "CHAT",
        },
    }

    created = request_json("POST", f"/accounts/{account_id}/datasets", create_body)
    print(
        json.dumps(
            {
                "created_dataset": created.get("name", f"accounts/{account_id}/datasets/{dataset_id}"),
                "state": created.get("state"),
                "exampleCount": created.get("exampleCount"),
            },
            indent=2,
        )
    )

    uploaded = multipart_upload(f"/accounts/{account_id}/datasets/{dataset_id}:upload", file_path)
    print(json.dumps({"uploaded": uploaded}, indent=2))

    validated = request_json("POST", f"/accounts/{account_id}/datasets/{dataset_id}:validateUpload", {})
    print(json.dumps({"validated": validated}, indent=2))

    if args.wait:
        wait_for_dataset_ready(account_id, dataset_id, timeout_seconds=args.timeout)

    return 0


def wait_for_dataset_ready(account_id: str, dataset_id: str, timeout_seconds: int) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last = {}
    while time.time() < deadline:
        last = request_json("GET", f"/accounts/{account_id}/datasets/{dataset_id}")
        state = last.get("state")
        status = last.get("status", {})
        print(
            json.dumps(
                {
                    "dataset": last.get("name"),
                    "state": state,
                    "status": status,
                    "estimatedTokenCount": last.get("estimatedTokenCount"),
                    "exampleCount": last.get("exampleCount"),
                },
                indent=2,
            )
        )
        if state == "READY":
            return last
        time.sleep(10)
    raise FireworksApiError(f"Dataset {dataset_id} did not become READY within {timeout_seconds}s. Last: {last}")


def create_sft_job(args: argparse.Namespace) -> int:
    account_id = normalize_account_id(args.account_id)
    dataset = args.dataset
    eval_dataset = args.evaluation_dataset
    if not dataset.startswith("accounts/"):
        dataset = f"accounts/{account_id}/datasets/{dataset}"
    if eval_dataset and not eval_dataset.startswith("accounts/"):
        eval_dataset = f"accounts/{account_id}/datasets/{eval_dataset}"

    query = urllib.parse.urlencode({"supervisedFineTuningJobId": args.job_id})
    body: dict[str, Any] = {
        "dataset": dataset,
        "displayName": args.display_name or args.job_id,
        "outputModel": args.output_model,
        "baseModel": args.base_model,
        "epochs": args.epochs,
        "earlyStop": args.early_stop,
        "evalAutoCarveout": False,
    }
    if args.lora_rank is not None:
        body["loraRank"] = args.lora_rank
    if eval_dataset:
        body["evaluationDataset"] = eval_dataset
    if args.max_context_length:
        body["maxContextLength"] = args.max_context_length
    if args.learning_rate:
        body["learningRate"] = args.learning_rate

    response = request_json("POST", f"/accounts/{account_id}/supervisedFineTuningJobs?{query}", body)
    print(json.dumps(response, indent=2))
    return 0


def get_sft_job(args: argparse.Namespace) -> int:
    account_id = normalize_account_id(args.account_id)
    response = request_json("GET", f"/accounts/{account_id}/supervisedFineTuningJobs/{args.job_id}")
    print(json.dumps(response, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fireworks SFT REST helper for VIRGIL.")
    subparsers = parser.add_subparsers(required=True)

    accounts_parser = subparsers.add_parser("list-accounts")
    accounts_parser.set_defaults(func=list_accounts)

    dataset_parser = subparsers.add_parser("upload-dataset")
    dataset_parser.add_argument("--account-id", required=True)
    dataset_parser.add_argument("--dataset-id", required=True)
    dataset_parser.add_argument("--display-name")
    dataset_parser.add_argument("--file", type=Path, required=True)
    dataset_parser.add_argument("--wait", action="store_true")
    dataset_parser.add_argument("--timeout", type=int, default=600)
    dataset_parser.set_defaults(func=create_upload_dataset)

    get_dataset_parser = subparsers.add_parser("get-dataset")
    get_dataset_parser.add_argument("--account-id", required=True)
    get_dataset_parser.add_argument("--dataset-id", required=True)
    get_dataset_parser.set_defaults(func=get_dataset)

    sft_parser = subparsers.add_parser("create-sft-job")
    sft_parser.add_argument("--account-id", required=True)
    sft_parser.add_argument("--job-id", required=True)
    sft_parser.add_argument("--display-name")
    sft_parser.add_argument("--base-model", required=True)
    sft_parser.add_argument("--dataset", required=True)
    sft_parser.add_argument("--evaluation-dataset")
    sft_parser.add_argument("--output-model", required=True)
    sft_parser.add_argument("--epochs", type=int, default=1)
    sft_parser.add_argument("--lora-rank", type=int, default=None)
    sft_parser.add_argument("--max-context-length", type=int)
    sft_parser.add_argument("--learning-rate", type=float)
    sft_parser.add_argument("--early-stop", action=argparse.BooleanOptionalAction, default=False)
    sft_parser.set_defaults(func=create_sft_job)

    get_sft_parser = subparsers.add_parser("get-sft-job")
    get_sft_parser.add_argument("--account-id", required=True)
    get_sft_parser.add_argument("--job-id", required=True)
    get_sft_parser.set_defaults(func=get_sft_job)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except FireworksApiError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
