# Fireworks Fine-Tuning Prep

This repo exports VIRGIL synthesis data to Fireworks-compatible JSONL without
changing the canonical `data/synthesis/` files.

## Current Export

Generated files:

```bash
data/fireworks/virgil_fireworks_train.jsonl
data/fireworks/virgil_fireworks_eval.jsonl
data/fireworks/manifest.json
```

The train and eval files contain only Fireworks/OpenAI-style chat rows:

```json
{"messages":[{"role":"system","content":"..."},{"role":"user","content":"..."},{"role":"assistant","content":"<reasoning>...</reasoning>\n<answer>{...}</answer>"}]}
```

The manifest contains source category counts, split details, token estimates,
file hashes, and task coverage. VIRGIL `meta` fields are intentionally not
embedded in Fireworks upload rows.

## Regenerate Export

```bash
python3 scripts/export_fireworks_sft.py
```

Defaults:

- input: `data/synthesis/*.jsonl`
- output: `data/fireworks/`
- split: 95% train / 5% eval
- eval split: stratified by `meta.source_book`
- assistant format: preserves `<reasoning>` and `<answer>` tags in assistant `content`

Optional Fireworks thinking-trace format:

```bash
python3 scripts/export_fireworks_sft.py --assistant-mode reasoning_content
```

Use this only after confirming the chosen base model supports Fireworks
`reasoning_content` training.

## Validate Export

```bash
python3 scripts/validate_fireworks_sft.py
```

This validates:

- every non-empty JSONL line parses
- root rows only use Fireworks-compatible keys
- messages have valid roles and string content
- system message is first when present
- assistant output has VIRGIL reasoning and answer content
- extracted `<answer>...</answer>` is valid JSON
- manifest counts and file hashes match the exported files
- eval split contains every source category

## Fireworks Notes

The Fireworks SFT docs currently say SFT training data uses the
OpenAI-compatible `messages` JSONL format. Fireworks also supports optional
`reasoning_content` for models that support thinking traces.

The Fireworks managed fine-tuning overview currently says RFT is free for
models under 16B parameters, while SFT and DPO are billed per training token.
For the free small-model path, prepare an RFT prompt dataset plus evaluator
instead of uploading the SFT label files directly.

Docs checked:

- https://docs.fireworks.ai/fine-tuning/fine-tuning-models
- https://docs.fireworks.ai/fine-tuning/managed-finetuning-intro
- https://docs.fireworks.ai/fine-tuning/training-prerequisites
- https://docs.fireworks.ai/fine-tuning/fine-tuning-via-api

## Upload Sketch

Do not run these until the target account, model ID, and billing/free route are
confirmed.

```bash
export FIREWORKS_API_KEY="fw_..."
firectl dataset create virgil-sft-train data/fireworks/virgil_fireworks_train.jsonl
firectl dataset create virgil-sft-eval data/fireworks/virgil_fireworks_eval.jsonl
firectl sftj create \
  --base-model accounts/fireworks/models/<model-id> \
  --dataset virgil-sft-train \
  --evaluation-dataset virgil-sft-eval \
  --output-model virgil-<model-id>-sft-v1
```

Before running a free under-16B experiment, verify whether the selected job is
RFT, not SFT, and create the matching evaluator.

## First Target: Qwen2 7B Instruct LoRA SFT

Use this as the first paid smoke test under the new account usage cap.

Model:

```text
accounts/fireworks/models/qwen2-7b-instruct
```

Current Fireworks model page notes:

- parameters: 7.61B
- fine-tuning: supported
- method: LoRA
- base model serverless: not supported
- fine-tuned LoRA serving: on-demand only, per Fireworks LoRA deployment docs

Estimated SFT training cost with the current export:

```text
train tokens: 2,017,500
epochs: 1
price tier: models up to 16B parameters, LoRA SFT at $0.50 / 1M training tokens
estimated training cost: 2.0175 * $0.50 = ~$1.01
```

Leave room for upload retries, validation, and short inference tests, but the
training job itself should be comfortably below the new-account $50 cap.

Preflight:

```bash
python3 scripts/validate_fireworks_sft.py
```

Once `firectl` and `FIREWORKS_API_KEY` are configured:

```bash
firectl model get -a fireworks qwen2-7b-instruct

firectl dataset create virgil-qwen2-7b-sft-train-v1 data/fireworks/virgil_fireworks_train.jsonl
firectl dataset create virgil-qwen2-7b-sft-eval-v1 data/fireworks/virgil_fireworks_eval.jsonl

firectl sftj create \
  --job-id virgil-qwen2-7b-sft-1ep-v1 \
  --base-model accounts/fireworks/models/qwen2-7b-instruct \
  --dataset virgil-qwen2-7b-sft-train-v1 \
  --evaluation-dataset virgil-qwen2-7b-sft-eval-v1 \
  --epochs 1.0 \
  --lora-rank 8 \
  --output-model virgil-qwen2-7b-sft-1ep-v1
```

Monitor:

```bash
firectl sftj get virgil-qwen2-7b-sft-1ep-v1
firectl model list
```

Deploy only after the job looks good:

```bash
firectl deployment create accounts/<ACCOUNT_ID>/models/virgil-qwen2-7b-sft-1ep-v1
```
