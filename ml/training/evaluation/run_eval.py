#!/usr/bin/env python3
"""
VIRGIL Automated Evaluation Runner

This is the core script for measuring whether fine-tuning is actually helping VIRGIL
become a better endpoint investigative agent.

Usage:
    python evaluation/run_eval.py \
        --model_path microsoft/phi-4 \
        --tasks hypothesis_testing,evidence_evaluation \
        --output_dir ./eval_results/phi4_baseline
"""

import argparse
import json
import os
from pathlib import Path
from typing import List, Dict, Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from tqdm import tqdm

from .metrics import compute_virgil_score
from .judge import VIRGILJudge


def load_tasks(task_names: List[str], tasks_dir: str = "evaluation/tasks") -> List[Dict]:
    """Load evaluation tasks from JSONL files."""
    all_tasks = []
    for task_name in task_names:
        task_file = Path(tasks_dir) / f"{task_name}.jsonl"
        if not task_file.exists():
            print(f"Warning: Task file {task_file} not found. Skipping.")
            continue
        with open(task_file, "r") as f:
            for line in f:
                task = json.loads(line)
                task["task_type"] = task_name
                all_tasks.append(task)
    return all_tasks


def generate_response(model, tokenizer, prompt: str, max_new_tokens: int = 1024) -> str:
    """Generate a response from the model."""
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            temperature=0.7,
            do_sample=True,
            pad_token_id=tokenizer.eos_token_id,
        )
    response = tokenizer.decode(outputs[0], skip_special_tokens=True)
    # Extract only the assistant part if using chat template
    if "<|assistant|>" in response:
        response = response.split("<|assistant|>")[-1].strip()
    return response


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_path", type=str, required=True, help="Path or HF ID of the model to evaluate")
    parser.add_argument("--tasks", type=str, default="all", help="Comma-separated list of tasks or 'all'")
    parser.add_argument("--output_dir", type=str, required=True, help="Where to save results")
    parser.add_argument("--judge_model", type=str, default="Qwen/Qwen3.5-72B-Instruct", help="Judge model for LLM-as-Judge")
    parser.add_argument("--max_samples", type=int, default=None, help="Limit number of examples per task")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    print(f"Loading model: {args.model_path}")
    model = AutoModelForCausalLM.from_pretrained(
        args.model_path,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=True)

    # Load tasks
    if args.tasks == "all":
        task_files = [f.stem for f in Path("evaluation/tasks").glob("*.jsonl")]
    else:
        task_files = [t.strip() for t in args.tasks.split(",")]

    tasks = load_tasks(task_files)
    if args.max_samples:
        tasks = tasks[: args.max_samples]

    print(f"Loaded {len(tasks)} evaluation examples across {len(task_files)} tasks.")

    judge = VIRGILJudge(model_name=args.judge_model)

    results = []
    for task in tqdm(tasks, desc="Evaluating"):
        prompt = task["input"]  # Assuming input is already formatted
        generated = generate_response(model, tokenizer, prompt)

        # Get judge scores
        judge_result = judge.score(
            input_text=task["input"],
            model_output=generated,
            reference=task.get("reference"),
            task_type=task.get("task_type", "general"),
        )

        result = {
            "id": task.get("id"),
            "task_type": task.get("task_type"),
            "input": task["input"],
            "generated": generated,
            "judge_scores": judge_result,
        }
        results.append(result)

    # Save raw results
    output_file = Path(args.output_dir) / "results.jsonl"
    with open(output_file, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    # Compute aggregate metrics
    summary = compute_virgil_score(results)
    summary_path = Path(args.output_dir) / "summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nEvaluation complete. Results saved to {args.output_dir}")
    print("Summary:")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
