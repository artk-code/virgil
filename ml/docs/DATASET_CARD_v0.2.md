# VIRGIL Advisor Training Dataset — v0.2

Instruction-tuning corpus for fine-tuning a small LLM into the **VIRGIL Advisor**.

**v0.2** adds expert-book-grounded examples on top of the v0.1 MITRE/Sigma/sysmon
foundation. The new layer brings macOS, Windows internals, vulnerability research,
red-team operational anticipation, and reverse-engineering reasoning that no
public-corpus extraction can cover.

| Version | Records | Train | Eval | Synthesis |
|---|---:|---:|---:|---|
| v0.1 (May 2026) | 15,653 | 13,689 | 1,964 | Deterministic templates from MITRE STIX + Sigma + sysmon-config |
| **v0.2 (May 2026)** | **15,705** | **13,731** | **1,974** | **+ 52 hand-authored book examples** |
| v0.2 + synthesis (planned) | ~30,000–60,000 | ~26k–53k | ~3k–6k | + machine-synthesized from book chunks |

## What's new in v0.2

### 1. Six No-Starch expert books ingested

| Book | Lens | Pages | Chunks |
|---|---|---:|---:|
| Android Malware Handbook (Kuo & Carlsen) | APK/dex/manifest internals, Play Protect ML | ~500 | 110 |
| The Art of Mac Malware (Wardle) | Mach-O, persistence locations, code signing | ~250 | 96 |
| Windows Security Internals (Forshaw) | Tokens, ACLs, ALPC, ETW, kernel objects | ~600 | 204 |
| From Day Zero to Zero Day | Vuln classes, fuzzing, exploit precursors | ~370 | 108 |
| Red Team Engineering | C2, OPSEC, lateral movement, attacker decisions | ~340 | 101 |
| The Ghidra Book (Eagle & Nance) | RE workflow, disasm reasoning, attribution | ~600 | 183 |
| **Total** | | ~2,660 | **802 chunks** |

All ingestion is paraphrase-only synthesis — **no verbatim content** from any
copyrighted source is redistributed. The chunks live in `books/chunks/` only as
grounding for the synthesizer; they are never shipped as training data.

### 2. New task types (28 distinct task types in v0.2)

The book lens introduces 21 new task types beyond the v0.1 MITRE-anchored set:

- **Android (5):** `apk_triage`, `manifest_reasoning`, `dex_reasoning`, `mobile_persistence`, `android_evasion`
- **macOS (5):** `macos_persistence`, `code_signing_analysis`, `dylib_xpc_abuse`, `macos_malware_behavior`, `macos_evasion`
- **Windows internals (5):** `windows_internals_qa`, `token_acl_reasoning`, `etw_telemetry`, `kernel_object_security`, `windows_privesc_reasoning`
- **Vulnerability research (5):** `exploit_chain_precursors`, `vulnerability_class_reasoning`, `cve_to_telemetry`, `patch_diff_reasoning`, `fuzzing_to_detection`
- **Red team (5):** `red_team_anticipation`, `opsec_tradeoff`, `attacker_decision_tree`, `infra_pivot_reasoning`, `phishing_pretext`
- **Reverse engineering (5):** `disasm_reasoning`, `re_workflow`, `function_purpose_id`, `malware_attribution`, `binary_triage`

### 3. Hand-authored seed (52 examples, all 6 books)

Every book has at least 7 hand-authored Q&A pairs covering its highest-value task
types, demonstrating the quality bar and serving as few-shot exemplars for the
machine-synthesis run. Token-level overlap with source chunks was hand-controlled
to stay below 12-word verbatim spans.

## What's pending (your synthesis run)

The hand-authored seed proves the format works; the bulk expansion needs a
teacher-LLM run that this sandbox can't perform (no API key here). The runner is
fully implemented and turnkey:

```bash
# In your local environment, with VIRGIL dataset checked out:
export ANTHROPIC_API_KEY=sk-...
pip install anthropic

# Preview first (no API spend):
python3 scripts/synthesize_book_qa.py --books windows_security_internals \
        --per-chunk 3 --limit 3 --max-concurrency 2

# Real run — all 6 books, 3 Q&A per chunk:
python3 scripts/synthesize_book_qa.py --books all \
        --per-chunk 3 \
        --model claude-sonnet-4-6 \
        --max-concurrency 8

# Merge synthesized + seed + v0.1 into final v0.2 training files:
python3 scripts/merge_v0_2.py
```

### Expected synthesis output (rough sizing)

At `--per-chunk 3` on 802 chunks with ~70% post-leak-check survival:
- ~1,700 new machine-synthesized examples
- Combined with v0.1 + seed = **~15,500 v0.2 training examples**

### Cost estimate (your spend)

| Model | Cost per chunk | Total (802 chunks × 3 Q&A) | Notes |
|---|---:|---:|---|
| Claude Sonnet 4.6 | ~$0.030 | **~$24** | Recommended for quality |
| Claude Haiku 4.5 | ~$0.010 | **~$8** | Adequate when grounded in source chunks |

Costs scale linearly with `--per-chunk`. Recommend starting with `--per-chunk 3`
on Sonnet for the first wave, evaluate quality, then run `--per-chunk 5` only
on the rare-task chunks where you need more coverage.

## Non-verbatim guarantee — how it works

The runner enforces three layers of protection:

1. **Prompt instruction.** The teacher prompt explicitly forbids quoting more than
   ~12 consecutive words from the source, requires synthesized prose, and tells
   the teacher to reframe code snippets in its own commentary.
2. **Post-generation similarity check.** Every generated user-turn + reasoning is
   compared against the source chunk via word-level longest-common-substring. If
   any 13+ word span appears verbatim in the source, the example is dropped and
   the chunk is re-queued (up to 2 retries).
3. **Final audit.** After merge, `scripts/audit_v0_2.py` reports the verbatim-leak
   rate across the entire dataset for your inspection.

The dataset that ships contains **only** synthesized Q&A pairs that pass the
similarity check. The source chunks remain in `books/chunks/` for re-running
synthesis but are **not** part of the training files.

## Repository layout

```
virgil-dataset/
├── raw/                            # Source corpora — gitignored
│   ├── mitre-attack/               # MITRE STIX (v0.1)
│   ├── sigma/                      # SigmaHQ (v0.1)
│   └── sysmon-config/              # SwiftOnSecurity (v0.1)
├── parsed/                         # v0.1 intermediates
├── books/                          # v0.2 additions
│   ├── raw_text/                   # Extracted text per book
│   ├── chunks/                     # ~3-page semantic chunks per book
│   └── qa_final/
│       └── virgil_books_seed.jsonl # 52 hand-authored examples
├── instructions/                   # v0.1 outputs (preserved)
│   ├── virgil_train.jsonl
│   └── virgil_eval.jsonl
├── instructions_v0.2/              # v0.2 outputs
│   ├── virgil_train.jsonl
│   ├── virgil_eval.jsonl
│   └── v0.2_report.json
└── scripts/
    ├── parse_mitre.py              # v0.1 parsers
    ├── parse_sigma.py
    ├── parse_sysmon.py
    ├── build_instructions.py       # v0.1 instruction generator
    ├── extract_books.py            # v0.2: PDF → raw text
    ├── chunk_books.py              # v0.2: raw text → semantic chunks
    ├── seed_qa_batch_2.py          # v0.2: hand-authored examples generator
    ├── synthesize_book_qa.py       # v0.2: teacher-LLM Q&A generator (THE ONE TO RUN)
    ├── merge_v0_2.py               # v0.2: final merge into instructions_v0.2/
    ├── expand_synthetic.py         # v0.1 paraphrase expander (separate path)
    └── audit_dataset.py            # token + cost audit
```

## Fine-tuning quickstart (unchanged from v0.1)

Same Axolotl config, just point at `instructions_v0.2/virgil_train.jsonl`:

```yaml
base_model: Qwen/Qwen2.5-7B-Instruct
adapter: qlora
load_in_4bit: true
lora_r: 16
lora_alpha: 32
lora_target_linear: true

datasets:
  - path: instructions_v0.2/virgil_train.jsonl
    type: chat_template
    chat_template: chatml
    field_messages: messages

sequence_len: 2048
sample_packing: true
num_epochs: 3
micro_batch_size: 1
gradient_accumulation_steps: 8
learning_rate: 0.0002
bf16: true
output_dir: ./virgil-qwen7b-v0.2-lora
```

Training cost projection (v0.2, before synthesis expansion):
- Lambda A100 80GB @ $2.79/hr → ~$2 per run (3 epochs, ~0.7h)
- Lambda H100 SXM @ $3.99/hr → ~$1.70 per run

After synthesis expansion (~25–55k records), expect:
- 1.5–4 hours of A100 80GB time → **$4–$12 per training run**

## Eval methodology (v0.2 carries forward v0.1's discipline)

Three-axis evaluation on the held-out eval set:

1. **Technique-ID exact match** (B, C, F tasks): parse `<answer>`, compare
   `technique_id` to ground truth. Target: >70% F1.
2. **Structural validity** (all tasks): does every assistant turn produce
   parseable `<reasoning>...</reasoning><answer>{valid_json}</answer>`?
   Target: >99%.
3. **Reasoning quality** (sample-based human review): does the `<reasoning>`
   span show genuine technique-anchored thinking, or did the model collapse to
   pattern matching? Score on 50-sample random review per book.

If technique-ID F1 lifts ≥5pp over the stock base model AND structural validity
stays >99%, the v0.2 fine-tune is doing real work.

## Provenance + licensing

- Book content: each of the 6 No-Starch books is purchased and owned by the
  project owner. Source PDFs are NOT redistributed.
- The dataset that ships contains only **synthesized Q&A pairs that paraphrase
  but do not reproduce** book content.
- MITRE ATT&CK content: ©MITRE, used under ATT&CK Terms of Use (attribution required).
- Sigma rules: Detection Rule License (DRL) 1.1.
- SwiftOnSecurity sysmon-config: MIT-style permissive.
- This dataset's structure, generated examples, and code: MIT.

## Limitations & v0.3 roadmap

Still on the wishlist (carried from v0.1):

- **Linux endpoint coverage** is thin. Add Wazuh rule set, auditd rule corpora,
  Falco rules. Currently dominated by Windows in v0.1, somewhat balanced by Mac
  in v0.2.
- **False-positive examples.** Sigma `falsepositives` field and sysmon
  `exclude` rules give us labeled benign cases — a future `is_this_benign` task.
- **Multi-event kill-chain stitching.** Every example is single-event today.
- **Operator-voice Android slice.** The dataset owner is an SME on Android
  malware (co-author of the Android Malware Handbook, ex-Google Play Protect
  team) and plans an authoring pass where he writes ideal expert answers for a
  structured set of Android scenarios in his own voice. That slice will be the
  uniquely high-signal data nobody else has.
