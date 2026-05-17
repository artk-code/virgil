# AGENTS.md — VIRGIL Training Subfolder

**This folder contains all code and configuration for fine-tuning VIRGIL models.**

## Purpose

This is the dedicated workspace for training VIRGIL-PHI1 (and future variants like VIRGIL-MINI-1). The goal is to turn high-quality synthetic data (from books, CISA, OSINT, Android RE, Red Team, SOC training, etc.) into a strong **endpoint investigative agent** that excels at:

- Hypothesis formation and elimination
- Evidence evaluation
- Lead prioritization
- Structured incident response reasoning
- Telemetry interpretation on Windows, Linux, Android, and network data

## Core Principles

1. **Evaluation is King**
   - We do **not** trust generic benchmarks (MMLU, GPQA, etc.) as the primary signal.
   - All iteration is driven by VIRGIL-specific evaluation tasks.
   - The eval system must be **fast, cheap, and repeatable** so we can run it after every meaningful training change.

2. **Reasoning Over Memorization**
   - We care more about the model’s ability to do Holmes-style deductive reasoning than raw factual recall.
   - Evaluation tasks should force the model to eliminate impossible hypotheses, assess source credibility, and recommend concrete next actions.

3. **Data is Differentiated by Model Size**
   - VIRGIL-PHI1 (larger model, cloud) sees broad organizational context.
   - VIRGIL-MINI-1 (small on-device) will use more focused, endpoint-local data.
   - Do **not** mix these datasets without clear reasoning.

4. **Reproducibility & Agent-Friendliness**
   - Every training run must be fully reproducible via config files.
   - Any agent (or human) should be able to understand the current state by reading this folder.

## Recommended Stack (Current)

- **Base Model**: Microsoft Phi-4 (or Phi-4-reasoning variants) — strong at complex reasoning.
- **Framework**: Llama-Factory (with Unsloth backend when possible) — best balance of speed, features, and cloud compatibility.
- **Method**: QLoRA (4-bit) with targeted layer training.
- **Cloud Platforms**: Anyscale (Ray), Together.ai, Fireworks.ai, RunPod, Vertex AI.
- **Evaluation**: Custom VIRGIL eval harness using LLM-as-Judge + lightweight human review.

## Folder Structure

```
training/
├── AGENTS.md                 # This file
├── README.md
├── configs/                  # Training configuration files (YAML)
├── scripts/                  # Training, data prep, and launch scripts
├── evaluation/               # The most important folder
│   ├── tasks/                # Individual evaluation task definitions
│   ├── judge/                # LLM judge prompts and scoring logic
│   ├── metrics.py
│   └── run_eval.py
├── data/                     # (symlinks or pointers to datasets)
├── utils/                    # Shared utilities
└── requirements.txt
```

## How to Work in This Folder

### Starting a New Training Run

1. Create a new config in `configs/` (copy an existing one).
2. Make sure your dataset is registered (see data pipeline docs).
3. Update the evaluation tasks if you’ve added new capabilities.
4. Launch the job using the appropriate platform script in `scripts/`.

### Evaluating a Model

```bash
python evaluation/run_eval.py \
    --model_path <path_or_hf_id> \
    --tasks all \
    --output_dir ./eval_results/$(date +%Y%m%d_%H%M)
```

The evaluation system should be fast enough to run after every significant training experiment (target: < 30–60 minutes for a full eval on a strong judge model).

### Adding New Evaluation Tasks

1. Create a new file in `evaluation/tasks/`.
2. Define input format, expected output schema, and scoring criteria.
3. Add it to the task registry.
4. Update the LLM judge prompt if needed.

All new tasks must test **investigative reasoning**, not just factual knowledge.

## Current Priorities (as of latest update)

- Build a fast, reliable, automated evaluation harness for VIRGIL-PHI1.
- Create high-quality held-out evaluation sets across key domains (Windows internals, Linux forensics, Android RE, Red Team OPSEC, SOC triage, investigative OSINT).
- Optimize training code for speed and reproducibility on Anyscale + other clouds.
- Establish clear before/after metrics so we know when fine-tuning is actually helping.

## Important Constraints

- **Non-verbatim data**: All training data must follow the strict non-verbatim rules defined in the root `AGENTS.md`.
- **VIRGIL output format**: Every example must produce valid `<reasoning>...</reasoning>\n<answer>{JSON}</answer>` output.
- **Investigative focus**: We are not building a general coding or chat model. Every task should improve the model’s ability to investigate endpoint security incidents.

## Contact / Ownership

This folder is owned by the VIRGIL training team. Any major changes to the evaluation methodology or training stack should be discussed here first.

---

**Future agents**: Read this file first before touching anything in `training/`. The evaluation system is the single most important piece of infrastructure for making progress on VIRGIL.