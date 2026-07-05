#!/usr/bin/env bash
# Install gfx1151-native PyTorch for encinitas (Strix Halo / Radeon 8060S).
#
# Debian's python3-torch-rocm (2.9.1+debian) sees the GPU but HIP tensor alloc fails
# with hipErrorInvalidValue. AMD ships gfx1151 builds that actually work.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${ROOT}/encinitas-venv-gfx1151"
INDEX="https://rocm.nightlies.amd.com/v2/gfx1151/"
DEPS=(transformers peft accelerate safetensors sentencepiece huggingface_hub)

echo "==> Creating gfx1151 venv (${VENV})"
if [[ -d "${VENV}" ]]; then
  rm -rf "${VENV}" || {
    echo "Could not remove old venv. Run:"
    echo "  sudo rm -rf ${VENV}"
    exit 1
  }
fi
python3 -m venv "${VENV}"
"${VENV}/bin/pip" install --upgrade pip

echo "==> Installing gfx1151 PyTorch from AMD nightlies"
"${VENV}/bin/pip" install torch torchvision \
  --index-url "${INDEX}"

echo "==> Installing inference deps"
"${VENV}/bin/pip" install "${DEPS[@]}"

echo "==> GPU smoke test"
export HIP_VISIBLE_DEVICES="${HIP_VISIBLE_DEVICES:-0}"
export HSA_OVERRIDE_GFX_VERSION="${HSA_OVERRIDE_GFX_VERSION:-11.5.1}"
export ROCM_PATH="${ROCM_PATH:-/usr}"
export AMDGPU_IDS_PATH="${AMDGPU_IDS_PATH:-/usr/share/libdrm/amdgpu.ids}"
export PYTHONNOUSERSITE=1

"${VENV}/bin/python" - <<'PY'
import torch
print("torch", torch.__version__)
print("hip", getattr(torch.version, "hip", None))
if not torch.cuda.is_available():
    raise SystemExit("GPU not visible to PyTorch")
print("device", torch.cuda.get_device_name(0))
x = torch.ones(4, device="cuda")
y = torch.randn(128, 128, device="cuda")
z = y @ y
print("gpu matmul ok", z.shape, z.device)
PY

echo
echo "Ready:"
echo "  cp ${ROOT}/encinitas.env.example ${ROOT}/encinitas.env"
echo "  ${ROOT}/run_encinitas_local.sh \"Say hello.\""