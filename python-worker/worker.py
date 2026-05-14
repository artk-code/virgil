"""Security analysis pipeline worker for Redis stream events."""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any
from uuid import uuid4

from config import load_pipeline_config
from emit import build_analysis, publish_alert, publish_analysis, publish_dlq
from ingest import ensure_group, mark_dedupe, parse_event_message, read_from_group, redis_from_env
from models import score_event
from rules import evaluate_rules

log = logging.getLogger(__name__)


def _normalize_event(event: dict[str, Any], host_id: str) -> dict[str, Any]:
    normalized = dict(event)
    normalized.setdefault("event_id", str(uuid4()))
    normalized.setdefault("trace_id", str(uuid4()))
    normalized.setdefault("host_id", host_id)
    normalized.setdefault("agent_id", "unknown-agent")
    normalized.setdefault("source_type", "logs")
    normalized.setdefault("event_type", "unknown")
    normalized.setdefault("severity", "low")
    normalized.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    normalized.setdefault("raw", {})
    normalized.setdefault("normalized", {})
    normalized.setdefault("tags", [])
    return normalized


def _apply_redaction(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("raw", {})
    if isinstance(raw, dict) and "command" in raw:
        cmd = str(raw["command"])
        if "token" in cmd.lower() or "password" in cmd.lower():
            raw["command"] = "[redacted]"
    event["raw"] = raw
    return event


def _structured_log(event_name: str, **fields: Any) -> None:
    payload = {"event": event_name, **fields}
    log.info(json.dumps(payload, separators=(",", ":"), sort_keys=True))


def _lifecycle_fields(event: dict[str, Any], stream_id: str, attempt: int, outcome: str) -> dict[str, Any]:
    return {
        "event_id": str(event.get("event_id", "")),
        "trace_id": str(event.get("trace_id", "")),
        "host_id": str(event.get("host_id", "")),
        "event_type": str(event.get("event_type", "")),
        "severity": str(event.get("severity", "")),
        "stream_id": stream_id,
        "attempt": attempt,
        "outcome": outcome,
    }


def _metrics_snapshot(counters: dict[str, int], runtime_seconds: float) -> dict[str, Any]:
    runtime = max(1.0, runtime_seconds)
    processed = counters.get("processed", 0)
    return {
        "processed": processed,
        "retried": counters.get("retried", 0),
        "deduped": counters.get("deduped", 0),
        "dlq_published": counters.get("dlq_published", 0),
        "pipeline_errors": counters.get("pipeline_errors", 0),
        "throughput_per_sec": round(processed / runtime, 3),
    }


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    cfg = load_pipeline_config()
    client = redis_from_env()
    if client is None:
        while True:
            time.sleep(5)

    ensure_group(client, cfg.events_stream, cfg.rules_group)
    counters: dict[str, int] = {
        "processed": 0,
        "retried": 0,
        "deduped": 0,
        "dlq_published": 0,
        "pipeline_errors": 0,
    }
    cycle_started = time.time()

    while True:
        messages = read_from_group(
            client,
            stream=cfg.events_stream,
            group=cfg.rules_group,
            consumer=cfg.consumer_name,
            block_ms=cfg.block_ms,
            count=cfg.read_count,
        )
        if not messages:
            _emit_metrics(counters, cycle_started)
            continue

        for stream_id, message_data in messages:
            success = False
            for attempt in range(1, cfg.retry_max + 1):
                try:
                    event = parse_event_message(message_data)
                    event = _normalize_event(event, cfg.host_id)
                    event = _apply_redaction(event)
                    event_id = str(event["event_id"])

                    if not mark_dedupe(client, event_id, cfg.dedupe_ttl_seconds):
                        client.xack(cfg.events_stream, cfg.rules_group, stream_id)
                        counters["deduped"] += 1
                        _structured_log("worker_message_deduped", **_lifecycle_fields(event, stream_id, attempt, "deduped"))
                        success = True
                        break

                    rule_hits, derived_severity, explanation = evaluate_rules(event)
                    score = score_event(event, rule_hits, derived_severity)
                    analysis = build_analysis(
                        event=event,
                        rule_hits=rule_hits,
                        score=score,
                        severity=derived_severity,
                        explanation=explanation,
                    )
                    publish_analysis(client, cfg.analysis_stream, analysis)
                    if score >= 0.8 or derived_severity in {"high", "critical"}:
                        publish_alert(client, cfg.alerts_stream, analysis)

                    client.xack(cfg.events_stream, cfg.rules_group, stream_id)
                    counters["processed"] += 1
                    _structured_log(
                        "worker_message_processed",
                        **_lifecycle_fields(event, stream_id, attempt, "processed"),
                        score=round(score, 3),
                        rule_hits_count=len(rule_hits),
                    )
                    success = True
                    break
                except Exception as exc:  # pragma: no cover - runtime path
                    if attempt >= cfg.retry_max:
                        counters["pipeline_errors"] += 1
                        counters["dlq_published"] += 1
                        publish_dlq(
                            client,
                            cfg.dlq_stream,
                            cfg.events_stream,
                            stream_id,
                            str(exc),
                            message_data,
                        )
                        client.xack(cfg.events_stream, cfg.rules_group, stream_id)
                        _structured_log(
                            "worker_message_dlq",
                            stream_id=stream_id,
                            attempt=attempt,
                            outcome="dlq",
                            reason=str(exc),
                        )
                    else:
                        counters["retried"] += 1
                        _structured_log(
                            "worker_message_retry",
                            stream_id=stream_id,
                            attempt=attempt,
                            outcome="retrying",
                            reason=str(exc),
                        )
                        time.sleep(min(2**attempt, 5))
            if not success:
                _structured_log("worker_message_failed", stream_id=stream_id, outcome="failed")

        _emit_metrics(counters, cycle_started)


def _emit_metrics(counters: dict[str, int], cycle_started: float) -> None:
    snapshot = _metrics_snapshot(counters, time.time() - cycle_started)
    _structured_log("worker_metrics", **snapshot)


if __name__ == "__main__":
    main()
