# encinitas — Gemma 4 26B MoE LoRA for VIRGIL-style cyber inference

**encinitas** is a LoRA adapter on [Gemma 4 26B A4B](https://huggingface.co/google/gemma-4-26B-A4B-it) trained for blue-team security reasoning in the VIRGIL output contract: evidence-based `<reasoning>` followed by structured `<answer>` JSON with MITRE ATT&CK citations.

This directory is the **local inference stack** for AMD ROCm (Strix Halo / gfx1151) and NVIDIA CUDA. It handles Fireworks' `fused_peft_3d_v1` MoE expert LoRA layout, which stock PEFT and Ollama cannot load alone.

| Artifact | Location |
|----------|----------|
| Inference scripts | This directory (`chat_encinitas_local.py`, setup shells) |
| LoRA weights (~1 GB) | [`coldcurrent/encinitas-gemma4-lora`](https://huggingface.co/coldcurrent/encinitas-gemma4-lora) |
| Base model (~49 GB, gated) | [`google/gemma-4-26B-A4B-it`](https://huggingface.co/google/gemma-4-26B-A4B-it) |
| Training corpus + eval tooling | [`ml/`](../../ml/) in this repo |
| Background write-ups | [VIRGIL training story](https://www.artkaiser.net/blog/custom-cybersecurity-models-fireworks) · [encinitas eval + cost](https://www.artkaiser.net/blog/encinitas-cheaper-better-cyber-inference) |

**Licenses:** MIT for scripts in [artk-code/virgil](https://github.com/artk-code/virgil). Adapter weights: MIT. Base Gemma 4: Google Gemma license (accept on Hugging Face).

---

## What encinitas is

encinitas is not a standalone 26B checkpoint. It is a **~1 GB LoRA** that specializes Gemma 4 26B A4B for endpoint-security investigation tasks:

- MITRE ATT&CK technique mapping from telemetry and threat intel
- Sigma rule analysis and detection-engineering reasoning
- Malware behavior and living-off-the-land scenario triage
- Structured defender recommendations (detect, hunt, isolate, investigate)

Training used the VIRGIL contract from the [`ml/`](../../ml/) corpus — roughly **36M tokens × 3 epochs** on Fireworks (~**$380** SFT). The model name comes from the coastal California town; it sits in the VIRGIL model family alongside smaller Qwen-based advisors documented in the [first VIRGIL blog post](https://www.artkaiser.net/blog/custom-cybersecurity-models-fireworks).

### Architecture at inference time

```
HF gated base (google/gemma-4-26B-A4B-it, ~49 GB fp16)
        +
LoRA adapter (coldcurrent/encinitas-gemma4-lora, fused_peft_3d_v1)
        ↓
chat_encinitas_local.py
  · safetensors pread (avoids mmap ENOMEM on large shards)
  · ROCm-safe weight staging (gfx1151 HIP fixes)
  · PEFT patches for Gemma4ClippableLinear + Gemma4TextExperts
  · apply_fused_expert_lora() — merges MoE expert LoRA into gate_up/down
  · eager attention on ROCm (avoids SDPA generation hangs)
```

**Active parameters at inference:** Gemma 4 26B A4B is a MoE model (~26B total, ~4B active per token). You still need **48 GiB+ VRAM** for fp16 weights; Strix Halo unified memory (~96 GiB) is an excellent fit.

### Strengths (from public evals)

Fine-tuning improved **discipline**, not just domain knowledge:

- Shortest, most parseable outputs on VIRGIL-style prompts
- Reliable `<reasoning>` / `<answer>` contract adherence
- Precise ATT&CK IDs without meta-reasoning leakage
- Competitive cyber quality vs much larger models at a fraction of inference cost

encinitas is optimized for **operator and downstream-system consumption** — SOC parsers, agents, and ticket routers — not for maximal prose length.

---

## Evaluation results

Full methodology, raw generations, and cost models are in [How Less Than $500 of SFT Let a Small Model Beat Kimi 2.7 on Cyber Tasks](https://www.artkaiser.net/blog/encinitas-cheaper-better-cyber-inference). Summary below.

### VIRGIL corpus fine-tuning (Qwen family)

From [One Night, Two Million Tokens, and a Custom Cybersecurity Model](https://www.artkaiser.net/blog/custom-cybersecurity-models-fireworks) — 10 held-out prompts, temperature 0, same decoding settings:

| Model | Type | Valid JSON | Avg judge (1–10) |
|-------|------|------------|------------------|
| Base Qwen2 7B | Base | 0/10 | 4.74 |
| Qwen2 7B 1ep | Fine-tuned | 8/10 | 6.00 |
| Qwen2 7B 5ep | Fine-tuned | 10/10 | 7.53 |
| Base Qwen3 30B A3B | Base | 2/10 | 6.85 |
| Qwen3 30B A3B 1ep | Fine-tuned | 9/10 | 7.48 |
| **Qwen3 30B A3B 5ep** | Fine-tuned | **10/10** | **8.89** |

Fine-tuning also cut completion tokens on the 30B model (13,457 → 5,306 across 10 cases) — better structure *and* lower per-query cost.

### encinitas public OOD eval (Gemma 4 + Kimi)

Out-of-distribution prompts inspired by Meta CyberSecEval-style blue-team scenarios (lsass hollowing, Volt Typhoon, Sigma→TTP). Scoring:

- **TTP %** — proper MITRE ID (`Txxxx` or `Txxxx.yyy`)
- **Actionable %** — defender signal words (recommend, detect, hunt, isolate, …)
- **Format (0–4)** — markdown table + `<reasoning>`/`<answer>` + technique language + MITRE citation

| Model | n | Dataset | TTP % | Actionable % | Format avg |
|-------|---|---------|-------|--------------|------------|
| Base Gemma4-26b | 2 | 2-ex VIRGIL-style | 100% | 50% | 1.5 |
| Gemma4-26b-a4b-it | 3 | 3-ex cyber | 100% | 67% | **3.0** |
| Gemma4-31b-it | 3 | 3-ex cyber | 100% | **100%** | 2.7 |
| **Encinitas LoRA** | 2 | 2-ex VIRGIL-style | 100% | 50% | 2.0 |
| Kimi k2p7-code | 3 | 3-ex cyber | 100% | **100%** | 1.3 |

**Read of the table:** TTP mapping was trivial for all models. Kimi had the highest actionable keyword density but the **lowest format score** (long outputs, visible internal monologue). Encinitas produced the **shortest, cleanest, training-contract-aligned** answers — e.g. 183 chars for an APT39 keystrokes prompt vs verbose base-model breakdowns. For production parsers, that discipline often matters more than raw breadth.

At realistic SOC volumes (800–3000 queries/day), the ~$380 SFT cost pays back in **weeks or less** vs Kimi-class inference pricing. See the blog for break-even math.

---

## Requirements

| Component | Detail |
|-----------|--------|
| VRAM | **48 GiB+** fp16. **80+ GiB** recommended. Strix Halo (~96 GiB unified) works well. |
| Disk | ~50 GB for base model cache + ~1 GB adapter |
| HF access | Token with Gemma 4 license accepted |
| AMD ROCm | gfx1151: AMD PyTorch nightlies (see below). Other ROCm: legacy path. |
| NVIDIA | CUDA 12.4+ wheel, 48 GiB+ GPU |

**Not supported here:** hybrid NPU/GPU offload for this 26B stack — run GPU-only (ROCm or CUDA).

---

## Quick start — AMD ROCm (Strix Halo / gfx1151)

Tested on Ryzen AI Max+ 395 / Radeon 8060S (gfx1151), ROCm 7.x.

```bash
git clone https://github.com/artk-code/virgil.git
cd virgil/inference/encinitas

cp encinitas.env.example encinitas.env
# Edit encinitas.env — set HF_TOKEN only locally (never commit encinitas.env)
# Accept license: https://huggingface.co/google/gemma-4-26B-A4B-it

bash fix_encinitas_gfx1151_torch.sh
./run_encinitas_local.sh "Map this activity to MITRE ATT&CK: powershell -enc JAB..."
```

Interactive chat (no prompt argument):

```bash
./run_encinitas_local.sh
```

### Why gfx1151 needs a special venv

Debian/Ubuntu `python3-torch-rocm` often **detects** the GPU but **fails HIP tensor allocation** on gfx1151 (`hipErrorInvalidValue`). The fix script installs PyTorch from [AMD ROCm nightlies](https://rocm.nightlies.amd.com/v2/gfx1151/) into `encinitas-venv-gfx1151/`.

Expected startup lines:

```
ROCm safe loading enabled (no warmup, CPU-staged GPU copies)
ROCm inference: eager attention, math SDPA only
```

### ROCm environment (set automatically by `run_encinitas_local.sh`)

| Variable | Default | Purpose |
|----------|---------|---------|
| `HIP_VISIBLE_DEVICES` | `0` | GPU index |
| `HSA_OVERRIDE_GFX_VERSION` | `11.5.1` | gfx1151 compatibility |
| `HF_DEACTIVATE_ASYNC_LOAD` | `1` | Avoid parallel CPU→GPU copy HIP errors |
| `PYTORCH_ALLOC_CONF` | `expandable_segments:True` | Reduce fragmentation |
| `ENCINITAS_ATTN` | `eager` (on ROCm) | Avoid SDPA generation hangs |

If VRAM is under-reported on Strix Halo: `ENCINITAS_GPU_MEMORY_GIB=96` in `encinitas.env`.

---

## Quick start — other AMD ROCm (legacy)

For non-gfx1151 AMD GPUs where system `python3-torch-rocm` works:

```bash
sudo apt-get install -y python3-torch-rocm
bash fix_encinitas_rocm_venv.sh
./run_encinitas_local.sh "Say hello."
```

---

## Quick start — NVIDIA CUDA (48 GB+)

```bash
cd inference/encinitas
cp encinitas.env.example encinitas.env   # HF_TOKEN
bash setup_cuda_venv.sh
./run_encinitas_local.sh "Say hello."
```

If VRAM is tight: `ENCINITAS_LOW_MEMORY=1` in `encinitas.env` (4-bit / offload path).

---

## Secrets and configuration

| File | Commit? |
|------|---------|
| `encinitas.env.example` | Yes — empty placeholders only |
| `encinitas.env` | **Never** — gitignored, holds your HF token |

| Variable | Required | Default |
|----------|----------|---------|
| `HF_TOKEN` | Yes (in `encinitas.env`) | — |
| `ENCINITAS_ADAPTER_HF` | No | `coldcurrent/encinitas-gemma4-lora` |
| `ENCINITAS_ADAPTER_PATH` | No | HF repo, or `weights/encinitas-peft/` if present |
| `ENCINITAS_BASE_MODEL` | No | `google/gemma-4-26B-A4B-it` |
| `ENCINITAS_LOW_MEMORY` | No | off — set `1` if VRAM < 55 GiB |
| `ENCINITAS_ATTN` | No | `eager` on ROCm |
| `ENCINITAS_GPU_MEMORY_GIB` | No | auto |

Create a token at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) with gated-repo read access.

---

## Weights layout

Do **not** commit the 49 GB base model or adapter blobs to git.

| Piece | Source | Size |
|-------|--------|------|
| Base | `google/gemma-4-26B-A4B-it` (auto-download on first run) | ~49 GB |
| Adapter | `coldcurrent/encinitas-gemma4-lora` (auto-download) | ~1 GB |
| Local override | `weights/encinitas-peft/` (gitignored) | ~1 GB |

First run downloads both via `huggingface_hub` using `HF_TOKEN`.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `HF_TOKEN is not set` | `cp encinitas.env.example encinitas.env` and add token |
| Gated repo 401/403 | Accept Gemma 4 license; confirm token has gated read |
| `mmap` / `ENOMEM` loading shards | Use `fix_encinitas_gfx1151_torch.sh` (pread patch is automatic) |
| HIP alloc fails on gfx1151 | Same — avoid Debian `python3-torch-rocm` |
| `Gemma4TextExperts not supported` | Use this repo's `chat_encinitas_local.py` (fused expert merge) |
| Hang on `generate` + SDPA warnings | Confirm `ROCm inference: eager attention` at startup |
| GPU visible but alloc fails at probe | Run `fix_encinitas_gfx1151_torch.sh`; check `HIP_VISIBLE_DEVICES` |

---

## Maintainer: publish adapter to Hugging Face

```bash
# Token from env only — never commit
export HF_TOKEN=hf_...
python upload_adapter_to_hf.py --source /path/to/encinitas-peft
```

Default target repo: `coldcurrent/encinitas-gemma4-lora`. Use `--repo` to override.

---

## Production notes

- **Output contract:** Prompt with the VIRGIL system message from [`ml/`](../../ml/) exports for best format adherence.
- **Parsing:** Extract `<answer>...</answer>` JSON downstream; do not rely on free-form prose.
- **Serving:** For multi-user production, wrap `chat_encinitas_local.py` behind an OpenAI-compatible API or batch worker; keep one model loaded per GPU.
- **Cloud fallback:** Fireworks deployment of the same adapter is documented in [`ml/docs/FIREWORKS_FINE_TUNING.md`](../../ml/docs/FIREWORKS_FINE_TUNING.md) if local VRAM is unavailable.

---

## Related reading

- [VIRGIL Advisor ML overview](../../README.md#virgil-advisor-ml)
- [Fireworks fine-tuning guide](../../ml/docs/FIREWORKS_FINE_TUNING.md)
- [Dataset card](../../ml/docs/DATASET_CARD.md)