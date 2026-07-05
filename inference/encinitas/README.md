# encinitas local inference

Run the **encinitas** LoRA adapter on [Gemma 4 26B A4B](https://huggingface.co/google/gemma-4-26B-A4B-it) with Transformers + PEFT.

Supports Fireworks' `fused_peft_3d_v1` MoE expert LoRA — not loadable via Ollama or stock PEFT alone.

**License:** MIT for scripts here. Adapter weights are on Hugging Face separately. You must accept Google's Gemma 4 license for the base model.

## Requirements

| Component | Detail |
|-----------|--------|
| VRAM | **48 GiB+** (fp16). **80+ GiB** recommended. Strix Halo (~96 GiB unified) works. |
| Base model | `google/gemma-4-26B-A4B-it` (~49 GB, gated) |
| Adapter | [`coldcurrent/encinitas-gemma4-lora`](https://huggingface.co/coldcurrent/encinitas-gemma4-lora) (~1 GB) |

## Quick start — AMD ROCm (Strix Halo / gfx1151)

```bash
cd inference/encinitas

cp encinitas.env.example encinitas.env
# Edit encinitas.env — set HF_TOKEN only locally (never commit encinitas.env)
# Accept license: https://huggingface.co/google/gemma-4-26B-A4B-it

bash fix_encinitas_gfx1151_torch.sh
./run_encinitas_local.sh "Say hello in one sentence."
```

## Quick start — NVIDIA CUDA (48GB+)

```bash
cd inference/encinitas
cp encinitas.env.example encinitas.env
bash setup_cuda_venv.sh
./run_encinitas_local.sh "Say hello."
```

## Secrets

| File | Commit? |
|------|---------|
| `encinitas.env.example` | Yes — empty placeholders only |
| `encinitas.env` | **Never** — gitignored, holds your HF token |

## Environment variables

| Variable | Required | Default |
|----------|----------|---------|
| `HF_TOKEN` | Yes (in `encinitas.env`) | — |
| `ENCINITAS_ADAPTER_HF` | No | `coldcurrent/encinitas-gemma4-lora` |
| `ENCINITAS_ADAPTER_PATH` | No | HF repo above, or `weights/encinitas-peft/` if present |
| `ENCINITAS_BASE_MODEL` | No | `google/gemma-4-26B-A4B-it` |
| `ENCINITAS_LOW_MEMORY` | No | off — set `1` if VRAM < 55 GiB |
| `ENCINITAS_ATTN` | No | `eager` on ROCm (avoids generation hangs) |
| `ENCINITAS_GPU_MEMORY_GIB` | No | auto — set `96` if Strix Halo under-reports VRAM |

## ROCm troubleshooting

| Symptom | Fix |
|---------|-----|
| `mmap` / `ENOMEM` | `bash fix_encinitas_gfx1151_torch.sh` |
| HIP alloc fails on gfx1151 | Same — avoid Debian `python3-torch-rocm` |
| `Gemma4TextExperts not supported` | Use this `chat_encinitas_local.py` (fused expert merge) |
| Hang on generate + SDPA warnings | Confirm `ROCm inference: eager attention` at startup |

## Maintainer: publish adapter to Hugging Face

```bash
export HF_TOKEN=hf_...   # your token, never commit
python upload_adapter_to_hf.py --source /path/to/encinitas-peft
```