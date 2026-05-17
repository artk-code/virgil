#!/usr/bin/env python3
"""
VIRGIL-PHI1 Training Script (Pure Unsloth)

Optimized for:
- RunPod H100 80GB (default / production)
- Local Mac 24GB (with --force-mac)

Usage:
    # RunPod H100 (default)
    python scripts/train_virgil_phi1.py --config configs/virgil_phi1_h100.yaml

    # Local Mac 24GB
    python scripts/train_virgil_phi1.py --config configs/virgil_phi1_mac.yaml --force-mac

    # Quick test on Mac with overrides
    python scripts/train_virgil_phi1.py --config configs/virgil_phi1_mac.yaml \
        --force-mac --num_train_epochs 0.2 --lora_rank 16
"""

import argparse
import os
import torch
from unsloth import FastLanguageModel
from datasets import load_dataset
from trl import SFTTrainer, SFTConfig
import yaml


def get_device_info():
    if torch.cuda.is_available():
        return "cuda", torch.cuda.get_device_name(0)
    elif torch.backends.mps.is_available():
        return "mps", "Apple Silicon (MPS)"
    else:
        return "cpu", "CPU"


def load_config(path):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="VIRGIL-PHI1 Unsloth Trainer")
    parser.add_argument("--config", type=str, required=True, help="Path to training config YAML")
    parser.add_argument("--force-mac", action="store_true", help="Force Mac-optimized settings (for 24GB Mac)")
    parser.add_argument("--learning_rate", type=float, default=None)
    parser.add_argument("--lora_rank", type=int, default=None)
    parser.add_argument("--num_train_epochs", type=float, default=None)
    parser.add_argument("--output_dir", type=str, default=None)
    args = parser.parse_args()

    config = load_config(args.config)
    device, device_name = get_device_info()

    print(f"Detected device: {device_name}")

    # === Platform-aware settings ===
    if args.force_mac or device == "mps":
        print("→ Using Mac-optimized settings (24GB unified memory)")
        load_in_4bit = True
        lora_rank = args.lora_rank or config.get("lora_rank", 16)
        per_device_batch_size = 1
        gradient_accumulation_steps = 16
        max_seq_length = 4096
    else:
        print("→ Using high-performance CUDA settings (H100/A100 recommended)")
        load_in_4bit = True
        lora_rank = args.lora_rank or config.get("lora_rank", 32)
        per_device_batch_size = config.get("per_device_train_batch_size", 2)
        gradient_accumulation_steps = config.get("gradient_accumulation_steps", 8)
        max_seq_length = config.get("max_seq_length", 8192)

    # === Load Model ===
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=config["model_name_or_path"],
        max_seq_length=max_seq_length,
        dtype=None,
        load_in_4bit=load_in_4bit,
        trust_remote_code=True,
    )

    model = FastLanguageModel.get_peft_model(
        model,
        r=lora_rank,
        target_modules=config.get(
            "lora_target_modules",
            ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        ),
        lora_alpha=config.get("lora_alpha", 32),
        lora_dropout=0.0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=3407,
        use_rslora=True,
    )

    # === Dataset ===
    dataset = load_dataset("json", data_files=config["dataset_path"], split="train")

    def formatting_func(example):
        return tokenizer.apply_chat_template(example["messages"], tokenize=False)

    # === Training Arguments ===
    output_dir = args.output_dir or config.get("output_dir", "outputs/VIRGIL-PHI1")
    learning_rate = args.learning_rate or config.get("learning_rate", 1.5e-5)
    num_train_epochs = args.num_train_epochs or config.get("num_train_epochs", 2.0)

    training_args = SFTConfig(
        output_dir=output_dir,
        per_device_train_batch_size=per_device_batch_size,
        gradient_accumulation_steps=gradient_accumulation_steps,
        warmup_steps=50,
        num_train_epochs=num_train_epochs,
        learning_rate=learning_rate,
        logging_steps=10,
        optim="adamw_8bit",
        weight_decay=0.01,
        lr_scheduler_type="cosine",
        seed=3407,
        report_to="wandb",
        run_name=config.get("run_name", "virgil-phi1-v1"),
        max_seq_length=max_seq_length,
        packing=True,
        dataset_text_field="text",
        save_strategy="steps",
        save_steps=300,
        save_total_limit=3,
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        formatting_func=formatting_func,
        args=training_args,
    )

    print(f"\n=== Starting VIRGIL-PHI1 Training ===")
    print(f"Device: {device_name}")
    print(f"LoRA rank: {lora_rank}")
    print(f"Learning rate: {learning_rate}")
    print(f"Epochs: {num_train_epochs}")
    print(f"Effective batch size: {per_device_batch_size * gradient_accumulation_steps}")
    print(f"Max sequence length: {max_seq_length}")
    print(f"Output directory: {output_dir}\n")

    trainer.train()
    trainer.save_model(os.path.join(output_dir, "final"))
    print(f"\nTraining complete. Model saved to {output_dir}/final")


if __name__ == "__main__":
    main()
