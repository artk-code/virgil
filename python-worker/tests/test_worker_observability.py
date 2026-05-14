import json
import logging

import worker


def test_lifecycle_fields_exclude_raw_payload():
    event = {
        "event_id": "evt-1",
        "trace_id": "tr-1",
        "host_id": "host-1",
        "event_type": "process_exec",
        "severity": "high",
        "raw": {"command": "curl --token hidden"},
    }
    fields = worker._lifecycle_fields(event, stream_id="1-0", attempt=2, outcome="processed")
    assert fields["event_id"] == "evt-1"
    assert fields["stream_id"] == "1-0"
    assert fields["attempt"] == 2
    assert "raw" not in fields


def test_metrics_snapshot_contains_expected_counters():
    counters = {
        "processed": 10,
        "retried": 3,
        "deduped": 2,
        "dlq_published": 1,
        "pipeline_errors": 1,
    }
    snapshot = worker._metrics_snapshot(counters, runtime_seconds=5.0)
    assert snapshot["processed"] == 10
    assert snapshot["retried"] == 3
    assert snapshot["deduped"] == 2
    assert snapshot["dlq_published"] == 1
    assert snapshot["pipeline_errors"] == 1
    assert snapshot["throughput_per_sec"] == 2.0


def test_structured_log_emits_single_line_json(caplog):
    caplog.set_level(logging.INFO)
    worker._structured_log("worker_metrics", processed=1, pipeline_errors=0)
    record = caplog.records[-1]
    payload = json.loads(record.message)
    assert payload["event"] == "worker_metrics"
    assert payload["processed"] == 1
    assert payload["pipeline_errors"] == 0
