"""Security analysis pipeline worker for Redis stream events."""
from __future__ import annotations

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


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    cfg = load_pipeline_config()
    client = redis_from_env()
    if client is None:
        while True:
            time.sleep(5)

    ensure_group(client, cfg.events_stream, cfg.rules_group)
    processed = 0
    pipeline_errors = 0
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
            _emit_metrics(processed, pipeline_errors, cycle_started)
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
                    processed += 1
                    success = True
                    break
                except Exception as exc:  # pragma: no cover - runtime path
                    if attempt >= cfg.retry_max:
                        pipeline_errors += 1
                        publish_dlq(
                            client,
                            cfg.dlq_stream,
                            cfg.events_stream,
                            stream_id,
                            str(exc),
                            message_data,
                        )
                        client.xack(cfg.events_stream, cfg.rules_group, stream_id)
                    else:
                        time.sleep(min(2**attempt, 5))
            if not success:
                log.warning("message failed after retries stream_id=%s", stream_id)

        _emit_metrics(processed, pipeline_errors, cycle_started)


def _emit_metrics(processed: int, pipeline_errors: int, cycle_started: float) -> None:
    runtime = max(1.0, time.time() - cycle_started)
    throughput = processed / runtime
    log.info(
        "metrics processed=%s pipeline_errors=%s throughput_per_sec=%.3f",
        processed,
        pipeline_errors,
        throughput,
    )


if __name__ == "__main__":
    main()
