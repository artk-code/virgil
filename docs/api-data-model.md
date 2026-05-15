# VIRGIL API + Data Model

This document tracks the current API and SQL baseline for **VIRGIL**
(Vendor-neutral Incident Response Graph & Intelligence Layer). The model still
reflects the initial Phase 1 scaffold and will expand toward fleet inventory,
agent identity, alert workflow, and detection intelligence.

## Go API endpoints

- `POST /api/v1/agents/checkin`
  - body: `agent_id`, `host_id`, `source_type`, `capabilities[]`
  - effect: upsert host + heartbeat row
- `GET /api/v1/agents/{agent_id}/status`
  - returns latest heartbeat status for one agent
- `GET /api/v1/alerts/recent?limit=20&offset=0`
  - returns newest rows from `security_findings` with deterministic order (`analyzed_at DESC, analysis_id DESC`)
  - query guardrails: `limit` range `1..100`, `offset` range `0..10000`
  - response includes `pagination` object: `limit`, `offset`, `returned`, `has_more`
- `GET /api/v1/events/search?host_id=&event_type=&severity=&limit=50&offset=0`
  - returns filtered rows from `security_events` with deterministic order (`ts DESC, event_id DESC`)
  - query guardrails: `limit` range `1..250`, `offset` range `0..10000`
  - `severity` must be one of: `low`, `medium`, `high`, `critical`
  - response includes `pagination` object: `limit`, `offset`, `returned`, `has_more`

## Error contract for query validation

For invalid query parameters on the two query endpoints above, API returns:

```json
{
  "error_code": "invalid_query",
  "message": "human-readable validation message",
  "details": {
    "param": "severity",
    "value": "urgent"
  }
}
```

## SQL model (migration `001_init_security_schema.sql`)

- `hosts`
  - PK: `host_id`
  - tracking columns: `first_seen_at`, `last_seen_at`, `metadata`
- `security_events`
  - PK: `event_id`
  - key dimensions: `host_id`, `source_type`, `event_type`, `severity`, `ts`
  - payload columns: `raw`, `normalized`, `tags`
- `security_findings`
  - PK: `analysis_id`
  - FK: `event_id -> security_events`
  - scores + rules output for queryable analytics/alerts
- `agent_heartbeats`
  - PK: `agent_id`
  - latest online status + capabilities per agent
- `etl_checkpoints`
  - PK: `(stream_name, consumer_name)`
  - stores last Redis stream ID processed by ETL jobs
