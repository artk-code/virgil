#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENCINITAS_ENV_FILE:-${ROOT}/encinitas.env}"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

if [[ -z "${HF_TOKEN:-}" && -z "${HUGGING_FACE_HUB_TOKEN:-}" ]]; then
  echo "HF_TOKEN is not set."
  echo
  echo "1. Copy the example config:"
  echo "     cp ${ROOT}/encinitas.env.example ${ROOT}/encinitas.env"
  echo "2. Add your Hugging Face token to encinitas.env"
  echo "3. Accept the Gemma 4 license:"
  echo "     https://huggingface.co/google/gemma-4-26B-A4B-it"
  echo
  echo "Or export HF_TOKEN in your shell for this session only."
  exit 1
fi

export HF_TOKEN
export HUGGING_FACE_HUB_TOKEN="${HUGGING_FACE_HUB_TOKEN:-$HF_TOKEN}"

if [[ -x "${ROOT}/encinitas-venv-gfx1151/bin/python" ]]; then
  VENV="${ROOT}/encinitas-venv-gfx1151"
elif [[ -x "${ROOT}/encinitas-venv-cuda/bin/python" ]]; then
  VENV="${ROOT}/encinitas-venv-cuda"
elif [[ -x "${ROOT}/encinitas-venv/bin/python" ]]; then
  VENV="${ROOT}/encinitas-venv"
else
  echo "Run setup first:"
  echo "  bash ${ROOT}/fix_encinitas_gfx1151_torch.sh   # AMD Strix Halo / gfx1151"
  echo "  bash ${ROOT}/fix_encinitas_rocm_venv.sh       # Other AMD ROCm (legacy)"
  echo "  bash ${ROOT}/setup_cuda_venv.sh               # NVIDIA CUDA 48GB+"
  exit 1
fi

export HIP_VISIBLE_DEVICES="${HIP_VISIBLE_DEVICES:-0}"
export HSA_OVERRIDE_GFX_VERSION="${HSA_OVERRIDE_GFX_VERSION:-11.5.1}"
export ROCM_PATH="${ROCM_PATH:-/usr}"
export AMDGPU_IDS_PATH="${AMDGPU_IDS_PATH:-/usr/share/libdrm/amdgpu.ids}"
export PYTHONNOUSERSITE=1
export PYTORCH_ALLOC_CONF="${PYTORCH_ALLOC_CONF:-expandable_segments:True}"
export HF_DEACTIVATE_ASYNC_LOAD="${HF_DEACTIVATE_ASYNC_LOAD:-1}"

exec "${VENV}/bin/python" "${ROOT}/chat_encinitas_local.py" "$@"