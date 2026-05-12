//! Long-running worker: connects to `REDIS_URL` and logs periodic pings.

use std::time::Duration;

use redis::aio::ConnectionManager;
use tokio::time::sleep;

#[tokio::main]
async fn main() -> redis::RedisResult<()> {
    let url = std::env::var("REDIS_URL").unwrap_or_else(|_| "redis://redis:6379".into());
    eprintln!("[rust-worker] connecting to {url}");

    let client = redis::Client::open(url)?;
    let mut mgr = ConnectionManager::new(client).await?;

    loop {
        let pong: String = redis::cmd("PING").query_async(&mut mgr).await?;
        eprintln!("[rust-worker] PING -> {pong}");
        sleep(Duration::from_secs(10)).await;
    }
}

#[cfg(test)]
mod tests {
    #[test]
    fn default_redis_url_is_valid() {
        let url = std::env::var("REDIS_URL").unwrap_or_else(|_| "redis://redis:6379".into());
        assert!(redis::Client::open(url.as_str()).is_ok());
    }
}
