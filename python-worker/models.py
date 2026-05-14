from __future__ import annotations

from typing import Any


def score_event(event: dict[str, Any], rule_hits: list[str], severity: str) -> float:
    base = {"low": 0.15, "medium": 0.45, "high": 0.75, "critical": 0.95}.get(severity, 0.2)
    bump = min(0.2, 0.05 * len(rule_hits))
    if str(event.get("source_type")) == "ebpf":
        bump += 0.03
    return round(min(0.99, base + bump), 3)
