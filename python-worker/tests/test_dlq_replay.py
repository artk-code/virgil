import json

from dlq_replay import parse_dlq_candidate, resolve_destination_stream, sanitize_payload


def test_parse_dlq_candidate_accepts_valid_entry():
    fields = {
        "dlq": json.dumps(
            {
                "stream": "security_events",
                "stream_id": "1715700000000-1",
                "reason": "boom",
                "payload": {"event": "{\"event_id\":\"abc\"}"},
                "ts": "2026-01-01T00:00:00Z",
            }
        )
    }
    candidate = parse_dlq_candidate("1715700000001-0", fields)
    assert candidate.stream_id == "1715700000001-0"
    assert candidate.source_stream == "security_events"
    assert candidate.payload["event"] == "{\"event_id\":\"abc\"}"


def test_parse_dlq_candidate_rejects_missing_event_payload():
    fields = {"dlq": json.dumps({"stream": "security_events", "payload": {"other": "x"}})}
    try:
        parse_dlq_candidate("1-0", fields)
        assert False, "expected error for missing event payload"
    except ValueError as exc:
        assert "missing event" in str(exc)


def test_sanitize_payload_stringifies_non_strings():
    out = sanitize_payload({"event": {"a": 1}, "n": 4, "s": "ok", "nil": None})
    assert out["event"] == '{"a":1}'
    assert out["n"] == "4"
    assert out["s"] == "ok"
    assert "nil" not in out


def test_resolve_destination_prefers_forced_stream():
    candidate = parse_dlq_candidate(
        "1-0",
        {"dlq": json.dumps({"stream": "security_events", "payload": {"event": "{}"}})},
    )
    destination = resolve_destination_stream(
        candidate,
        forced_stream="custom_stream",
        fallback_stream="security_events",
        dlq_stream="security_dlq",
    )
    assert destination == "custom_stream"


def test_resolve_destination_uses_fallback_if_source_is_dlq():
    candidate = parse_dlq_candidate(
        "1-0",
        {"dlq": json.dumps({"stream": "security_dlq", "payload": {"event": "{}"}})},
    )
    destination = resolve_destination_stream(
        candidate,
        forced_stream="",
        fallback_stream="security_events",
        dlq_stream="security_dlq",
    )
    assert destination == "security_events"
