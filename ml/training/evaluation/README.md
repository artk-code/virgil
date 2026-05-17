# VIRGIL Evaluation Framework

This is the most important part of the training infrastructure.

The goal of this evaluation system is to give us **fast, reliable, and actionable feedback** on whether changes to data, training configuration, or model architecture are actually improving VIRGIL as an endpoint investigative agent.

## Philosophy

- Generic benchmarks (MMLU, GPQA, etc.) are **secondary**.
- We primarily care about VIRGIL’s ability to do **real investigative reasoning** on endpoint security data.
- Evaluation must be **fast enough to run after every major experiment** (target: < 45 minutes for a full run on a strong judge model).
- We combine **LLM-as-Judge** (for scale) with **lightweight human review** (for calibration).

## Core Evaluation Dimensions

We evaluate models across these key capabilities:

1. **Hypothesis Generation & Testing**
   - Can the model generate multiple plausible hypotheses given partial evidence?
   - Can it correctly eliminate impossible or low-probability ones?

2. **Evidence Evaluation**
   - Can it assess the strength, reliability, and relevance of different pieces of evidence?

3. **Lead Prioritization**
   - Given multiple leads or observables, can it rank them by investigative value?

4. **Structured Decision Making**
   - Does it produce clean, usable JSON output that matches our expected schemas?
   - Are the recommended actions actually helpful for a SOC analyst?

5. **Domain Reasoning**
   - Does it correctly apply knowledge from Windows internals, Linux forensics, Android RE, Red Team tradecraft, etc.?

## Evaluation Task Format

Each evaluation task is stored as a JSONL file with the following structure:

```json
{
  "id": "win_token_0042",
  "category": "hypothesis_testing",
  "difficulty": "medium",
  "input": "We observed a low-privileged IIS worker process calling ImpersonateNamedPipeClient...",
  "reference": {
    "most_likely_hypothesis": "...",
    "eliminated_hypotheses": [...],
    "recommended_actions": [...]
  },
  "rubric": {
    "key_points": [...]
  }
}
```

## Running Evaluation

```bash
python evaluation/run_eval.py \
    --model_path <hf_path_or_local> \
    --tasks hypothesis_testing,evidence_evaluation,lead_prioritization \
    --judge_model Qwen3.5-72B-Instruct \
    --output_dir ./eval_results/virgil-phi1-v0.1
```

## LLM-as-Judge Prompt

The judge prompt lives in `evaluation/judge/virgil_judge_prompt.txt`.

It is designed to score the model on:
- Correctness of reasoning
- Quality of hypothesis elimination
- Actionability of recommendations
- Adherence to VIRGIL output format

We calibrate the judge periodically with human ratings.

## Current Task Categories

- `hypothesis_testing`
- `evidence_evaluation`
- `lead_prioritization`
- `incident_response_reasoning`
- `source_credibility_assessment`
- `investigative_pivot_reasoning`
- `dex_reasoning` (Android)
- `binary_triage` (Android native)
- `red_team_anticipation`
- `opsec_tradeoff`

## How to Add a New Evaluation Task

1. Create a new JSONL file in `evaluation/tasks/`.
2. Add 30–100 high-quality examples.
3. Update `evaluation/tasks/registry.json`.
4. Test the new task with the judge prompt.
5. Document why this task matters for VIRGIL.

## Iteration Loop (Recommended)

1. Make a change (new data, different LoRA config, new base model, etc.)
2. Run a small training job (1–2 epochs on a subset).
3. Run the full evaluation suite.
4. Analyze results per category (especially weak areas).
5. Decide next change.

The faster and more reliable this loop is, the faster we can improve VIRGIL.

## Current Status

- [ ] Core evaluation pipeline working
- [ ] 300+ high-quality eval examples across categories
- [ ] Judge prompt calibrated against human ratings
- [ ] Automated reporting (scores per category + qualitative examples)

This system is what allows us to move from "we trained something" to "we know it got better at X and worse at Y, so next we should...".