//! Stream producer simulator: emits normalized security events to Redis.

use std::time::Duration;

use chrono::Utc;
use redis::aio::ConnectionManager;
use serde::Serialize;
use tokio::time::sleep;
use uuid::Uuid;

#[derive(Serialize)]
struct SecurityEvent {
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
    let redis_url = std::env::var("REDIS_URL").unwrap_or_else(|_| "redis://redis:6379".into());
    let events_stream =
        std::env::var("SECURITY_EVENTS_STREAM").unwrap_or_else(|_| "security_events".into());
    let heartbeat_stream =
        std::env::var("SECURITY_HEARTBEAT_STREAM").unwrap_or_else(|_| "security_heartbeats".into());
    let host_id = std::env::var("HOST_ID").unwrap_or_else(|_| "local-dev-host".into());
    let agent_id = std::env::var("AGENT_ID").unwrap_or_else(|_| "agent-simulator".into());
    let source_type = std::env::var("SOURCE_TYPE").unwrap_or_else(|_| "simulator".into());
    eprintln!("[rust-worker] connecting to {redis_url}");

    let client = redis::Client::open(redis_url)?;
    let mut mgr = ConnectionManager::new(client).await?;
    let mut event_counter: u64 = 0;

    loop {
        event_counter += 1;
        let event = synthetic_event(&host_id, &agent_id, &source_type, event_counter);
        let payload = serde_json::to_string(&event).unwrap_or_else(|_| "{}".into());

        let publish: redis::RedisResult<String> = redis::cmd("XADD")
            .arg(&events_stream)
            .arg("*")
            .arg("event")
            .arg(payload)
            .query_async(&mut mgr)
            .await;

        match publish {
            Ok(stream_id) => {
                eprintln!(
                    "[rust-worker] published event={} stream_id={}",
                    event.event_id, stream_id
                );
            }
            Err(err) => {
                eprintln!("[rust-worker] publish error: {err}");
                sleep(Duration::from_secs(2)).await;
                continue;
            }
        }

        if event_counter % 5 == 0 {
            let heartbeat = serde_json::json!({
                "agent_id": agent_id,
                "host_id": host_id,
                "source_type": source_type,
                "status": "online",
                "seen_at": now_rfc3339(),
            });
            let _: redis::RedisResult<String> = redis::cmd("XADD")
                .arg(&heartbeat_stream)
                .arg("*")
                .arg("heartbeat")
                .arg(heartbeat.to_string())
                .query_async(&mut mgr)
                .await;
        }

        sleep(Duration::from_secs(2)).await;
    }
}

fn synthetic_event(host_id: &str, agent_id: &str, source_type: &str, event_counter: u64) -> SecurityEvent {
    let event_type = if event_counter % 3 == 0 {
        "network_egress"
    } else {
        "process_exec"
    };
    let severity = if event_counter % 5 == 0 { "high" } else { "medium" };
    let command = if event_counter % 5 == 0 { "/usr/bin/nc" } else { "/usr/bin/curl" };

    SecurityEvent {
        event_id: Uuid::new_v4().to_string(),
        trace_id: Uuid::new_v4().to_string(),
        host_id: host_id.to_string(),
        agent_id: agent_id.to_string(),
        source_type: source_type.to_string(),
        event_type: event_type.to_string(),
        severity: severity.to_string(),
        ts: now_rfc3339(),
        raw: serde_json::json!({
            "pid": 1000 + event_counter,
            "ppid": 1,
            "command": command,
        }),
        normalized: serde_json::json!({
            "process_name": if command.ends_with("nc") { "nc" } else { "curl" },
            "network_direction": if event_type == "network_egress" { "egress" } else { "none" },
        }),
        tags: vec!["linux".into(), "server".into(), "runtime".into()],
    }
}

fn now_rfc3339() -> String {
    Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Secs, true)
}

#[cfg(test)]
mod tests {
    #[test]
    fn default_redis_url_is_valid() {
        let url = std::env::var("REDIS_URL").unwrap_or_else(|_| "redis://redis:6379".into());
        assert!(redis::Client::open(url.as_str()).is_ok());
    }

    #[test]
    fn timestamp_format_has_z_suffix() {
        let ts = super::now_rfc3339();
        assert!(ts.ends_with('Z'));
    }
}
