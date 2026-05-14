from __future__ import annotations

from typing import Any


HIGH_RISK_COMMANDS = {"/usr/bin/nc", "/bin/nc", "/usr/bin/netcat"}


def evaluate_rules(event: dict[str, Any]) -> tuple[list[str], str, str]:
    rule_hits: list[str] = []
    explanation_parts: list[str] = []

    event_type = str(event.get("event_type", "unknown"))
    severity = str(event.get("severity", "low"))
    raw = event.get("raw", {}) if isinstance(event.get("raw", {}), dict) else {}
    command = str(raw.get("command", ""))

    if event_type == "network_egress":
        rule_hits.append("network_egress_activity")
        explanation_parts.append("network egress activity observed")
        severity = _promote(severity, "medium")

    if command in HIGH_RISK_COMMANDS:
        rule_hits.append("suspicious_exec")
        explanation_parts.append(f"high-risk binary executed: {command}")
        severity = _promote(severity, "high")

    if not rule_hits:
        explanation_parts.append("no high-signal heuristics matched")

    return rule_hits, severity, "; ".join(explanation_parts)


def _promote(current: str, target: str) -> str:
    rank = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    current_rank = rank.get(current, 1)
    target_rank = rank.get(target, 1)
    return target if target_rank > current_rank else current
