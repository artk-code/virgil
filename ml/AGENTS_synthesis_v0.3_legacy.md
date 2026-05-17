# AGENTS.md

**What changed / Why future agents will be 3x faster**

This v0.3-draft of AGENTS.md was written after the first synthesis agent had to re-explore the entire repo, discover the new `get_uncovered_chunks.py` helper, figure out the 12-book manifest, learn the parser/ staging workflow, and reverse-engineer good answer JSON schemas for the general_security and linux books.

Key upgrades for the next tired agent who just woke up:
- Explicit "canonical working tree" is now `virgil-dataset-v0.2/virgil-dataset/` (root manifest + root scripts are legacy copies).
- A 9-step "Quickstart checklist (Mode B)" that gets you producing real Q&A in <2 minutes.
- Fully worked batching + claiming + parallel-coordination instructions using the new `scripts/get_uncovered_chunks.py` helper (the exact while-loop pattern is here).
- Complete precise `<answer>` JSON schemas (every key listed) for the 4 general_security tasks and 5 practical_linux_forensics tasks.
- A new "Holmes-like deductive style" section with good/bad <reasoning> examples so reasoning tags are actually diagnostic instead of tautological.
- Updated 12-book corpora table, file reference for parser/ + get_uncovered_chunks.py, and clear v0.3 direction note.

Future parallel workers (Grok, Claude, humans) should now be able to start, stay safe across disconnects, coordinate without collisions, and produce high-quality defender-grounded data immediately.

---

Instructions for AI coding agents (Claude Code, Cursor, etc.) working in this
repository. Read this file first when you arrive.

This is the **VIRGIL Advisor training dataset** — instruction-tuning data for a
small fine-tuned LLM that helps the VIRGIL endpoint security platform reason
about MITRE ATT&CK, detections, and host telemetry.

The dataset already exists at v0.2 (see `README.md` and `docs/DATASET_CARD_v0.2.md`).
Most of the work an agent does here is **expanding the book-grounded slice**
via synthetic Q&A generation from chunks in `books/chunks/`.

---

## §1. Run modes — which one are you?

### The manifest is your entrypoint

**Critical first fact:** The canonical working tree is `virgil-dataset-v0.2/virgil-dataset/`.
All synthesis work (reading chunks, writing qa_raw, editing manifest) happens inside that directory. The manifest.json and scripts at the workspace root (`/home/parallels/virgil-training-data-files/`) are **legacy copies** from the v0.2 snapshot and should be ignored for day-to-day agent work.

Before reading anything else, `cd` into the canonical tree and check **`books/manifest.json`**. It lists every PDF that has been ingested, the assigned domain, the synthesis persona to use, the task types in scope, and a `synthesis_status` field. Your job is usually to process every source where `synthesis_status == "pending"`.

```bash
# From inside virgil-dataset-v0.2/virgil-dataset/
# See what's still pending (the ones you should work on):
jq '.sources | to_entries[] | select(.value.synthesis_status == "pending") | .key' books/manifest.json
```

There are now **12 sources** total (6 original v0.2 + 6 newly ingested toward v0.3):

| short_name                    | domain             | n_chunks | persona summary (see full in manifest)                  | task_types count |
|-------------------------------|--------------------|----------|---------------------------------------------------------|------------------|
| android_malware_handbook      | android            | 110      | Google Android Security reverse engineer                | 5                |
| art_of_mac_malware            | macos              | 96       | Patrick Wardle / Objective-See style macOS researcher   | 5                |
| day_zero_to_zero_day          | vuln_research      | 108      | CVE-shipping vulnerability researcher (precursor focus) | 5                |
| ghidra_book                   | reverse_engineering| 183      | Senior Ghidra/RE workflow expert                        | 5                |
| red_team_engineering          | red_team           | 101      | Senior red-team operator teaching defenders             | 5                |
| windows_security_internals    | windows            | 204      | James Forshaw-tier Windows internals + kernel security  | 5                |
| attacking_network_protocols   | general_security   | 107      | Broad endpoint security engineer                        | 4                |
| black_hat_go                  | general_security   | 119      | Broad endpoint security engineer                        | 4                |
| bug_bounty_bootcamp           | general_security   | 133      | Broad endpoint security engineer                        | 4                |
| game_hacking                  | general_security   | 99       | Broad endpoint security engineer                        | 4                |
| gtfo                          | general_security   | 200      | Broad endpoint security engineer (GTFOBins-style)       | 4                |
| practical_linux_forensics     | linux              | 138      | Linux EDR engineer (auditd/ebpf/Falco/containers)       | 5                |

The manifest entry for a source tells you everything you need (example for a new general_security book):

```json
{
  "short_name": "gtfo",
  "domain": "general_security",
  "persona": "You are a senior security engineer with broad endpoint experience. You translate technical concepts into actionable defender guidance.",
  "task_types": ["concept_explanation", "telemetry_recommendation", "detection_engineering", "incident_response_reasoning"],
  "n_chunks": 200,
  "chunks_jsonl": "books/chunks/gtfo.jsonl",
  "qa_output_target": "books/qa_raw/gtfo.jsonl",
  "synthesis_status": "pending"
}
```

Read chunks from `chunks_jsonl`, generate Q&A per the persona and task_types (see §3 for exact schemas), write to `qa_output_target`. When done, update `synthesis_status` to `"done"`.

### Adding new PDFs to the pipeline

New PDFs are staged in the `parser/` directory at the workspace root (or copied there). Use the root-level `pdf_to_training.py` (or the copy inside `virgil-dataset-v0.2/virgil-dataset/scripts/`) to process them:

```bash
# From workspace root
python3 pdf_to_training.py parser/PracticalLinuxForensics.pdf --domain linux

# Or directory of new PDFs
python3 pdf_to_training.py parser/ --domain general_security
```

The script extracts text, semantic-chunks at ~600 words on paragraph boundaries, drops front/back matter, writes chunks + raw_text into `parser/parsed/`, and produces a local manifest entry. You (or a human) then promote the resulting `.jsonl` chunk files into `virgil-dataset-v0.2/virgil-dataset/books/chunks/`, update the canonical `books/manifest.json` (add the source with `synthesis_status: "pending"`), and clean up `parser/parsed/` if desired. `parser/` is the **staging area** — never synthesize directly from chunks that only live under `parser/parsed/`.

### Mode A: Direct API (you have an `ANTHROPIC_API_KEY`)

You're running standalone Python with metered API access. ...

(Mode A instructions unchanged from v0.2 — the API runner still works for the original 6 books whose profiles live in `scripts/synthesize_book_qa.py`.)

### Mode B: Agent mode (Claude Max subscription / Claude Code / Claude in chat)

You're an AI agent ... You ARE the synthesis engine.

**Manifest-driven workflow (recommended):**

1. `cd virgil-dataset-v0.2/virgil-dataset`
2. Load `books/manifest.json` and filter to entries where `synthesis_status == "pending"`
3. For each pending source (claim first — see below):
   a. Read `chunks_jsonl` (path from manifest) — **use the helper** (next section)
   b. Use the entry's `persona` as your synthesis-time character
   c. Pick task types from the entry's `task_types` list (round-robin or per-chunk fit)
   d. Generate 2–4 Q&A pairs per chunk per the §3 schema + Holmes deductive style
   e. Append to `qa_output_target` as JSONL (one record per line)
   f. When the source is fully processed (0 uncovered chunks), update its `synthesis_status` to `"done"`

**Quickstart checklist for a synthesis agent (Mode B) — follow this in order**

1. `cd /home/parallels/virgil-training-data-files/virgil-dataset-v0.2/virgil-dataset` (this is now the only place that matters).
2. Run `jq '.sources | to_entries[] | select(.value.synthesis_status == "pending") | .key' books/manifest.json` — pick one book that nobody else has claimed.
3. **Claim the book**: Edit `books/manifest.json` and change that book's `"synthesis_status"` from `"pending"` to `"in_progress"`. Save. (This is the coordination signal.)
4. Run the helper for your first safe batch:
   `python3 scripts/get_uncovered_chunks.py --book <short_name> --max 12 --with-text`
   (add `> /tmp/next_batch.json` if you want the output on disk).
5. For each returned chunk, craft 2–4 examples:
   - User question in real SOC-analyst voice (never "Explain the concept of X").
   - `<reasoning>` in Holmes-like deductive style (see new section below).
   - `<answer>{...}</answer>` using the exact schema for the chosen task (see §3).
6. Append each complete record (the big `{"messages": [...], "meta": {...}}` object) as one line to the `qa_output_target` path shown in the manifest.
7. After the batch finishes, re-run the `get_uncovered_chunks.py` command for the same book — it will automatically skip anything already in `qa_raw/*.jsonl`.
8. Repeat steps 4–7 until the helper reports 0 uncovered chunks for that book.
9. Update the manifest entry: set `"synthesis_status": "done"`.
10. Optionally run `python3 scripts/merge_v0_2.py` and `python3 scripts/audit_v0_2.py` (they work without an API key) to produce a fresh training snapshot, or wait until a human triggers the release.

**Batching for interruption-safety (greatly expanded)**

Never try to synthesize an entire 100–200 chunk book in one go. Use the dedicated helper that was added precisely for this:

```bash
# From inside virgil-dataset-v0.2/virgil-dataset/
python3 scripts/get_uncovered_chunks.py --book gtfo --max 12 --with-text
# or (lighter, for planning only)
python3 scripts/get_uncovered_chunks.py --book windows_security_internals --max 20
```

The helper:
- Reads the live `books/manifest.json` to locate the chunks file and the qa_output_target.
- Scans the existing `qa_raw/<book>.jsonl` (if any) and collects every `meta.source_ids` value that has already been covered.
- Returns only chunks that have **zero** synthesized examples so far.
- Supports `--with-text` (full text for synthesis) or preview-only mode.
- Is completely safe to re-run after every batch or after a disconnect.

**Recommended agent loop pattern (copy-paste this):**

```bash
#!/bin/bash
# run_synthesis_gtfo.sh
BOOK="gtfo"
MAX=12
while true; do
    echo "=== $(date) Fetching next uncovered batch for $BOOK ==="
    python3 scripts/get_uncovered_chunks.py --book "$BOOK" --max "$MAX" --with-text > /tmp/next_batch.json 2>/dev/null || true

    COUNT=$(python3 -c "import json,sys; print(len(json.load(open('/tmp/next_batch.json'))))" 2>/dev/null || echo 0)
    if [ "$COUNT" -eq 0 ]; then
        echo "All chunks for $BOOK are covered. Marking done and exiting."
        # (human or you) jq-edit the manifest to "done"
        break
    fi

    echo "Synthesizing $COUNT chunks..."
    # === YOUR WORK HERE ===
    # 1. Read /tmp/next_batch.json
    # 2. For each chunk: generate 2-4 Q&A records using the book's persona + task_types + §3 schemas + Holmes reasoning
    # 3. Append each full record object (as a single JSON line) to books/qa_raw/${BOOK}.jsonl
    #    (use python or `cat >> books/qa_raw/${BOOK}.jsonl` carefully)
    # 4. (optional) git add + commit the qa_raw file after each batch for safety

    echo "Batch complete. Sleeping 5s before next check..."
    sleep 5
done
```

**Claiming a book (coordination primitive)**
Before you start heavy work on a book, edit `books/manifest.json` (with your editor or via `jq` + `sponge`) and set:

```json
"synthesis_status": "in_progress"
```

for that source. Other agents (or humans) scanning the manifest will see it is claimed and will pick a different pending book. When you finish the last chunk, change it to `"done"`.

**Parallel worker coordination**

Multiple agents (Grok instances, Claude Code sessions, humans) can and should work simultaneously:

- **Preferred pattern**: Assign each worker a different book (e.g., one does all 5 general_security books, one does practical_linux_forensics, one finishes the last windows chunks). This eliminates almost all contention.
- **Same-book parallel is safe** because `get_uncovered_chunks.py` computes the covered set from the live `qa_raw/<book>.jsonl` on every invocation. Two agents asking for `--max 10` at the same moment will receive disjoint sets (the second run sees whatever the first just appended).
- **Race condition to avoid**: Two agents appending to the exact same `qa_raw/*.jsonl` file at the exact same second. Coordinate via:
  - Git (`git pull; append; git add books/qa_raw/xxx.jsonl; git commit -m "synthesis: 12 gtfo chunks"`).
  - A shared `CLAIMS.md` or `WORK_LOG.txt` at the dataset root ("@grok-3: claiming gtfo, batch 3, chunks 45-56").
  - Simple chat/hand-off ("I'm about to do 10 more on linux, you take black_hat_go").
- Never edit `qa_raw` for the same book at the literal same instant. The helper + short batches + git makes this trivial to avoid.
- If a worker dies mid-batch, the next `get_uncovered...` run simply reclaims the still-uncovered chunks. No lost work.

---

## §2. The corpora

### v0.1 sources (already processed — `parsed/`)

- **MITRE ATT&CK STIX 2.1** — 697 techniques, 1758 analytics, 174 groups, 821 software
- **SigmaHQ rules** — 3,728 community detection rules (87% MITRE-tagged)
- **SwiftOnSecurity sysmon-config** — 724 Windows Sysmon rule lines with expert rationale

Do **not** re-run v0.1 parsing unless the source repos have updated...

### v0.2 + v0.3-expansion sources (book chunks — `books/chunks/`, registered in `books/manifest.json`)

PDFs ingested via `scripts/pdf_to_training.py` (or the parser/ staging flow). The manifest inside `virgil-dataset-v0.2/virgil-dataset/books/manifest.json` is the source of truth.

| Source                          | Domain             | Chunks | Notes |
|---------------------------------|--------------------|--------|-------|
| Android Malware Handbook        | `android`          | 110    | APK / dex / manifest / Play Protect |
| The Art of Mac Malware          | `macos`            | 96     | Mach-O, launchd, XPC, code signing |
| Windows Security Internals      | `windows`          | 204    | Tokens, ACLs, ETW, kernel objects (Forshaw-tier) |
| From Day Zero to Zero Day       | `vuln_research`    | 108    | Exploit primitives, precursor telemetry |
| Red Team Engineering            | `red_team`         | 101    | OPSEC, infra, anticipation for defenders |
| The Ghidra Book                 | `reverse_engineering` | 183 | Disasm, RE workflow, function ID |
| Attacking Network Protocols     | `general_security` | 107    | Protocol abuse, network telemetry |
| Black Hat Go                    | `general_security` | 119    | Go-based offensive tooling & detection |
| Bug Bounty Bootcamp             | `general_security` | 133    | Web/appsec concepts mapped to endpoint |
| Game Hacking                    | `general_security` | 99     | Game cheats, anti-cheat, memory abuse |
| GTFO                            | `general_security` | 200    | GTFOBins / LOLBins style living-off-the-land |
| Practical Linux Forensics       | `linux`            | 138    | auditd, eBPF, containers, persistence, privesc |

Run `jq '.sources | keys' books/manifest.json` (from the canonical tree) to see the live list. Each chunk has the same shape as before (`chunk_id`, `book`, `pages`, `first_heading`, `text`).

---

## §3. Output schema — what you produce

Every example must match the exact format shown in the original AGENTS.md (messages array + meta). The assistant turn is always:

```
<reasoning>plain-prose chain of thought, 3-6 sentences, Holmes deductive style</reasoning>
<answer>{valid JSON object whose schema fits the task}</answer>
```

### Task types — pick one per example (now 12 books)

The original six books keep their task definitions (see the v0.2 text for `apk_triage` through `binary_triage` — they are unchanged).

#### general_security books (attacking_network_protocols, black_hat_go, bug_bounty_bootcamp, game_hacking, gtfo)

All five books share the same four task types and the same defender-focused persona. Use these exact `<answer>` schemas (every key must be present):

- `concept_explanation`
  ```json
  {
    "concept": "string (concise name of the idea from the chunk)",
    "defender_friendly_explanation": "string (1-3 sentences, SOC-analyst language)",
    "why_relevant_to_endpoint_defense": "string (why an EDR/SOC person should care)",
    "key_telemetry_or_artifacts": ["string", "..."],
    "mitre_techniques": ["Txxxx", "Txxxx.yyy"] or [],
    "suggested_hunt_or_detection": "string (brief actionable idea)"
  }
  ```

- `telemetry_recommendation`
  ```json
  {
    "scenario": "string (the situation described in the chunk)",
    "recommended_data_sources": ["Sysmon EID 1", "auditd execve", "eBPF tracepoint X", "..."],
    "rationale": "string (why this telemetry catches the thing)",
    "sample_detection_logic": "string (short pseudo-query or rule sketch)",
    "potential_fps": "string (realistic false-positive sources and how to tune)",
    "mitre_techniques": ["Txxxx", ...] or []
  }
  ```

- `detection_engineering`
  ```json
  {
    "detection_title": "string",
    "core_logic": "string (what the detection looks for, in plain English)",
    "primary_data_sources": ["string", "..."],
    "mitre_techniques": ["Txxxx", ...] or [],
    "tuning_notes": "string (how to reduce noise, what thresholds, context needed)",
    "priority": "high" | "medium" | "low"
  }
  ```

- `incident_response_reasoning`
  ```json
  {
    "initial_observation": "string (what the analyst sees in telemetry)",
    "most_likely_attacker_activity": "string (Txxxx + short description)",
    "eliminated_alternatives": "string (why this is unlikely to be benign)",
    "immediate_actions": ["string", "string", "..."],
    "follow_on_hunting": ["string", "..."],
    "containment_options": ["string", "..."]
  }
  ```

#### practical_linux_forensics (the one linux book)

Five Linux-specific tasks. Use these exact schemas:

- `linux_persistence`
  ```json
  {
    "mechanism": "string (e.g. systemd service, cron, LD_PRELOAD, .desktop autostart)",
    "typical_artifacts": ["string", "string", "..."],
    "mitre_techniques": ["T1543.002", "T1053.003", ...] or [],
    "monitoring_telemetry": ["auditd watch on /etc/systemd/system", "eBPF exec + file events", "file integrity on ~/.config/autostart", "..."],
    "detection_recommendation": "string (concrete rule or query idea)"
  }
  ```

- `ebpf_telemetry`
  ```json
  {
    "ebpf_technology_or_hook": "string (tracepoint, kprobe, uprobe, LSM hook, ringbuf, etc.)",
    "events_or_data_provided": ["string", "..."],
    "defender_applications": ["Falco", "Tracee", "custom BCC/libbpf", "Cilium", "..."],
    "example_defensive_use": "string (real SOC or detection use case)",
    "limitations_or_noise": "string (what it misses or over-reports)"
  }
  ```

- `kernel_module_abuse`
  ```json
  {
    "abuse_pattern": "string (e.g. rootkit loading via insmod, signed-but-malicious module, LKMs for hiding)",
    "required_capabilities_or_privs": ["CAP_SYS_MODULE", "CAP_SYS_ADMIN", "root", "..."],
    "observable_indicators": ["string (modprobe logs, /proc/modules anomalies, dmesg)", "..."],
    "mitre_techniques": ["T1014", "T1547.006", ...] or [],
    "prevention_or_detection": "string (recommended control or telemetry rule)"
  }
  ```

- `container_escape`
  ```json
  {
    "escape_technique": "string (e.g. privileged container + hostPath, CAP_SYS_ADMIN + mount, dirty pipe via /proc, etc.)",
    "prerequisites": ["privileged: true", "CAP_SYS_ADMIN", "hostPID + hostPath volume", "..."],
    "host_telemetry_signals": ["string (auditd mount events, eBPF container escape probes, unexpected /proc writes)", "..."],
    "mitre_techniques": ["T1611", "T1068", ...] or [],
    "defensive_recommendations": "string (runtime policy, seccomp, user namespaces, Falco rule, etc.)"
  }
  ```

- `linux_privesc_reasoning`
  ```json
  {
    "privesc_vector": "string (SUID binary, sudo misconfig, kernel vuln, capability abuse, namespace escape, etc.)",
    "conditions_for_success": "string (what the attacker needs on the box)",
    "telemetry_signature": ["string (auditd USER_AUTH + USER_CMD, eBPF setuid, unexpected setcap)", "..."],
    "mitre_techniques": ["T1068", "T1548.001", "T1548.003", ...] or [],
    "response_or_hunt_priority": "string (immediate actions + high-value hunt)"
  }
  ```

(For the original six books' task schemas, keep using the descriptions already present in the v0.2 AGENTS.md — they remain authoritative.)

---

### Holmes-like deductive style for `<reasoning>`

The `<reasoning>` block must read like Sherlock Holmes investigating a cyber incident on an endpoint.

**Voice**: You observe every concrete detail present in the chunk or the described telemetry. You explicitly note what is *missing* that would have been present in a benign explanation. You systematically eliminate impossible or unlikely benign causes. You arrive at the single most likely attacker activity (with MITRE ID when applicable) and the precise defensive response or telemetry action.

**Good example** (for a GTFO / general_security chunk about a particular LOLBin):

```
<reasoning>The chunk describes a binary that accepts a remote UNC path as an argument to a file-write operation and then immediately executes the written file via CreateProcess. In the observed telemetry we see the parent process (explorer.exe or a browser) spawning this binary with a command line containing \\attacker-share\payload.dll followed 800 ms later by the same path appearing as the image of a new process. A benign user or scheduled task would almost never combine an outbound UNC write with immediate local execution of that exact path; normal software either writes locally first or uses a well-known temp directory with a random name. The timing, the UNC source, and the lack of any corresponding prefetch or recent-file artifact for a legitimate download eliminate the "user double-clicked a document" hypothesis. The only remaining coherent explanation is that an attacker used the binary's remote-file feature as a download-and-execute primitive (T1105 + T1059.003 via LOLBin). We should therefore hunt for this exact parent-child + UNC pattern and block the binary from being spawned by non-admin Office or browser processes.</reasoning>
```

**Bad example** (just restates the future answer — do not do this):

```
<reasoning>The chunk talks about how the binary can be abused for remote execution. Therefore the answer is that this is a download-and-execute technique mapped to T1105.</reasoning>
```

Always prefer the first style. It trains the model to perform actual forensic elimination rather than pattern matching.

---

## §4–§9 (rest of document)

The remaining sections (§4 Constraints, §5 Common tasks, §6 Things NOT to do, §7 File reference, §8 Quality bar, §9 Versioning & releases) are updated only in the places below for brevity. All original guidance on non-verbatim, SOC voice, MITRE citation, variety, and quality bar remains in force and is even more important with the new broader books.

### Updates to §5 Common tasks (batching / resume)

Add this new bullet:

### "Resume or safely batch using the helper"

```bash
python3 scripts/get_uncovered_chunks.py --book <short_name> --max 15 --with-text
# then synthesize only those, append, repeat
```

The helper completely replaces the old "read the qa_raw and collect source_ids yourself" manual step.

### Updates to §7 File reference (new & important entries)

| Path | Purpose |
|------|---------|
| `books/manifest.json` | **Registry of all 12 PDF sources** (canonical copy lives in `virgil-dataset-v0.2/virgil-dataset/books/manifest.json`) |
| `scripts/get_uncovered_chunks.py` | **New helper** — returns only still-uncovered chunks for a book by scanning the live qa_raw file. Use for every batch and every resume. Supports `--max`, `--with-text`, JSON output. |
| `parser/` | **Staging area for fresh PDFs**. Drop new `.pdf` files here, run `python3 parser/parser.py` or the root `pdf_to_training.py`, review the produced chunks under `parser/parsed/chunks/`, then promote good ones into the main `books/chunks/` tree and update the canonical manifest. Never synthesize directly from `parser/parsed/` output. |
| `virgil-dataset-v0.2/virgil-dataset/` | The **only canonical working tree** for synthesis agents. All `books/`, `scripts/`, `qa_raw/` work happens here. |

(Other rows in the table remain valid but paths are understood to be relative to the canonical tree.)

### Updates to §9 Versioning & releases

Current: **v0.2** (May 2026) — six books fully synthesized.

We are now actively expanding toward **v0.3** on top of the v0.2 snapshot by ingesting and synthesizing the six new books (five general_security + one linux). When the new synthesis is complete, merged, and audited, we will create `instructions_v0.3/`, update `DATASET_CARD_v0.3.md`, and bump the top-level README + this file. Never overwrite earlier `instructions_v0.X/` directories.

---

**You now have everything a fresh agent needs.**
Start with the Quickstart checklist, claim a book, run the helper for your first batch of 12, and begin producing. Welcome to the VIRGIL dataset expansion. The endpoint defenders of the future are counting on your grounded, deductive, non-verbatim work.