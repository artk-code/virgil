This directory contains the current training snapshot for VIRGIL-PHI1 (Unsloth).

Files here are copies of the latest from ../data/final/.

After running new synthesis:
1. Append to files in ../data/synthesis/
2. Run training/scripts/prepare_virgil_data.py (pointing at the synthesis files)
3. Copy the output train/eval back here and into ../data/final/

This keeps training/ runnable in isolation (e.g. when you rsync the training/ folder to a fresh RunPod pod).

Current snapshot date: 2026-05-16 (reorg)
Target: 10M tokens balanced reasoning data.