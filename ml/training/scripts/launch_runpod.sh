#!/bin/bash
#
# VIRGIL RunPod Launch Helper
# Quick commands for spinning up H100 training pods with data mounted.
#
# Usage:
#   bash training/scripts/launch_runpod.sh help
#   bash training/scripts/launch_runpod.sh create-volume
#   bash training/scripts/launch_runpod.sh upload-data
#   bash training/scripts/launch_runpod.sh run-training
#

set -e

echo "🚀 VIRGIL RunPod Launch Helper"
echo "=============================="

case "$1" in
  create-volume)
    echo ""
    echo "1. Go to RunPod → Storage → Volumes"
    echo "2. Create a new Network Volume:"
    echo "   - Name: virgil-training-data"
    echo "   - Size: 300GB or more"
    echo "   - Region: Same as where you'll run your pods"
    echo ""
    echo "After creating, note the Volume ID (you'll attach it when launching a pod)."
    ;;

  upload-data)
    echo ""
    echo "Fastest ways to upload your training data:"
    echo ""
    echo "Option A (Recommended): rclone"
    echo "  rclone copy ./training/data/ runpod:virgil-training-data/ --progress"
    echo ""
    echo "Option B: rsync over SSH (after pod is running)"
    echo "  rsync -avz --progress ./training/data/ root@<POD-IP>:/workspace/data/"
    echo ""
    echo "Tip: Create a RunPod Network Volume first, then upload to it."
    ;;

  run-training)
    echo ""
    echo "Inside the pod, run:"
    echo ""
    echo "  cd /workspace/training"
    echo "  pip install -r requirements.txt"
    echo ""
    echo "  # Full training run (H100)"
    echo "  python scripts/train_virgil_phi1.py --config configs/virgil_phi1_h100.yaml"
    echo ""
    echo "  # With W&B logging"
    echo "  wandb login"
    echo "  python scripts/train_virgil_phi1.py --config configs/virgil_phi1_h100.yaml"
    ;;

  help|*)
    echo ""
    echo "Available commands:"
    echo "  create-volume     → Instructions to create a Network Volume"
    echo "  upload-data       → Fastest ways to get your data onto RunPod"
    echo "  run-training      → Commands to start training inside the pod"
    echo ""
    echo "Typical workflow:"
    echo "  1. bash scripts/launch_runpod.sh create-volume"
    echo "  2. bash scripts/launch_runpod.sh upload-data"
    echo "  3. Launch H100 pod and attach the volume"
    echo "  4. bash scripts/launch_runpod.sh run-training"
    ;;
esac
