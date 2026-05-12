"""Minimal worker template: read REDIS_URL and stay alive with periodic pings."""
from __future__ import annotations

import logging
import os
import time

import redis

log = logging.getLogger(__name__)


def redis_from_env() -> redis.Redis | None:
    url = os.environ.get("REDIS_URL", "").strip()
    if not url:
        log.warning("REDIS_URL not set; idle mode")
        return None
    return redis.Redis.from_url(url, decode_responses=True)


def ping_once(client: redis.Redis) -> bool:
    try:
        return client.ping()
    except redis.RedisError:
        return False


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    client = redis_from_env()
    while True:
        if client is None:
            time.sleep(5)
            continue
        ok = ping_once(client)
        log.info("redis ping=%s", ok)
        time.sleep(10)


if __name__ == "__main__":
    main()
