from __future__ import annotations

import json
import logging
import os
from typing import Any

import redis

log = logging.getLogger(__name__)


def redis_from_env() -> redis.Redis | None:
    url = os.environ.get("REDIS_URL", "").strip()
    if not url:
        log.warning("REDIS_URL not set; idle mode")
        return None
    return redis.Redis.from_url(url, decode_responses=True)


def ensure_group(client: redis.Redis, stream: str, group: str) -> None:
    try:
        client.xgroup_create(stream, group, id="0", mkstream=True)
    except redis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def read_from_group(
    client: redis.Redis,
    stream: str,
    group: str,
    consumer: str,
    block_ms: int,
    count: int,
) -> list[tuple[str, dict[str, str]]]:
    response = client.xreadgroup(
        groupname=group,
        consumername=consumer,
        streams={stream: ">"},
        count=count,
        block=block_ms,
    )
    if not response:
        return []
    _stream, messages = response[0]
    return messages


def parse_event_message(message_data: dict[str, str]) -> dict[str, Any]:
    payload = message_data.get("event", "{}")
    event = json.loads(payload)
    if not isinstance(event, dict):
        raise ValueError("event payload must be object")
    return event


def mark_dedupe(client: redis.Redis, event_id: str, ttl_seconds: int) -> bool:
    return bool(
        client.set(
            name=f"dedupe:event:{event_id}",
            value="1",
            nx=True,
            ex=max(60, ttl_seconds),
        )
    )
