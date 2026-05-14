from __future__ import annotations

import json
import logging
import time
from typing import Any

import redis

from config import load_transform_config
from storage import (
    connect_postgres,
    read_checkpoint,
    upsert_event,
    upsert_finding,
    write_checkpoint,
)

log = logging.getLogger(__name__)


def _consume_stream(
    redis_client: redis.Redis,
    conn,
    stream_name: str,
    payload_field: str,
    consumer_name: str,
    batch_size: int,
) -> int:
    start_id = read_checkpoint(conn, stream_name, consumer_name)
    rows = redis_client.xrange(stream_name, min=start_id, max="+", count=batch_size)
    if not rows:
        return 0

    moved = 0
    latest_id = start_id
    for stream_id, fields in rows:
        if stream_id == start_id:
            continue
        payload_raw = fields.get(payload_field, "{}")
        try:
            payload = json.loads(payload_raw)
        except json.JSONDecodeError:
            log.warning("Skipping malformed payload from %s id=%s", stream_name, stream_id)
            write_checkpoint(conn, stream_name, consumer_name, stream_id)
            continue

        if payload_field == "event":
            upsert_event(conn, payload)
        else:
            upsert_finding(conn, payload)
        latest_id = stream_id
        moved += 1

    if latest_id != start_id:
        write_checkpoint(conn, stream_name, consumer_name, latest_id)
    return moved


def run_once() -> tuple[int, int]:
    cfg = load_transform_config()
    redis_client = redis.Redis.from_url(cfg.redis_url, decode_responses=True)
    with connect_postgres(cfg.database_url) as conn:
        with conn.transaction():
            events_moved = _consume_stream(
                redis_client,
                conn,
                cfg.events_stream,
                "event",
                cfg.transform_consumer,
                cfg.batch_size,
            )
            analysis_moved = _consume_stream(
                redis_client,
                conn,
                cfg.analysis_stream,
                "analysis",
                f"{cfg.transform_consumer}-analysis",
                cfg.batch_size,
            )
    return events_moved, analysis_moved


def main() -> None:
    logging.basicConfig(level=logging.getLevelName("INFO"))
    cfg = load_transform_config()
    while True:
        try:
            events_moved, analysis_moved = run_once()
            log.info(
                "transform cycle complete events=%s analysis=%s",
                events_moved,
                analysis_moved,
            )
        except Exception:  # pragma: no cover - top-level loop guard
            log.exception("transform cycle failed")
        if cfg.run_once:
            return
        time.sleep(cfg.interval_seconds)


if __name__ == "__main__":
    main()
