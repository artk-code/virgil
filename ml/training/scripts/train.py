#!/usr/bin/env python3
"""
VIRGIL Training Launcher

This script provides a clean, high-performance entrypoint for fine-tuning VIRGIL-PHI1.

It supports:
- Local Mac (24GB) via Unsloth
- Cloud (Anyscale, Together, RunPod, Vertex) via Llama-Factory

Usage:
    # Local / Mac
    python scripts/train.py --config configs/virgil_phi1_lora.yaml --backend unsloth

    # Cloud (Anyscale / Together style)
    python scripts/train.py --config configs/virgil_phi1_lora.yaml --backend llamafactory
"""

import argparse
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, required=True, help="Path to training config YAML")
    parser.add_argument("--backend", type=str, choices=["unsloth", "llamafactory"], default="llamafactory",
                        help="Training backend")
    parser.add_argument("--dry-run", action="store_true", help="Print command instead of running")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    if not config_path.exists():
        print(f"Config not found: {config_path}")
        sys.exit(1)

    if args.backend == "unsloth":
        cmd = [
            "python", "-m", "unsloth.train",
            "--config", str(config_path),
        ]
    else:
        # Llama-Factory
        cmd = [
            "llamafactory-cli", "train",
            str(config_path),
        ]

    print("Running command:")
    print(" ".join(cmd))

    if args.dry_run:
        return

    result = subprocess.run(cmd)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
