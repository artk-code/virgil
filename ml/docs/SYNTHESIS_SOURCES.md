# VIRGIL-ML Synthesis Sources Policy

## Core Rule (Non-Negotiable)

**All training data in this repository must be 100% original LLM-synthesized content.**

- We **never** include copyrighted text, book excerpts, PDFs, raw book chunks, or parser output.
- We **never** copy-paste from paid books, courses, or proprietary material.
- We **read** publicly available or legitimately purchased material **only as inspiration**.
- We then **create our own original scenarios, questions, and Holmes-style deductive reasoning chains**.

Every record must be generated in the VIRGIL format (`<reasoning>` Holmes analysis + structured `<answer>` JSON) by the swarm agents.

## Approved Source Categories for Synthesis

These are the **only** categories of material the synthesis swarm is allowed to draw from:

### 1. Publicly Licensed / Government Data (Strongly Preferred)
| Category                  | Examples                                      | Notes |
|---------------------------|-----------------------------------------------|-------|
| Sigma rules               | SigmaHQ public GitHub repo (https://github.com/SigmaHQ/sigma) | All rules are public. Always cite rule ID in `source_ids`. |
| CISA KEV                  | https://www.cisa.gov/known-exploited-vulnerabilities-catalog | Public US government data. Reference specific CVE. |
| MITRE ATT&CK              | https://attack.mitre.org/                     | Technique IDs, procedures, and detections are public. |
| GTFOBins / LOLBAS         | https://gtfobins.github.io/ and https://lolbas-project.github.io/ | Public living-off-the-land databases. |
| Sysmon / ETW schema       | Microsoft public documentation                | Official telemetry schemas. |

### 2. Public Technical Content (With Attribution in meta)
- Laurie Kirk (Windows internals, ETW, token abuse, kernel callbacks, etc.) — public YouTube + blog content
- Public Black Hat / DEF CON / Blue Team Village talks (when slides + videos are freely available)
- Open source project documentation (Velociraptor, OSQuery, Wazuh, Elastic, etc.)
- Public Microsoft Learn / Windows security documentation
- Public GitHub repositories with detection logic, PoCs, or telemetry research (properly licensed)

### 3. Cross-Domain Public OSINT
- Public threat intelligence reports (when freely published)
- Public blog posts from researchers who release their work openly
- Public CVE write-ups and exploit analyses on sites like exploit-db (for technique understanding only)
- Public GitHub security advisories, NVD entries, and vendor security posts for web framework vulnerabilities. Use these to synthesize defender scenarios, not runnable exploit instructions.
- Public GitHub PoC repositories and lab frameworks may be reviewed for telemetry understanding and safe lab design. Do not copy payloads, commands, or exploit workflows into learner-facing data.

## Strictly Forbidden

- Any paid book or course material (even if you own a copy)
- PDFs or chapters from "Art of Mac Malware", "Practical Linux Forensics", "Windows Security Internals", "Day Zero to Zero Day", Ghidra book, etc.
- Any content behind a paywall or license that prohibits derivative training use
- Direct quotes or close paraphrases from copyrighted sources
- Raw log samples copied from private customer environments or proprietary datasets

## How Agents Must Work (The Correct Process)

When an agent is assigned a topic (e.g., Sigma rule analysis or KEV exploitation):

1. **Read** the public source (Sigma rule YAML + comments, CISA KEV entry, public blog post, etc.).
2. **Extract** the technical essence (what the rule is trying to catch, what the exploit actually does, what telemetry is missing).
3. **Create an original VIRGIL scenario** — a realistic SOC/telemetry story that could plausibly occur in an enterprise.
4. **Write a Holmes-style user question** that forces the model to:
   - Observe every present detail
   - Note every critical absence
   - Form and eliminate hypotheses
   - Land on the most likely attacker activity + MITRE
   - Recommend precise defender actions / telemetry / hunts
5. **Output** a full VIRGIL JSONL record with proper `meta`:
   ```json
   "meta": {
     "task": "sigma_rule_logic_analysis",
     "source_ids": ["sigma-b9d9cc83"],
     "source_book": "sigma_detection",
     "source_pages": null,
     "split": "train",
     "synthesized": true
   }
   ```

The `source_ids` should point to the public identifier (Sigma rule ID, CVE, etc.). This allows traceability without ever including the original text.

## Recommended High-Value Public Sources for Next Waves

**Priority thin tracks (currently only 4 records each):**

- **sigma_detection** — Pull fresh rules from SigmaHQ GitHub (especially detection engineering, evasion, and high-fidelity rules for T1059, T1543, T1053, T1547, etc.)
- **kev_exploitation** — Use the current CISA KEV catalog. Focus on recent RCE chains, supply-chain compromises, and what telemetry would have caught them early.
- **deep_technical_detection** — Laurie Kirk style content (public YouTube + blogs on token impersonation, ALPC, ETW blind spots, kernel callbacks, setcb, etc.), combined with public Microsoft ETW/ETL documentation.

**Other strong public sources for volume:**
- LOLBAS / GTFOBins + public detection engineering blogs
- Public Velociraptor / OSQuery detection content
- Microsoft Sysmon configuration samples + public advanced Sysmon research
- Public Windows 10/11 ETW provider documentation
- Public framework advisories and safe lab references for SSRF/CSRF/RCE boundary analysis, especially when they improve cloud credential, egress, and inventory triage examples.

## Enforcement

- Before appending any new records, the swarm lead (or you) should verify `meta.source_book` uses only generalized topic names (never book titles).
- Run `python scripts/update_synthesis_registry.py` after every batch.
- If any record ever looks like it contains long verbatim text from a book or paid course → delete it immediately.

This policy keeps us clean for GitHub release and allows the broader VIRGIL community to use the dataset without legal risk.

---

**Last updated:** 2026-05-16
**Maintained by:** VIRGIL-ML synthesis swarm
