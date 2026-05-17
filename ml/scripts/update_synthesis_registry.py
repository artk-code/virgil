#!/usr/bin/env python3
"""
Update synthesis_registry.json with accurate live counts from data/synthesis/*.jsonl

Usage:
    python scripts/update_synthesis_registry.py

This script:
- Scans all *.jsonl files in data/synthesis/
- Skips any junk/temp files (phi1_fragment*, etc.)
- Uses a stable character-based token estimator
- Extracts task breakdown from meta.task
- Rewrites synthesis_registry.json with fresh numbers
"""

import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
SYNTH_DIR = ROOT / "data" / "synthesis"
REGISTRY_PATH = ROOT / "synthesis_registry.json"

# Good empirical constant for VIRGIL-style JSONL (messages + long <reasoning> + structured <answer>)
CHARS_PER_TOKEN = 3.85

# Canonical metadata for each topic file (keeps registry clean and consistent)
TOPIC_META = {
    "virgil_phi1_investigative": {
        "domain": "cross_domain_investigative",
        "persona": "VIRGIL-PHI1 main swarm — Sherlock-style SOC reasoning, hypothesis testing, and cross-domain correlation",
    },
    "linux_forensics": {
        "domain": "linux",
        "persona": "Linux endpoint forensics and EDR analysis",
    },
    "windows_internals": {
        "domain": "windows",
        "persona": "Windows security internals and advanced detection",
    },
    "mobile_app_analysis": {
        "domain": "mobile",
        "persona": "Android and mobile application security & malware analysis",
    },
    "red_team_operations": {
        "domain": "red_team",
        "persona": "Red team operations and adversary emulation from defender perspective",
    },
    "lolbin_detection": {
        "domain": "general_security",
        "persona": "Living-off-the-land and LOLBin detection engineering",
    },
    "soc_investigation_training": {
        "domain": "soc_operations",
        "persona": "SOC investigation, triage, and operational reasoning training",
    },
    "osint_investigation": {
        "domain": "osint_investigative",
        "persona": "Open source intelligence and cross-domain investigation",
    },
    "sigma_detection": {
        "domain": "detection_engineering",
        "persona": "Sigma rule analysis and high-fidelity detection engineering",
    },
    "kev_exploitation": {
        "domain": "vulnerability_exploitation",
        "persona": "CISA KEV exploitation analysis and threat-informed hunting",
    },
    "deep_technical_detection": {
        "domain": "technical_detection",
        "persona": "Deep technical internals and malware technique detection (high-signal sources)",
    },
    "macos_security": {
        "domain": "macos",
        "persona": "macOS endpoint security, launchd persistence, TCC, Gatekeeper, and Apple telemetry",
    },
    "web_framework_security": {
        "domain": "web_framework_security",
        "persona": "Framework SSRF, CSRF, RCE boundary analysis and defender telemetry correlation",
    },
}


def count_tokens(example: dict) -> int:
    total_chars = sum(len(m.get("content", "")) for m in example.get("messages", []))
    return int(total_chars / CHARS_PER_TOKEN)


def main():
    print("Scanning synthesis directory...\n")

    files = sorted(SYNTH_DIR.glob("*.jsonl"))
    sources = {}
    total_records = 0
    total_tokens = 0

    for path in files:
        name = path.stem

        # Skip junk / temp files
        if name.startswith("phi1_fragment") or name.startswith("temp") or name.startswith("fragment"):
            print(f"  Skipping junk file: {path.name}")
            continue

        records = 0
        tokens = 0
        task_counts = defaultdict(int)

        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ex = json.loads(line)
                except json.JSONDecodeError:
                    continue

                records += 1
                tokens += count_tokens(ex)
                task = ex.get("meta", {}).get("task", "unknown")
                task_counts[task] += 1

        if records == 0:
            continue

        total_records += records
        total_tokens += tokens

        meta = TOPIC_META.get(name, {"domain": "other", "persona": "General / uncategorized synthesis"})
        sources[name] = {
            "n_records": records,
            "approx_tokens": tokens,
            "domain": meta["domain"],
            "persona": meta["persona"],
            "task_breakdown": dict(sorted(task_counts.items())),
            "file": f"data/synthesis/{name}.jsonl",
        }

        print(f"  {name:32s} {records:4d} records  ~{tokens:7,d} tokens")

    print(f"\n{'TOTAL CLEAN SYNTHESIS':32s} {total_records:4d} records  ~{total_tokens:7,d} tokens\n")

    # Build the new registry
    registry = {
        "version": "0.3-synthesis",
        "description": "VIRGIL-ML synthetic training data registry. All records are original LLM-synthesized examples in VIRGIL format (messages + <reasoning> + <answer> JSON). No copyrighted source text included.",
        "total_records": total_records,
        "approx_total_tokens": total_tokens,
        "sources": sources,
        "notes": "All synthesis data is original LLM-generated VIRGIL-format content. Files use generalized topic names only. Run this script after every swarm wave to keep counts accurate.",
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "final_train_records": 13689,   # from v0.2 baseline
        "final_eval_records": 1964,
        "target": {
            "goal": "10M tokens well-balanced VIRGIL-PHI1 training set",
            "current_approx": total_tokens,
            "plan": "100k token batches via 10-agent swarm into virgil_phi1_investigative + targeted topic tracks (linux_forensics, windows_internals, sigma_detection, kev_exploitation, deep_technical_detection, etc.)",
        },
    }

    # Write it
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)

    print(f"✅ Updated {REGISTRY_PATH}")
    print(f"   Total: {total_records} records (~{total_tokens:,} tokens)")


if __name__ == "__main__":
    main()
