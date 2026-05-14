CREATE TABLE IF NOT EXISTS hosts (
    host_id TEXT PRIMARY KEY,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS security_events (
    event_id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL,
    host_id TEXT NOT NULL REFERENCES hosts(host_id),
    agent_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    raw JSONB NOT NULL DEFAULT '{}'::jsonb,
    normalized JSONB NOT NULL DEFAULT '{}'::jsonb,
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS security_findings (
    analysis_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES security_events(event_id) ON DELETE CASCADE,
    trace_id TEXT NOT NULL,
    host_id TEXT NOT NULL REFERENCES hosts(host_id),
    score DOUBLE PRECISION NOT NULL,
    severity TEXT NOT NULL,
    rule_hits JSONB NOT NULL DEFAULT '[]'::jsonb,
    explanation TEXT NOT NULL DEFAULT '',
    analyzed_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_heartbeats (
    agent_id TEXT PRIMARY KEY,
    host_id TEXT NOT NULL REFERENCES hosts(host_id),
    source_type TEXT NOT NULL,
    capabilities JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL DEFAULT 'online',
    seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS etl_checkpoints (
    stream_name TEXT NOT NULL,
    consumer_name TEXT NOT NULL,
    last_stream_id TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (stream_name, consumer_name)
);

CREATE INDEX IF NOT EXISTS idx_security_events_host_id ON security_events(host_id);
CREATE INDEX IF NOT EXISTS idx_security_events_event_type ON security_events(event_type);
CREATE INDEX IF NOT EXISTS idx_security_events_severity ON security_events(severity);
CREATE INDEX IF NOT EXISTS idx_security_events_ts ON security_events(ts DESC);

CREATE INDEX IF NOT EXISTS idx_security_findings_host_id ON security_findings(host_id);
CREATE INDEX IF NOT EXISTS idx_security_findings_severity ON security_findings(severity);
CREATE INDEX IF NOT EXISTS idx_security_findings_analyzed_at ON security_findings(analyzed_at DESC);
