import os

import worker


def test_redis_from_env_none(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    assert worker.redis_from_env() is None


def test_redis_from_env_set(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    r = worker.redis_from_env()
    assert r is not None
