from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import redis


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_analysis(
    event: dict[str, Any],
    rule_hits: list[str],
    score: float,
    severity: str,
    explanation: str,
) -> dict[str, Any]:
    return {
        "analysis_id": str(uuid4()),
        "event_id": str(event.get("event_id", "")),
        "trace_id": str(event.get("trace_id", "")),
        "host_id": str(event.get("host_id", "")),
        "score": score,
        "severity": severity,
        "rule_hits": rule_hits,
        "explanation": explanation,
        "analyzed_at": now_iso(),
    }


def publish_analysis(client: redis.Redis, stream: str, analysis: dict[str, Any]) -> str:
    return str(client.xadd(stream, {"analysis": json.dumps(analysis)}))


def publish_alert(client: redis.Redis, stream: str, analysis: dict[str, Any]) -> str:
    alert = {
        "alert_id": str(uuid4()),
        "analysis_id": analysis["analysis_id"],
        "event_id": analysis["event_id"],
        "trace_id": analysis["trace_id"],
        "host_id": analysis["host_id"],
        "severity": analysis["severity"],
        "title": f"Security finding ({analysis['severity']})",
        "created_at": now_iso(),
    }
    return str(client.xadd(stream, {"alert": json.dumps(alert)}))


def publish_dlq(
    client: redis.Redis,
    stream: str,
    stream_name: str,
    stream_id: str,
    reason: str,
    payload: dict[str, str],
) -> str:
    item = {
        "stream": stream_name,
        "stream_id": stream_id,
        "reason": reason,
        "payload": payload,
        "ts": now_iso(),
    }
    return str(client.xadd(stream, {"dlq": json.dumps(item)}))
