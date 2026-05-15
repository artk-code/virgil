# VIRGIL Security Event Contract

This contract defines the Redis stream topology and JSON payloads used by
**VIRGIL** (Vendor Independent Response Governance Intelligence Layer).

## Redis streams

- `security_events`: normalized host telemetry from Rust agents.
- `security_analysis`: enrichment and scoring output from Python rules/model pipeline.
- `security_alerts`: actionable alert events generated from analysis.
- `security_dlq`: dead-letter events for parse/processing failures.
- `security_heartbeats`: optional lightweight heartbeat stream from producers.

## Redis consumer groups

- `py-rules-cg` on `security_events`
  - Consumer naming: `py-rules-<hostname>-<pid>`
- `transform-cg` on `security_events`
  - Consumer naming: `transform-<hostname>-<pid>`
- `transform-analysis-cg` on `security_analysis`
  - Consumer naming: `transform-analysis-<hostname>-<pid>`

## `security_events` payload schema

Stream field: `event` (JSON string)

```json
{
  "event_id": "b9cc3135-25f6-4692-b66c-d71d8f205f5f",
  "trace_id": "d2290fca-9f89-4d66-a1f2-5ea25a5e1370",
  "host_id": "srv-prod-01",
  "agent_id": "agent-simulator",
  "source_type": "ebpf",
  "event_type": "process_exec",
  "severity": "medium",
  "ts": "2026-05-14T19:45:10Z",
  "raw": {
    "pid": 1337,
    "ppid": 1,
    "command": "/usr/bin/curl"
  },
  "normalized": {
    "process_name": "curl",
    "network_direction": "egress"
  },
  "tags": ["linux", "server", "runtime"]
}
```

## `security_analysis` payload schema

Stream field: `analysis` (JSON string)

```json
{
  "analysis_id": "23c50f45-7b2f-4766-ae7f-c508f93f5aaf",
  "event_id": "b9cc3135-25f6-4692-b66c-d71d8f205f5f",
  "trace_id": "d2290fca-9f89-4d66-a1f2-5ea25a5e1370",
  "host_id": "srv-prod-01",
  "score": 0.91,
  "severity": "high",
  "rule_hits": ["suspicious_exec", "rare_parent_child"],
  "explanation": "execution of high-risk binary with network egress pattern",
  "analyzed_at": "2026-05-14T19:45:11Z"
}
```

## `security_alerts` payload schema

Stream field: `alert` (JSON string)

```json
{
  "alert_id": "f63fbc5f-0ad7-4ca2-b553-f6f8b6a5a605",
  "analysis_id": "23c50f45-7b2f-4766-ae7f-c508f93f5aaf",
  "event_id": "b9cc3135-25f6-4692-b66c-d71d8f205f5f",
  "trace_id": "d2290fca-9f89-4d66-a1f2-5ea25a5e1370",
  "host_id": "srv-prod-01",
  "severity": "high",
  "title": "High-risk process execution detected",
  "created_at": "2026-05-14T19:45:11Z"
}
```

## Idempotency key

All processors should use `event_id` as their idempotency key. The Phase 1
Python pipeline stores a short-lived Redis dedupe key:

- key: `dedupe:event:<event_id>`
- operation: `SET NX EX`
- default TTL: `3600s`

## Notes

- `source_type` must be one of `ebpf`, `logs`, `simulator`.
- `severity` values: `low`, `medium`, `high`, `critical`.
- `ts` and derived timestamps are UTC RFC3339 strings.
