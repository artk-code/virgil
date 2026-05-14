from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import psycopg


def now_dt() -> datetime:
    return datetime.now(timezone.utc)


def connect_postgres(database_url: str) -> psycopg.Connection:
    return psycopg.connect(database_url)


def upsert_host(conn: psycopg.Connection, host_id: str) -> None:
    conn.execute(
        """
        INSERT INTO hosts (host_id, first_seen_at, last_seen_at)
        VALUES (%s, NOW(), NOW())
        ON CONFLICT (host_id) DO UPDATE SET last_seen_at = EXCLUDED.last_seen_at
        """,
        (host_id,),
    )


def upsert_event(conn: psycopg.Connection, event: dict[str, Any]) -> None:
    upsert_host(conn, str(event.get("host_id", "unknown-host")))
    conn.execute(
        """
        INSERT INTO security_events (
            event_id, trace_id, host_id, agent_id, source_type,
            event_type, severity, ts, raw, normalized, tags, ingested_at
        )
        VALUES (
            %(event_id)s, %(trace_id)s, %(host_id)s, %(agent_id)s, %(source_type)s,
            %(event_type)s, %(severity)s, %(ts)s, %(raw)s::jsonb, %(normalized)s::jsonb,
            %(tags)s::jsonb, NOW()
        )
        ON CONFLICT (event_id) DO UPDATE SET
            severity = EXCLUDED.severity,
            normalized = EXCLUDED.normalized,
            tags = EXCLUDED.tags,
            ingested_at = NOW()
        """,
        {
            "event_id": str(event.get("event_id", "")),
            "trace_id": str(event.get("trace_id", "")),
            "host_id": str(event.get("host_id", "unknown-host")),
            "agent_id": str(event.get("agent_id", "unknown-agent")),
            "source_type": str(event.get("source_type", "unknown")),
            "event_type": str(event.get("event_type", "unknown")),
            "severity": str(event.get("severity", "low")),
            "ts": str(event.get("ts", datetime.now(timezone.utc).isoformat())),
            "raw": json.dumps(event.get("raw", {})),
            "normalized": json.dumps(event.get("normalized", {})),
            "tags": json.dumps(event.get("tags", [])),
        },
    )


def upsert_finding(conn: psycopg.Connection, analysis: dict[str, Any]) -> None:
    host_id = str(analysis.get("host_id", "unknown-host"))
    upsert_host(conn, host_id)
    conn.execute(
        """
        INSERT INTO security_findings (
            analysis_id, event_id, trace_id, host_id, score, severity,
            rule_hits, explanation, analyzed_at
        )
        VALUES (
            %(analysis_id)s, %(event_id)s, %(trace_id)s, %(host_id)s,
            %(score)s, %(severity)s, %(rule_hits)s::jsonb, %(explanation)s, %(analyzed_at)s
        )
        ON CONFLICT (analysis_id) DO UPDATE SET
            score = EXCLUDED.score,
            severity = EXCLUDED.severity,
            rule_hits = EXCLUDED.rule_hits,
            explanation = EXCLUDED.explanation,
            analyzed_at = EXCLUDED.analyzed_at
        """,
        {
            "analysis_id": str(analysis.get("analysis_id", "")),
            "event_id": str(analysis.get("event_id", "")),
            "trace_id": str(analysis.get("trace_id", "")),
            "host_id": host_id,
            "score": float(analysis.get("score", 0.0)),
            "severity": str(analysis.get("severity", "low")),
            "rule_hits": json.dumps(analysis.get("rule_hits", [])),
            "explanation": str(analysis.get("explanation", "")),
            "analyzed_at": str(analysis.get("analyzed_at", datetime.now(timezone.utc).isoformat())),
        },
    )


def read_checkpoint(conn: psycopg.Connection, stream: str, consumer: str) -> str:
    row = conn.execute(
        """
        SELECT last_stream_id
        FROM etl_checkpoints
        WHERE stream_name = %s AND consumer_name = %s
        """,
        (stream, consumer),
    ).fetchone()
    if not row:
        return "0-0"
    return str(row[0])


def write_checkpoint(conn: psycopg.Connection, stream: str, consumer: str, stream_id: str) -> None:
    conn.execute(
        """
        INSERT INTO etl_checkpoints (stream_name, consumer_name, last_stream_id, updated_at)
        VALUES (%s, %s, %s, NOW())
        ON CONFLICT (stream_name, consumer_name) DO UPDATE SET
            last_stream_id = EXCLUDED.last_stream_id,
            updated_at = NOW()
        """,
        (stream, consumer, stream_id),
    )


def upsert_heartbeat(
    conn: psycopg.Connection,
    agent_id: str,
    host_id: str,
    source_type: str,
    capabilities: list[str],
) -> None:
    upsert_host(conn, host_id)
    conn.execute(
        """
        INSERT INTO agent_heartbeats (agent_id, host_id, source_type, capabilities, status, seen_at)
        VALUES (%s, %s, %s, %s::jsonb, 'online', NOW())
        ON CONFLICT (agent_id) DO UPDATE SET
            host_id = EXCLUDED.host_id,
            source_type = EXCLUDED.source_type,
            capabilities = EXCLUDED.capabilities,
            status = 'online',
            seen_at = NOW()
        """,
        (agent_id, host_id, source_type, json.dumps(capabilities)),
    )
