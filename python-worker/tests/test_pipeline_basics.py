import worker


def test_normalize_event_applies_defaults():
    event = {"event_type": "process_exec"}
    normalized = worker._normalize_event(event, host_id="host-a")

    assert normalized["host_id"] == "host-a"
    assert normalized["event_type"] == "process_exec"
    assert normalized["agent_id"] == "unknown-agent"
    assert normalized["severity"] == "low"
    assert isinstance(normalized["tags"], list)
    assert "event_id" in normalized
    assert "trace_id" in normalized


def test_apply_redaction_masks_sensitive_command():
    event = {"raw": {"command": "curl --token topsecret"}}
    redacted = worker._apply_redaction(event)
    assert redacted["raw"]["command"] == "[redacted]"


def test_apply_redaction_leaves_normal_command():
    event = {"raw": {"command": "echo hello"}}
    redacted = worker._apply_redaction(event)
    assert redacted["raw"]["command"] == "echo hello"
