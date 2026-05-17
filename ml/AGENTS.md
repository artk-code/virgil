# AGENTS.md — VIRGIL-ML (Git-Friendly Synthesis + Training)

**This is the clean, git-friendly home for VIRGIL synthetic training data and training code.**

Only original LLM-synthesized material (our work) lives here:
- `data/synthesis/*.jsonl` — per-book + cross-domain VIRGIL-format examples (messages + `<reasoning>` Holmes style + `<answer>` JSON)
- `data/final/` — merged ready-to-train sets
- `training/` — complete Unsloth configs + scripts for Mac 24GB + RunPod H100 (phi-4 QLoRA)

**Nothing copyrighted** (no PDFs, no book chunks, no parser/, no raw_text).
See [docs/SYNTHESIS_SOURCES.md](docs/SYNTHESIS_SOURCES.md) for the full approved public source policy and how agents must work (read public material → synthesize original Holmes questions only).

---

## Current State (see synthesis_registry.json for live numbers)

- ~275k tokens in the raw synthesis layer (286 records across 11 generalized topic files)
- Final merged train set: 13,689 examples (v0.2 baseline including deterministic v0.1 MITRE/Sigma + hand seeds + early book synthesis)
- **Goal**: 10M well-balanced tokens for VIRGIL-PHI1 (strong endpoint investigator / "Sherlock of SOC")
- Active tracks: virgil_phi1_investigative (main swarm file), linux_forensics, lolbin_detection, red_team_operations, windows_internals, mobile_app_analysis + others

**Synthesis style (mandatory)**: Every `<reasoning>` block must be Holmes-like deductive reasoning:
- Observe every concrete detail in the chunk/scenario/telemetry
- Explicitly note what is *missing* that a benign explanation would require
- Form multiple hypotheses
- Systematically eliminate the impossible/unlikely
- Land on the single most likely attacker activity (with MITRE when applicable)
- Recommend precise, prioritized defender actions / telemetry / hunts

Bad (tautological): "The chunk talks about X so the answer is X."
Good: Long paragraph that eliminates benign causes using timing, absent artifacts, process ancestry, etc.

---

## How to Continue Synthesis (100k token batches)

1. Pick a focus area from `synthesis_registry.json` (or add a new one).
2. Use the 10-agent swarm pattern from the last session (specialized agents: Log Analysis, Adversarial Intuition, Hypothesis Testing, Lead Prioritization, Cross-Domain Correlation, SOC Operational Reasoning, etc.).
3. Each agent appends high-quality records to the appropriate generalized topic file:
   - Main cross-domain reasoning → `virgil_phi1_investigative.jsonl`
   - Specialized domains → `linux_forensics.jsonl`, `windows_internals.jsonl`, `mobile_app_analysis.jsonl`, `red_team_operations.jsonl`, `lolbin_detection.jsonl`, `soc_investigation_training.jsonl`, `osint_investigation.jsonl`, `sigma_detection.jsonl`, `kev_exploitation.jsonl`, `deep_technical_detection.jsonl`
4. Every record must be valid JSONL: full VIRGIL `{"messages": [system, user, assistant], "meta": {...}}`
5. After a batch (aim ~30-60 new high-quality examples per agent run = ~100k tokens), re-run the registry scanner (or manually update) and validate JSON.
6. When ready, re-build the final set:
   ```bash
   cd training
   python scripts/prepare_virgil_data.py \
     --input_files ../data/synthesis/virgil_phi1_investigative.jsonl ../data/synthesis/*.jsonl \
     --output_dir data \
     --eval_ratio 0.05
   ```
7. Copy the new `data/virgil_phi1_train.jsonl` + eval into `data/final/` (and back into `training/data/` for the next training run).

**Coordination**: Multiple agents can work in parallel on different task types or different source files. Always check the target JSONL for recent `meta.source_ids` to avoid duplicates.

---

## Training (Mac + RunPod + Unsloth)

Everything is in `training/`:

```bash
# On RunPod H100 (recommended for 10M token runs)
python training/scripts/train_virgil_phi1.py --config training/configs/virgil_phi1_h100.yaml

# On local Mac 24GB (testing / small experiments)
python training/scripts/train_virgil_phi1.py --config training/configs/virgil_phi1_mac.yaml --force-mac
```

See `training/README.md` for full RunPod volume, rclone, cost estimates, and Unsloth details.

Configs already target `microsoft/phi-4` with optimized LoRA for reasoning (rslora, 8-bit adamw, packing, etc.).

---

## File Reference (what lives where)

| Path | Purpose |
|------|---------|
| `data/synthesis/` | All raw synthetic output (append here during swarm) |
| `data/final/` | Canonical merged train/eval (v0.2 + latest synthesis) |
| `data/seeds/` | Hand-authored high-quality seeds |
| `training/data/` | Self-contained snapshot for immediate training runs |
| `training/configs/` | H100, Mac, LoRA, cloud-full variants |
| `training/scripts/` | `train_virgil_phi1.py` (pure Unsloth), `prepare_virgil_data.py`, launch_runpod.sh |
| `scripts/` | merge_v0_2.py, audit_*.py, build_instructions.py, expand_synthetic.py |
| `synthesis_registry.json` | Live counts, token estimates, task breakdown per source |
| `AGENTS_synthesis_v0.3_legacy.md` | Historical reference (old book-based structure — no longer used) |

---

## Git Notes

- All JSONL files are text and version-control friendly.
- Large final train sets (~25MB) are acceptable; use Git LFS only if individual files exceed ~100MB in the future.
- `.gitignore` should ignore `training/outputs/`, `*.pyc`, wandb/, and any local model caches.

**This repo is now the single source of truth for VIRGIL-ML data and training.** The old virgil-dataset-v0.2/ tree with PDFs and chunks can be archived or deleted.

Welcome to the clean 10M-token build. Let's fill it 100k at a time.