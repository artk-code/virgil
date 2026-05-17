# VIRGIL Training — VIRGIL-PHI1 (Phi-4)

This folder contains everything needed to fine-tune **VIRGIL-PHI1**, the main cloud/server version of the VIRGIL endpoint investigative agent.

**Current Target Model**: `microsoft/phi-4` (14B reasoning model) using Unsloth QLoRA.

---

## Directory Structure

We keep **everything** related to training inside this folder so it can eventually be moved into its own repository.

```bash
training/
├── AGENTS.md
├── README.md                          # This file
├── requirements.txt
├── configs/
│   ├── virgil_phi1_h100.yaml          # Production (H100/A100)
│   └── virgil_phi1_mac.yaml           # Local testing (24GB Mac)
├── scripts/
│   ├── train_virgil_phi1.py           # Main Unsloth training script
│   └── prepare_virgil_data.py
├── data/                              # ← Put your training data here
│   ├── virgil_phi1_train.jsonl
│   └── virgil_phi1_eval.jsonl
└── outputs/                           # Model checkpoints (add to .gitignore)
```

---

## How to Run Training

### On RunPod (H100 80GB) — Recommended

```bash
python scripts/train_virgil_phi1.py --config configs/virgil_phi1_h100.yaml
```

### On Local Mac (24GB)

```bash
python scripts/train_virgil_phi1.py --config configs/virgil_phi1_mac.yaml --force-mac
```

You can override any parameter:

```bash
python scripts/train_virgil_phi1.py \
    --config configs/virgil_phi1_h100.yaml \
    --lora_rank 16 \
    --learning_rate 1e-5 \
    --num_train_epochs 1.5
```

---

## RunPod Setup Guide (Fastest Way)

### 1. Create a Pod

**Recommended specs**:
- **GPU**: 1× **H100 80GB** (best price/performance)
- **Container Disk**: 100GB+
- **Volume Disk**: **300GB+** (this is critical)

**Container Image**:
- Use `unsloth/unsloth` (latest) — this is the fastest and most reliable option.

### 2. Mount Your Training Data (Fastest Methods)

**Best Practice**: Always use a **RunPod Network Volume**.

#### Recommended Fast Workflow

1. In RunPod, go to **Storage → Volumes** and create a new Network Volume (300GB+ recommended).
2. When launching your pod, **attach this volume**.
3. Mount it at `/workspace/data`.

#### Fastest ways to upload data (ranked):

| Method              | Speed      | Best For                  | Recommendation |
|---------------------|------------|---------------------------|----------------|
| **rclone**          | Very Fast  | Large datasets (recommended) | **Best choice** |
| **rsync over SSH**  | Fast       | Medium datasets           | Very good |
| RunPod Web UI       | Slow       | < 20GB only               | Avoid for 10M+ tokens |

**Example using rclone** (from your local machine):

```bash
# One-time setup (example with Google Drive or Backblaze B2)
rclone config

# Upload your data
rclone copy ./training/data/ runpod:virgil-data/ --progress
```

On the pod, your data will appear at the volume mount point (e.g. `/workspace/data`).

---

## Estimated Costs (10M Tokens, 2 Epochs, QLoRA)

| Hardware                  | Provider     | Approx. Cost | Time          | Notes |
|---------------------------|--------------|--------------|---------------|-------|
| **H100 80GB (Spot)**      | RunPod       | **$6 – $10**     | 2.5 – 3.5 hrs | **Recommended** |
| H100 80GB (On-demand)     | RunPod       | $12 – $18        | 2.5 – 3.5 hrs | More reliable |
| A100 80GB                 | RunPod       | $8 – $14         | 4 – 6 hrs     | Good alternative |
| Mac 24GB (M3/M4)          | Local        | Free             | 18 – 35 hrs   | Only for testing |

> These estimates assume good data packing and Unsloth optimizations. Real cost can vary ±25%.

---

## Data Organization

Keep your training data inside the `training/data/` folder:

```bash
training/data/
├── virgil_phi1_train.jsonl       # Main training set (~10M tokens)
├── virgil_phi1_eval.jsonl        # Evaluation set (recommended)
└── raw/                          # Optional: original source files
```

When running on RunPod, mount your Network Volume so that the `data/` folder points to persistent storage.

---

## Quick Tips

- Use the H100 config by default.
- Only use `--force-mac` when running locally on your 24GB Mac.
- Always use a Network Volume on RunPod for data and checkpoints.
- `rclone` is currently the fastest and most reliable way to move large training sets.

---

**This folder is designed to be self-contained** so it can be moved into its own repository later while remaining easy for both humans and AI agents to understand.

**Note on data sources (virgil-ml repo layout):**
The canonical synthesized data lives in `../data/final/` (and `../data/synthesis/` for raw per-source files).
`training/data/` contains a working snapshot of the current best `virgil_phi1_train.jsonl` / eval for immediate training runs.
After any new synthesis batch, re-run `prepare_virgil_data.py` and refresh both locations.

For agent-specific instructions, read `training/AGENTS.md` and the parent `../AGENTS.md`.

Happy training! 🚀
