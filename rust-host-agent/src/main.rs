use chrono::Utc;
use redis::aio::ConnectionManager;
use serde::Serialize;
use uuid::Uuid;

#[derive(Serialize)]
struct HostEvent {
    event_id: String,
    trace_id: String,
    host_id: String,
    agent_id: String,
    source_type: String,
    event_type: String,
    severity: String,
    ts: String,
    raw: serde_json::Value,
    normalized: serde_json::Value,
    tags: Vec<String>,
}

#[tokio::main]
async fn main() -> redis::RedisResult<()> {
    let redis_url = std::env::var("REDIS_URL").unwrap_or_else(|_| "redis://localhost:6379".into());
    let events_stream =
        std::env::var("SECURITY_EVENTS_STREAM").unwrap_or_else(|_| "security_events".into());
    let host_id = std::env::var("HOST_ID").unwrap_or_else(|_| "host-linux-01".into());
    let source_type = std::env::var("SOURCE_TYPE").unwrap_or_else(|_| "logs".into());
    let agent_id = std::env::var("AGENT_ID").unwrap_or_else(|_| "rust-host-agent".into());

    let client = redis::Client::open(redis_url)?;
    let mut conn = ConnectionManager::new(client).await?;

    // Phase 1 placeholder: emit one host event to validate host->stream plumbing.
    // Replace this with eBPF + log fallback collectors in the host deployment.
    let evt = HostEvent {
        event_id: Uuid::new_v4().to_string(),
        trace_id: Uuid::new_v4().to_string(),
        host_id,
        agent_id,
        source_type,
        event_type: "host_startup".into(),
        severity: "low".into(),
        ts: Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Secs, true),
        raw: serde_json::json!({"message":"host agent startup"}),
        normalized: serde_json::json!({"collector":"bootstrap"}),
        tags: vec!["linux".into(), "host".into()],
    };

    let payload = serde_json::to_string(&evt).unwrap_or_else(|_| "{}".into());
    let _: String = redis::cmd("XADD")
        .arg(events_stream)
        .arg("*")
        .arg("event")
        .arg(payload)
        .query_async(&mut conn)
        .await?;
    Ok(())
}
