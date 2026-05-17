# VIRGIL-ML

**The clean, git-friendly repository for VIRGIL synthetic training data and training infrastructure.**

This is the single directory you need for:
- All LLM-synthesized VIRGIL-format Q&A (Holmes deductive reasoning style)
- Ready-to-train final datasets
- Complete training code for **Mac (Unsloth + 24GB)** and **RunPod H100 (Unsloth QLoRA on phi-4)**

**No copyrighted material.** No PDFs, no book chunks, no parser output, no raw extracted text. Only our original synthetic work.

---

## Quick Start

### 1. Synthesis (continue filling the 10M token target)

```bash
# See exactly where we are
cat synthesis_registry.json

# Work on the main cross-domain swarm file (recommended)
# or any generalized topic file in data/synthesis/

# After generating new examples (via Claude/Grok subagent swarm),
# append them as valid VIRGIL JSONL lines to:
#   data/synthesis/virgil_phi1_investigative.jsonl   (primary)
#   data/synthesis/linux_forensics.jsonl
#   data/synthesis/lolbin_detection.jsonl
#   etc.

# Rebuild the final training set
cd training
python scripts/prepare_virgil_data.py \
  --input_files ../data/synthesis/virgil_phi1_investigative.jsonl ../data/synthesis/*.jsonl \
  --output_dir data --eval_ratio 0.05

# Copy the result back to the canonical final location
cp data/virgil_phi1_train.jsonl ../data/final/
cp data/virgil_phi1_eval.jsonl ../data/final/
cp data/virgil_phi1_train.jsonl data/virgil_phi1_train.jsonl   # also update the training snapshot
```

Target: **10M tokens**, well-balanced across domains and task types (hypothesis testing, evidence evaluation, log analysis, adversarial intuition, telemetry recommendation, incident response reasoning, etc.).

We add data in **~100k token batches** using specialized parallel subagents.

### 2. Training (Mac or RunPod)

```bash
# Production (RunPod H100 80GB + Network Volume)
python training/scripts/train_virgil_phi1.py --config training/configs/virgil_phi1_h100.yaml

# Local Mac 24GB testing
python training/scripts/train_virgil_phi1.py --config training/configs/virgil_phi1_mac.yaml --force-mac
```

See `training/README.md` for full RunPod setup, volume mounting, rclone upload, cost estimates (~$6-10 for 2 epochs on H100 spot), and Unsloth optimizations.

---

## Directory Layout

```
virgil-ml/
├── README.md
├── AGENTS.md                           # How to synthesize (swarm + Holmes style)
├── synthesis_registry.json             # Live counts + token estimates per source
├── AGENTS_synthesis_v0.3_legacy.md     # Detailed 12-book schemas + task JSON (reference)
│
├── data/
│   ├── synthesis/                      # ← Append new synthetic examples here
│   │   ├── virgil_phi1_investigative.jsonl   # Main swarm file (cross-domain)
│   │   ├── linux_forensics.jsonl
│   │   ├── lolbin_detection.jsonl
│   │   ├── red_team_operations.jsonl
│   │   ├── windows_internals.jsonl
│   │   ├── mobile_app_analysis.jsonl
│   │   └── ...
│   ├── final/                          # Canonical merged sets (source of truth)
│   │   ├── virgil_train.jsonl
│   │   └── virgil_eval.jsonl
│   └── seeds/                          # High-quality hand-authored seeds
│
├── training/                           # Self-contained training environment
│   ├── README.md
│   ├── AGENTS.md
│   ├── requirements.txt
│   ├── configs/
│   │   ├── virgil_phi1_h100.yaml       # Production Unsloth QLoRA (phi-4)
│   │   ├── virgil_phi1_mac.yaml        # 24GB Mac testing
│   │   └── ...
│   ├── scripts/
│   │   ├── train_virgil_phi1.py        # Pure Unsloth trainer
│   │   ├── prepare_virgil_data.py
│   │   └── launch_runpod.sh
│   └── data/                           # Snapshot for immediate training runs
│       ├── virgil_phi1_train.jsonl
│       └── virgil_phi1_eval.jsonl
│
├── scripts/                            # Post-synthesis tooling
│   ├── merge_v0_2.py
│   ├── audit_v0_2.py
│   ├── build_instructions.py
│   └── ...
│
└── docs/
    └── DATASET_CARD*.md
```

---

## The 10M Token Plan (100k at a time)

We are scaling the **10 specialized subagent swarm** (Log Analysis, Adversarial Intuition & Tradecraft, Hypothesis Testing, Evidence Evaluation, Lead Prioritization, Cross-Domain Correlation, SOC Operational Reasoning, etc.).

Each agent run targets ~100k-150k new tokens of high-signal, defender-grounded, Holmes-reasoning examples.

Priority gaps (from last session):
- Deep log / telemetry interpretation (Windows ETW, auditd, eBPF, Sysmon)
- Adversarial OPSEC smell tests and tradecraft
- Multi-hypothesis elimination on realistic SOC timelines
- Cross-book correlation (Windows + Linux + network + Android)
- Operational decision making under uncertainty

After each swarm cycle, update `synthesis_registry.json`, rebuild `data/final/`, and (optionally) kick off an eval run using `training/evaluation/run_eval.py`.

---

## Previous Versions

- v0.2 snapshot lives in `data/final/virgil_train_v0.2.jsonl` + `virgil_eval_v0.2.jsonl`
- Full v0.2 report: `data/final/v0.2_report.json`

---

## Contributing / Continuing Work

1. Read `AGENTS.md` (this repo's version) + `training/AGENTS.md`
2. Run synthesis in 100k token batches using the swarm pattern
3. Keep `synthesis_registry.json` accurate
4. Always validate JSONL after appending (`python -c "import json; [json.loads(l) for l in open('file.jsonl')]"`)
5. Train early and often on the Mac config for fast feedback, then scale on H100

This repo is designed to be the permanent, clean home for the VIRGIL training effort.

The endpoint defenders of the future are counting on high-quality, well-balanced, reasoning-heavy synthetic data.

Let's build it.