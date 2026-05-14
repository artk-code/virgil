from __future__ import annotations

import os
from dataclasses import dataclass


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        return int(raw)
    except ValueError:
        return default


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, str(default)).strip().lower()
    return raw in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class PipelineConfig:
    redis_url: str
    database_url: str
    events_stream: str
    analysis_stream: str
    alerts_stream: str
    dlq_stream: str
    rules_group: str
    consumer_name: str
    host_id: str
    retry_max: int
    dedupe_ttl_seconds: int
    block_ms: int
    read_count: int


@dataclass(frozen=True)
class TransformConfig:
    redis_url: str
    database_url: str
    events_stream: str
    analysis_stream: str
    transform_consumer: str
    batch_size: int
    interval_seconds: int
    run_once: bool


def load_pipeline_config() -> PipelineConfig:
    host_id = os.environ.get("HOST_ID", "local-dev-host")
    return PipelineConfig(
        redis_url=os.environ.get("REDIS_URL", "redis://redis:6379"),
        database_url=os.environ.get("DATABASE_URL", ""),
        events_stream=os.environ.get("SECURITY_EVENTS_STREAM", "security_events"),
        analysis_stream=os.environ.get("SECURITY_ANALYSIS_STREAM", "security_analysis"),
        alerts_stream=os.environ.get("SECURITY_ALERTS_STREAM", "security_alerts"),
        dlq_stream=os.environ.get("SECURITY_DLQ_STREAM", "security_dlq"),
        rules_group=os.environ.get("SECURITY_RULES_GROUP", "py-rules-cg"),
        consumer_name=os.environ.get("SECURITY_RULES_CONSUMER", f"py-rules-{host_id}"),
        host_id=host_id,
        retry_max=max(1, _int_env("PIPELINE_RETRY_MAX", 3)),
        dedupe_ttl_seconds=max(60, _int_env("PIPELINE_DEDUPE_TTL_SECONDS", 3600)),
        block_ms=max(100, _int_env("PIPELINE_BLOCK_MS", 5000)),
        read_count=max(1, _int_env("PIPELINE_READ_COUNT", 25)),
    )


def load_transform_config() -> TransformConfig:
    return TransformConfig(
        redis_url=os.environ.get("REDIS_URL", "redis://redis:6379"),
        database_url=os.environ.get("DATABASE_URL", ""),
        events_stream=os.environ.get("SECURITY_EVENTS_STREAM", "security_events"),
        analysis_stream=os.environ.get("SECURITY_ANALYSIS_STREAM", "security_analysis"),
        transform_consumer=os.environ.get("ETL_CONSUMER_NAME", "transform-etl"),
        batch_size=max(1, _int_env("ETL_BATCH_SIZE", 200)),
        interval_seconds=max(5, _int_env("ETL_INTERVAL_SECONDS", 60)),
        run_once=_bool_env("ETL_RUN_ONCE", False),
    )
