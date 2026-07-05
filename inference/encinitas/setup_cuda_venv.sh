#!/usr/bin/env bash
# NVIDIA CUDA setup for encinitas (48 GiB VRAM or higher).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${ROOT}/encinitas-venv-cuda"
DEPS=(transformers peft accelerate safetensors sentencepiece huggingface_hub)

echo "==> Creating CUDA venv (${VENV})"
rm -rf "${VENV}"
python3 -m venv "${VENV}"
"${VENV}/bin/pip" install --upgrade pip wheel
"${VENV}/bin/pip" install torch torchvision --index-url https://download.pytorch.org/whl/cu124
"${VENV}/bin/pip" install "${DEPS[@]}"

"${VENV}/bin/python" - <<'PY'
import torch
if not torch.cuda.is_available():
    raise SystemExit("CUDA GPU not visible")
props = torch.cuda.get_device_properties(0)
gib = props.total_memory / (1024**3)
print("device", torch.cuda.get_device_name(0), f"({gib:.1f} GiB)")
if gib < 48:
    print("WARNING: under 48 GiB — set ENCINITAS_LOW_MEMORY=1")
PY

echo "Ready: ${ROOT}/run_encinitas_local.sh"