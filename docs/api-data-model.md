# Phase 1 API + Data Model

## Go API endpoints

- `POST /api/v1/agents/checkin`
  - body: `agent_id`, `host_id`, `source_type`, `capabilities[]`
  - effect: upsert host + heartbeat row
- `GET /api/v1/agents/{agent_id}/status`
  - returns latest heartbeat status for one agent
- `GET /api/v1/alerts/recent?limit=20`
  - returns newest rows from `security_findings`
- `GET /api/v1/events/search?host_id=&event_type=&severity=&limit=50`
  - returns filtered rows from `security_events`

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
