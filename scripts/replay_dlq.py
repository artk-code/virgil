#!/usr/bin/env python3
"""Replay messages from the DLQ stream back to a target stream.

Safe by default: this command runs in dry-run mode unless --execute is provided.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass

import redis

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKER_PATH = os.path.join(ROOT, "python-worker")
if WORKER_PATH not in sys.path:
    sys.path.insert(0, WORKER_PATH)

from dlq_replay import parse_dlq_candidate, resolve_destination_stream  # noqa: E402


@dataclass
class ReplayStats:
    scanned: int = 0
    eligible: int = 0
    replayed: int = 0
    skipped: int = 0
    failed: int = 0
    deleted: int = 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Replay DLQ entries to a stream")
    p.add_argument("--redis-url", default=os.environ.get("REDIS_URL", "").strip())
    p.add_argument("--dlq-stream", default=os.environ.get("SECURITY_DLQ_STREAM", "security_dlq"))
    p.add_argument("--target-stream", default="", help="Optional forced destination stream")
    p.add_argument(
        "--fallback-stream",
        default=os.environ.get("SECURITY_EVENTS_STREAM", "security_events"),
        help="Used when a DLQ entry source stream is missing or equals DLQ stream",
    )
    p.add_argument("--from-id", default="-", help="XRANGE start id (default: '-')")
    p.add_argument("--limit", type=int, default=100, help="Max DLQ entries to inspect")
    p.add_argument("--execute", action="store_true", help="Perform replay writes")
    p.add_argument(
        "--delete-replayed",
        action="store_true",
        help="Delete successfully replayed entries from DLQ stream",
    )
    # Backward-compatible alias for operator wording.
    p.add_argument(
        "--ack-replayed",
        action="store_true",
        help="Alias for --delete-replayed in stream context",
    )
    return p


def _validate_args(args: argparse.Namespace) -> None:
    if not args.redis_url:
        raise ValueError("REDIS_URL is required (pass --redis-url or set REDIS_URL)")
    if args.limit < 1:
        raise ValueError("--limit must be >= 1")


def run(args: argparse.Namespace) -> int:
    _validate_args(args)
    if args.ack_replayed:
        args.delete_replayed = True

    mode = "execute" if args.execute else "dry-run"
    print(f"mode={mode} dlq_stream={args.dlq_stream} from_id={args.from_id} limit={args.limit}")
    print(f"target_stream={args.target_stream or '(from entry)'} fallback_stream={args.fallback_stream}")

    client = redis.Redis.from_url(args.redis_url, decode_responses=True)
    entries = client.xrange(args.dlq_stream, min=args.from_id, max="+", count=args.limit)
    stats = ReplayStats(scanned=len(entries))

    for stream_id, fields in entries:
        try:
            candidate = parse_dlq_candidate(stream_id, fields)
        except Exception as exc:
            stats.skipped += 1
            print(f"skip stream_id={stream_id} reason={exc}")
            continue

        stats.eligible += 1
        destination = resolve_destination_stream(
            candidate,
            forced_stream=args.target_stream,
            fallback_stream=args.fallback_stream,
            dlq_stream=args.dlq_stream,
        )
        print(f"eligible stream_id={stream_id} source={candidate.source_stream} destination={destination}")

        if not args.execute:
            continue

        try:
            new_id = client.xadd(destination, candidate.payload)
            stats.replayed += 1
            print(f"replayed stream_id={stream_id} new_id={new_id} destination={destination}")
            if args.delete_replayed:
                deleted = client.xdel(args.dlq_stream, stream_id)
                if deleted:
                    stats.deleted += 1
        except Exception as exc:
            stats.failed += 1
            print(f"failed stream_id={stream_id} reason={exc}")

    print(
        "summary "
        f"scanned={stats.scanned} eligible={stats.eligible} replayed={stats.replayed} "
        f"skipped={stats.skipped} failed={stats.failed} deleted={stats.deleted}"
    )
    return 0 if stats.failed == 0 else 1


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return run(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except redis.RedisError as exc:
        print(f"redis_error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
