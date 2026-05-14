from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReplayCandidate:
    stream_id: str
    source_stream: str
    payload: dict[str, str]


def parse_dlq_candidate(stream_id: str, fields: dict[str, str]) -> ReplayCandidate:
    raw = fields.get("dlq", "").strip()
    if not raw:
        raise ValueError("missing dlq field")
    item = json.loads(raw)
    if not isinstance(item, dict):
        raise ValueError("dlq entry must be object")

    source_stream = str(item.get("stream", "")).strip()
    if not source_stream:
        raise ValueError("dlq entry missing source stream")

    payload_any = item.get("payload")
    if not isinstance(payload_any, dict):
        raise ValueError("dlq payload must be object")
    payload = sanitize_payload(payload_any)
    if "event" not in payload:
        raise ValueError("dlq payload missing event field")

    return ReplayCandidate(stream_id=stream_id, source_stream=source_stream, payload=payload)


def sanitize_payload(payload: dict[str, Any]) -> dict[str, str]:
    clean: dict[str, str] = {}
    for key, value in payload.items():
        if value is None:
            continue
        if isinstance(value, str):
            clean[str(key)] = value
            continue
        clean[str(key)] = json.dumps(value, separators=(",", ":"))
    return clean


def resolve_destination_stream(
    candidate: ReplayCandidate,
    *,
    forced_stream: str | None,
    fallback_stream: str,
    dlq_stream: str,
) -> str:
    forced = (forced_stream or "").strip()
    if forced:
        return forced
    source = candidate.source_stream.strip()
    if source and source != dlq_stream:
        return source
    return fallback_stream
