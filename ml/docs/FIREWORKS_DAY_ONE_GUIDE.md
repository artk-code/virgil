# VIRGIL Fireworks Day-One Fine-Tuning Guide

Date: 2026-05-17
Project: VIRGIL cybersecurity investigator fine-tuning
Platform: Fireworks.ai
Dataset: ~2M tokens of highly curated, SME-approved cybersecurity training data built with LLMs and human reviewers

This guide captures exactly what we did to get from local JSONL data to trained Fireworks models, inference deployments, and side-by-side eval reports.

## 1. Prepared the Fireworks Export

The local source dataset already existed as validated VIRGIL synthesis JSONL. We exported it into Fireworks-compatible chat JSONL:

```bash
python3 scripts/export_fireworks_sft.py
python3 scripts/validate_fireworks_sft.py
```

Generated files:

```text
data/fireworks/virgil_fireworks_train.jsonl
data/fireworks/virgil_fireworks_eval.jsonl
data/fireworks/manifest.json
```

Final split:

```text
train: 1,900 examples
eval:    100 examples
```

Fireworks estimated the training dataset at:

```text
2,027,100 tokens
```

## 2. Uploaded Train and Eval Datasets

The Fireworks CLI was not available on the local ARM Linux machine, so we used the REST helper:

```text
scripts/fireworks_sft_api.py
```

Uploaded datasets:

```text
accounts/artk011235/datasets/virgil-qwen2-7b-sft-train-v1
accounts/artk011235/datasets/virgil-qwen2-7b-sft-eval-v1
```

Both reached `READY`.

## 3. Ran Fine-Tuning Jobs

### Successful Jobs

| Job | Base Model | Epochs | Method | Cost |
|---|---|---:|---|---:|
| `virgil-qwen2-7b-sft-1ep-v1` | `accounts/fireworks/models/qwen2-7b-instruct` | 1 | LoRA rank 8 | ~$0.82 |
| `virgil-qwen2-7b-lora-sft-5ep-v1` | `accounts/fireworks/models/qwen2-7b-instruct` | 5 | LoRA rank 8 | ~$4.10 |
| `virgil-deepseek-r1-qwen3-8b-lora-sft-1ep-v1` | `accounts/fireworks/models/deepseek-r1-0528-distill-qwen3-8b` | 1 | LoRA rank 8 | ~$0.81 |
| `virgil-qwen3-30b-a3b-lora-sft-1ep-v1` | `accounts/fireworks/models/qwen3-30b-a3b-instruct-2507` | 1 | LoRA rank 8 | ~$4.92 |
| `virgil-qwen3-30b-a3b-lora-sft-5ep-v1` | `accounts/fireworks/models/qwen3-30b-a3b-instruct-2507` | 5 | LoRA rank 8 | roughly high-$20s/low-$30s expected |

### Failed or Blocked Jobs

| Job/Model | Result |
|---|---|
| `virgil-qwen3-8b-full-1ep-v2` | Trainer provisioning failure |
| Kimi K2.6 | Blocked by B300 quota |

## 4. Compared Training Curves

The training metrics showed the expected pattern:

| Run | Eval Loss Start | Eval Loss End | Improvement |
|---|---:|---:|---:|
| Qwen2 7B 1ep | 2.7061 | 1.8418 | 31.9% |
| DeepSeek 8B 1ep | 2.7309 | 1.7888 | 34.5% |
| Qwen3 30B 1ep | 2.6167 | 1.5479 | 40.8% |
| Qwen2 7B 5ep | 2.7061 | 1.4570 | 46.2% |
| Qwen3 30B 5ep | 2.6167 | about 1.21 mid-run | best curve |

Interpretation:

- one epoch teaches some format and domain behavior
- five epochs greatly improves structure
- 30B learns the VIRGIL style faster than 7B
- loss alone is not enough; inference eval catches formatting and runaway failures

## 5. Built an Inference Eval Harness

We added:

```text
scripts/run_fireworks_inference_eval.py
```

The harness:

- waits for Fireworks deployments to become `READY`
- runs identical held-out prompts
- saves raw outputs locally
- scores tag structure and JSON validity
- records token usage and latency
- optionally deletes deployments immediately after eval

Important defaults used in this run:

```text
limit: 10
seed: 17
temperature: 0
max_tokens: 2200
```

These produced the same 10 eval case IDs across all successful runs.

## 6. Deployed Fine-Tuned Models for Eval

Temporary deployments were created for:

```text
Qwen3 30B 1ep
Qwen3 30B 5ep
Qwen2 7B 5ep
Qwen2 7B 1ep
```

DeepSeek 8B fine-tuned deployment failed internally before serving inference.

Every successful deployment was deleted after eval using the Fireworks delete endpoint with `ignoreChecks=true`.

## 7. Fine-Tuned Eval Result

| Model | Valid JSON | Avg Judge Score | Read |
|---|---:|---:|---|
| Qwen2 7B 1ep | 8/10 | 6.00 | undertrained |
| Qwen2 7B 5ep | 10/10 | 7.53 | best value |
| Qwen3 30B 1ep | 9/10 | 7.48 | high ceiling, one runaway |
| Qwen3 30B 5ep | 10/10 | 8.89 | best model |

The fine-tuned report lives at:

```text
docs/reports/fireworks_finetuned_eval_report_2026-05-17.md
```

## 8. Deployed Base Models for Value Comparison

We compared the fine-tuned models against available base models on the same 10 cases.

Successful base evals:

```text
accounts/fireworks/models/qwen2-7b-instruct
accounts/fireworks/models/qwen3-30b-a3b-instruct-2507
```

DeepSeek 8B base failed internally on both attempted deployment shapes:

```text
qwen3-8b-minimal
direct H100
```

## 9. Base vs Fine-Tuned Result

| Model | Type | Valid JSON | Avg Judge Score |
|---|---|---:|---:|
| Base Qwen2 7B | Base | 0/10 | 4.74 |
| Qwen2 7B 5ep | Fine-tuned | 10/10 | 7.53 |
| Base Qwen3 30B A3B | Base | 2/10 | 6.85 |
| Qwen3 30B A3B 5ep | Fine-tuned | 10/10 | 8.89 |

The value report lives at:

```text
docs/reports/fireworks_base_vs_finetuned_value_report_2026-05-17.md
```

## 10. What We Learned

The fine-tune improved three things that matter operationally:

1. Structured output reliability
2. Deductive cybersecurity reasoning style
3. Concise, parseable defender actions

Base Qwen3 30B was already smart, but it was not obedient enough for the VIRGIL contract. It knew security; it did not reliably package the answer for automation.

The 5-epoch 30B fine-tune did both.

## 11. Current Best Models

Quality target:

```text
accounts/artk011235/models/virgil-qwen3-30b-a3b-lora-sft-5ep-v1
```

Budget target:

```text
accounts/artk011235/models/virgil-qwen2-7b-lora-sft-5ep-v1
```

Training baseline:

```text
accounts/artk011235/models/virgil-qwen2-7b-sft-1ep-v1
accounts/artk011235/models/virgil-qwen3-30b-a3b-lora-sft-1ep-v1
```

## 12. Recommended Next Steps

Run a 50-case eval on:

```text
Qwen3 30B A3B 5ep
Qwen2 7B 5ep
Base Qwen3 30B A3B
```

Then add:

- automated LLM judge scoring
- stricter schema scoring
- per-category win rates
- cost-per-valid-answer
- cost-per-high-quality-answer

The next useful decision is whether Qwen3 30B 5ep is worth the inference premium over Qwen2 7B 5ep for production workflows.

## 13. Cleanup Checklist

At the end of the run, all eval deployments were deleted or soft-deleted.

Useful verification command:

```bash
python3 scripts/run_fireworks_inference_eval.py --help
```

Useful local artifacts:

```text
data/fireworks/inference_evals/
docs/reports/
scripts/run_fireworks_inference_eval.py
scripts/fireworks_sft_api.py
```

## Final Takeaway

The 2M-token fine-tune created measurable value.

It turned general chat models that could talk about security into VIRGIL-shaped endpoint investigators that return parseable, structured, evidence-driven analysis.
