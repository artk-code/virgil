#!/usr/bin/env bash
# Fix encinitas venv to use ROCm GPU PyTorch on Strix Halo (gfx1151).
#
# Pip wheels (torch+rocm7.1) detect the GPU but segfault on tensor alloc on gfx1151.
# Ubuntu's python3-torch-rocm is built against system ROCm 7.1 and works correctly.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${ROOT}/encinitas-venv"
DEPS=(transformers peft accelerate safetensors sentencepiece huggingface_hub torchvision)

if ! dpkg -s python3-torch-rocm >/dev/null 2>&1; then
  echo "ERROR: python3-torch-rocm is not installed."
  echo "Run first:"
  echo "  sudo apt-get install -y python3-torch-rocm"
  exit 1
fi

# Some torch builds look for amdgpu.ids here
if [[ ! -f /opt/amdgpu/share/libdrm/amdgpu.ids ]] && [[ -f /usr/share/libdrm/amdgpu.ids ]]; then
  echo "NOTE: optional fix if torch complains about amdgpu.ids:"
  echo "  sudo mkdir -p /opt/amdgpu/share/libdrm"
  echo "  sudo ln -sf /usr/share/libdrm/amdgpu.ids /opt/amdgpu/share/libdrm/amdgpu.ids"
fi

echo "==> Recreating venv with system ROCm torch (${VENV})"
rm -rf "${VENV}"
python3 -m venv --system-site-packages "${VENV}"
chown -R "${SUDO_USER:-$USER}:${SUDO_USER:-$USER}" "${VENV}" 2>/dev/null || true
"${VENV}/bin/pip" install --upgrade pip
"${VENV}/bin/pip" install "${DEPS[@]}"
# Gemma 4 processor imports torchvision; match system torch 2.9.1+debian
export TMPDIR=/tmp PIP_CACHE_DIR=/tmp/pip-cache-rocm
mkdir -p "${PIP_CACHE_DIR}"
"${VENV}/bin/pip" install --no-cache-dir torchvision==0.24.1+rocm6.4 \
  --index-url https://download.pytorch.org/whl/rocm6.4

echo "==> GPU smoke test"
export HIP_VISIBLE_DEVICES="${HIP_VISIBLE_DEVICES:-0}"
export HSA_OVERRIDE_GFX_VERSION="${HSA_OVERRIDE_GFX_VERSION:-11.5.1}"
export ROCM_PATH="${ROCM_PATH:-/usr}"
export AMDGPU_IDS_PATH="${AMDGPU_IDS_PATH:-/usr/share/libdrm/amdgpu.ids}"

"${VENV}/bin/python" - <<'PY'
import torch
print("torch", torch.__version__)
print("hip", getattr(torch.version, "hip", None))
print("cuda available", torch.cuda.is_available())
if not torch.cuda.is_available():
    raise SystemExit("GPU not visible to PyTorch")
print("device", torch.cuda.get_device_name(0))
x = torch.ones(4, device="cuda")
y = torch.randn(128, 128, device="cuda")
z = y @ y
print("gpu matmul ok", z.shape, z.device)
PY

echo
echo "Ready. Chat with:"
echo "  cp ${ROOT}/encinitas.env.example ${ROOT}/encinitas.env"
echo "  ${ROOT}/run_encinitas_local.sh"