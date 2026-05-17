#!/usr/bin/env python3
"""
Generate instruction-tuning examples from the parsed MITRE/Sigma/sysmon corpora.

Methodology follows CyberLLM-FINDS (arXiv 2601.06779): instruction-tuned
domain adaptation around the MITRE ATT&CK taxonomy with chain-of-thought
prompts.

Output format: OpenAI-compatible "messages" JSONL — directly consumable by
Axolotl, Unsloth, TRL SFTTrainer, and Together/Fireworks fine-tuning APIs.

Each line:
  {
    "messages": [
      {"role": "system", "content": "..."},
      {"role": "user", "content": "..."},
      {"role": "assistant", "content": "<reasoning>...</reasoning>\\n<answer>...</answer>"}
    ],
    "meta": {"task": "...", "source_ids": [...], "split": "train"}
  }

Tasks produced:
  A. technique_explanation   - explain a MITRE technique with CoT
  B. procedure_to_technique  - given a procedure description, identify technique
  C. sigma_to_technique      - given a Sigma rule, identify which technique
  D. technique_to_detection  - how would you detect technique X
  E. sysmon_rationale        - explain a SwiftOnSecurity sysmon rule
  F. event_to_technique      - given a synthesized endpoint event, classify
  G. mitigation_recommend    - given a technique, recommend mitigations
"""
from __future__ import annotations
import json
import random
import re
import textwrap
import yaml
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
PARSED = ROOT / "parsed"
OUT = ROOT / "instructions"
OUT.mkdir(parents=True, exist_ok=True)

random.seed(7)  # reproducible

SYSTEM_PROMPT = (
    "You are VIRGIL-Advisor, the endpoint-detection assistant inside the VIRGIL "
    "security platform. You reason about MITRE ATT&CK techniques, detection logic, "
    "and host telemetry. Wrap your step-by-step reasoning in <reasoning>...</reasoning> "
    "tags, then give the final structured response in <answer>...</answer> tags. "
    "Be precise; cite ATT&CK IDs in the form Txxxx or Txxxx.yyy."
)


def jsonl_iter(path: Path):
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def clean_text(s: str | None) -> str:
    """Light cleanup of MITRE description text: collapse whitespace, strip markdown citations."""
    if not s:
        return ""
    # Remove inline citation tokens like (Citation: FireEye 2017) which clutter descriptions
    s = re.sub(r"\(Citation:[^)]+\)", "", s)
    # Strip MITRE-internal markdown links: [Name](https://attack.mitre.org/...)
    s = re.sub(r"\[([^\]]+)\]\(https?://attack\.mitre\.org/[^)]+\)", r"\1", s)
    # Strip other markdown links but keep label
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def truncate(s: str, n: int) -> str:
    s = clean_text(s)
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


def example(task: str, system: str, user: str, assistant: str, source_ids: list[str], split: str = "train") -> dict:
    return {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ],
        "meta": {
            "task": task,
            "source_ids": source_ids,
            "split": split,
        },
    }


# ---------------------------------------------------------------------------
# Load corpora
# ---------------------------------------------------------------------------
techniques = list(jsonl_iter(PARSED / "mitre_techniques.jsonl"))
techniques_by_id = {t["id"]: t for t in techniques}
tactics = list(jsonl_iter(PARSED / "mitre_tactics.jsonl"))
mitigations_by_id = {m["id"]: m for m in jsonl_iter(PARSED / "mitre_mitigations.jsonl")}
software_by_id = {s["id"]: s for s in jsonl_iter(PARSED / "mitre_software.jsonl")}
groups_by_id = {g["id"]: g for g in jsonl_iter(PARSED / "mitre_groups.jsonl")}
sigma_rules = list(jsonl_iter(PARSED / "sigma_rules.jsonl"))
sigma_by_tech = json.loads((PARSED / "sigma_by_technique.json").read_text())
sysmon_rules = list(jsonl_iter(PARSED / "sysmon_rules.jsonl"))


# Pick a held-out evaluation set of techniques (~10%) — those records get split="eval"
# This way the same technique never bleeds across train/eval via different task types.
all_tids = sorted(techniques_by_id.keys())
random.Random(13).shuffle(all_tids)
eval_tids = set(all_tids[: max(50, len(all_tids) // 10)])

def split_for(tid: str) -> str:
    return "eval" if tid in eval_tids else "train"


# ---------------------------------------------------------------------------
# Task A: Technique explanation (CoT)
# ---------------------------------------------------------------------------
USER_A_TEMPLATES = [
    "Explain MITRE ATT&CK technique {tid} ({name}) and how a defender should think about it.",
    "What is {tid}? Walk through what it does, which tactic phase it serves, and what telemetry would surface it.",
    "I'm reviewing an alert mapped to {tid} — give me a concise briefing on this technique.",
    "Describe ATT&CK technique {tid} for an endpoint analyst, including platforms and detection ideas.",
]


def task_A_records():
    out = []
    for t in techniques:
        tid = t["id"]
        if not t["description"]:
            continue
        tactic_names = [x["name"] for x in t["tactics"] if x.get("name")]
        platforms = t["platforms"]
        det = t["detection"] or ""
        analytics = (t.get("detection_strategy") or {}).get("analytics") or []

        user = random.Random(hash(tid) & 0xFFFF).choice(USER_A_TEMPLATES).format(tid=tid, name=t["name"])

        # Build a chain-of-thought reasoning section
        reasoning_parts = [
            f"Technique {tid} is named '{t['name']}'.",
            f"It maps to the following ATT&CK tactic(s): {', '.join(tactic_names) or 'unspecified'}.",
            f"Affected platforms: {', '.join(platforms) or 'unspecified'}.",
            f"Core behavior: {truncate(t['description'], 800)}",
        ]
        if det:
            reasoning_parts.append(f"MITRE's published detection guidance: {truncate(det, 500)}")
        if analytics:
            ana = analytics[0]
            reasoning_parts.append(
                f"A concrete detection analytic ({ana['id']}): {truncate(ana['description'], 400)}"
            )
        if t["mitigations"]:
            mlist = ", ".join(f"{m['id']} {m['name']}" for m in t["mitigations"][:5])
            reasoning_parts.append(f"Relevant mitigations: {mlist}.")

        reasoning = " ".join(reasoning_parts)

        # Build the structured answer
        ans = {
            "technique_id": tid,
            "name": t["name"],
            "tactics": tactic_names,
            "platforms": platforms,
            "summary": truncate(t["description"], 350),
            "detection_pointers": (
                [truncate(det, 250)] if det else []
            ) + [truncate(a["description"], 200) for a in analytics[:2]],
            "top_mitigations": [{"id": m["id"], "name": m["name"]} for m in t["mitigations"][:3]],
        }
        assistant = f"<reasoning>{reasoning}</reasoning>\n<answer>{json.dumps(ans, ensure_ascii=False)}</answer>"
        out.append(example("technique_explanation", SYSTEM_PROMPT, user, assistant, [tid], split_for(tid)))
    return out


# ---------------------------------------------------------------------------
# Task B: Procedure description -> technique (TRAM-style)
# ---------------------------------------------------------------------------
USER_B_TEMPLATES = [
    "An analyst summarized adversary behavior as follows. Identify the MITRE ATT&CK technique.\n\nObservation: \"{proc}\"",
    "Map this procedure description to a single MITRE ATT&CK technique ID:\n\n\"{proc}\"",
    "Which ATT&CK technique best fits this observed activity?\n\n\"{proc}\"",
]


def task_B_records():
    out = []
    for t in techniques:
        tid = t["id"]
        for p in t["procedure_examples"]:
            proc = clean_text(p["procedure"])
            if len(proc) < 40 or len(proc) > 600:
                continue
            # Strip any literal mention of the technique ID from the prompt to avoid leakage
            proc_clean = re.sub(r"\bT\d{4}(?:\.\d{3})?\b", "[redacted]", proc)
            user = random.Random(hash((tid, p["actor_id"])) & 0xFFFF).choice(USER_B_TEMPLATES).format(proc=proc_clean)

            actor_kind = "group" if (p["actor_type"] == "intrusion-set") else "software"
            reasoning = (
                f"The observation describes activity attributed to {p['actor_name']} ({p['actor_id']}, a {actor_kind}). "
                f"The key behavior — {truncate(proc_clean, 280)} — corresponds to MITRE technique {tid} "
                f"({t['name']}), which is described as: {truncate(t['description'], 260)}. "
                f"This technique falls under the {', '.join(x['name'] for x in t['tactics']) or 'unspecified'} tactic."
            )
            ans = {
                "technique_id": tid,
                "technique_name": t["name"],
                "tactics": [x["name"] for x in t["tactics"]],
                "actor_attribution": {"id": p["actor_id"], "name": p["actor_name"], "type": p["actor_type"]},
                "confidence": "high",
            }
            assistant = f"<reasoning>{reasoning}</reasoning>\n<answer>{json.dumps(ans, ensure_ascii=False)}</answer>"
            out.append(example("procedure_to_technique", SYSTEM_PROMPT, user, assistant, [tid, p["actor_id"]], split_for(tid)))
    return out


# ---------------------------------------------------------------------------
# Task C: Sigma rule -> technique
# ---------------------------------------------------------------------------
USER_C_TEMPLATES = [
    "A SOC engineer wrote this Sigma rule. Which MITRE ATT&CK technique(s) does it primarily detect?\n\n```yaml\ntitle: {title}\nlogsource:\n  product: {product}\n  category: {category}\n  service: {service}\ndescription: {description}\ndetection:\n{detection}\n```",
    "Map this Sigma detection to the appropriate MITRE technique IDs:\n\nTitle: {title}\nLog source: product={product} category={category}\nDescription: {description}\nDetection logic:\n{detection}",
]


def indent(s: str, n: int = 2) -> str:
    pad = " " * n
    return "\n".join(pad + line for line in s.splitlines())


def task_C_records():
    out = []
    for r in sigma_rules:
        if not r["mitre_techniques"]:
            continue
        if not r["description"] or not r["detection_yaml"]:
            continue
        tids = r["mitre_techniques"]
        primary = tids[0]
        if primary not in techniques_by_id:
            continue
        t = techniques_by_id[primary]

        ls = r["logsource"]
        user = random.Random(hash(r["rule_id"]) & 0xFFFF).choice(USER_C_TEMPLATES).format(
            title=r["title"] or "",
            product=ls.get("product") or "",
            category=ls.get("category") or "",
            service=ls.get("service") or "",
            description=clean_text(r["description"])[:300],
            detection=indent(r["detection_yaml"][:1200]),
        )
        reasoning = (
            f"The rule '{r['title']}' has logsource product={ls.get('product')} "
            f"category={ls.get('category')} service={ls.get('service')}. "
            f"Its detection logic looks for: {truncate(r['description'], 220)}. "
            f"This behavior maps to MITRE technique {primary} ({t['name']}), "
            f"which is part of the {', '.join(x['name'] for x in t['tactics']) or 'unspecified'} tactic. "
            f"{('Secondary techniques tagged: ' + ', '.join(tids[1:]) + '. ') if len(tids) > 1 else ''}"
            f"Severity level set by the author: {r.get('level') or 'unspecified'}."
        )
        ans = {
            "primary_technique": primary,
            "all_techniques": tids,
            "sigma_rule_id": r["rule_id"],
            "logsource_product": ls.get("product"),
            "severity": r.get("level"),
        }
        assistant = f"<reasoning>{reasoning}</reasoning>\n<answer>{json.dumps(ans, ensure_ascii=False)}</answer>"
        out.append(example("sigma_to_technique", SYSTEM_PROMPT, user, assistant, [r["rule_id"], primary], split_for(primary)))
    return out


# ---------------------------------------------------------------------------
# Task D: Technique -> detection recommendation
# ---------------------------------------------------------------------------
USER_D_TEMPLATES = [
    "How should I detect MITRE technique {tid} on an endpoint? Suggest log sources and a detection approach.",
    "I need to write a detection for {tid} ({name}). What telemetry should I be looking at and what should the detection logic key on?",
    "We don't have coverage for {tid} yet. Recommend a detection strategy with concrete log sources.",
]


def task_D_records():
    out = []
    for t in techniques:
        tid = t["id"]
        ds = t.get("detection_strategy")
        if not ds or not ds.get("analytics"):
            continue
        if not t["description"]:
            continue
        user = random.Random(hash(tid) & 0xFFFF).choice(USER_D_TEMPLATES).format(tid=tid, name=t["name"])

        analytics = ds["analytics"]
        ana_lines = []
        for a in analytics[:4]:
            log_src_names = [ls["name"] for ls in a.get("log_sources", []) if ls.get("name")]
            ana_lines.append(
                f"- {a['id']} ({', '.join(a.get('platforms') or []) or 'any platform'}): "
                f"{truncate(a['description'], 350)} "
                f"Log sources: {', '.join(log_src_names) or 'unspecified'}."
            )

        # Cross-reference Sigma rules tagged with this technique as concrete examples
        sigma_examples = sigma_by_tech.get(tid, [])[:3]

        reasoning = (
            f"Technique {tid} ({t['name']}) involves: {truncate(t['description'], 300)} "
            f"MITRE has published detection strategy {ds['id']} for this technique, "
            f"composed of {len(analytics)} analytic(s). "
            f"The key analytics are:\n" + "\n".join(ana_lines)
        )
        if sigma_examples:
            reasoning += f"\nThere are {len(sigma_by_tech.get(tid, []))} community Sigma rules tagged for {tid} that can serve as starting points."

        ans = {
            "technique_id": tid,
            "detection_strategy_id": ds["id"],
            "log_sources": sorted({
                ls["name"]
                for a in analytics for ls in a.get("log_sources", [])
                if ls.get("name")
            }),
            "analytics": [
                {"id": a["id"], "summary": truncate(a["description"], 200), "platforms": a.get("platforms", [])}
                for a in analytics[:4]
            ],
            "existing_sigma_rules_available": len(sigma_by_tech.get(tid, [])),
        }
        assistant = f"<reasoning>{reasoning}</reasoning>\n<answer>{json.dumps(ans, ensure_ascii=False)}</answer>"
        out.append(example("technique_to_detection", SYSTEM_PROMPT, user, assistant, [tid, ds["id"]], split_for(tid)))
    return out


# ---------------------------------------------------------------------------
# Task E: Sysmon rule rationale
# ---------------------------------------------------------------------------
USER_E_TEMPLATES = [
    "I'm reviewing the SwiftOnSecurity sysmon config. This rule is in there — what is it watching for and why?\n\n```xml\n<{field} condition=\"{cond}\">{value}</{field}>\n```\nContext: Sysmon event ID {eid} ({event_name}), action=\"{action}\", section=\"{section}\".",
    "Explain this Sysmon rule: event_id={eid} ({event_name}), action={action}, field={field}, condition={cond}, value='{value}'. Section: {section}.",
]


def task_E_records():
    out = []
    for r in sysmon_rules:
        if not r["comment"]:
            continue
        comment = clean_text(r["comment"])
        if len(comment) < 15:
            continue
        user = random.Random(hash((r["event_id"], r["field"], r["value"])) & 0xFFFF).choice(USER_E_TEMPLATES).format(
            field=r["field"] or "",
            cond=r["condition"] or "",
            value=(r["value"] or "")[:200],
            eid=r["event_id"],
            event_name=r["event_name"] or "",
            action=r["action"] or "",
            section=r["section"] or "(unscoped)",
        )

        techs = r["mitre_techniques"]
        action_phrase = (
            "logs this event because it is suspicious"
            if r["action"] == "include"
            else "suppresses this event because it is known-benign noise"
        )
        reasoning_parts = [
            f"This is a sysmon event {r['event_id']} ({r['event_name']}) {r['action']}-rule from the "
            f"{r['section'] or 'unscoped'} section.",
            f"It matches {r['field']} {r['condition']} '{(r['value'] or '')[:160]}'.",
            f"The author's annotation reads: '{comment}'.",
            f"The rule {action_phrase}.",
        ]
        if techs:
            tech_blurbs = []
            for tid in techs[:3]:
                t = techniques_by_id.get(tid)
                if t:
                    tech_blurbs.append(f"{tid} ({t['name']})")
                else:
                    tech_blurbs.append(tid)
            reasoning_parts.append(f"Related MITRE technique(s): {', '.join(tech_blurbs)}.")
        reasoning = " ".join(reasoning_parts)

        ans = {
            "event_id": r["event_id"],
            "event_name": r["event_name"],
            "action": r["action"],
            "intent": comment,
            "related_techniques": techs,
            "is_suspicious_pattern": r["action"] == "include",
        }
        assistant = f"<reasoning>{reasoning}</reasoning>\n<answer>{json.dumps(ans, ensure_ascii=False)}</answer>"
        primary_tid = techs[0] if techs else None
        if primary_tid:
            sp = split_for(primary_tid)
        else:
            # Deterministic ~10% holdout based on the rule's natural key
            key = f"sysmon:{r['event_id']}:{r['field']}:{r['value']}"
            sp = "eval" if (abs(hash(key)) % 10) == 0 else "train"
        out.append(example("sysmon_rationale", SYSTEM_PROMPT, user, assistant, [f"sysmon:{r['event_id']}:{r['field']}"], sp))
    return out


# ---------------------------------------------------------------------------
# Task F: Synthesized endpoint event -> technique classification
#         (this is the actual VIRGIL runtime task)
# ---------------------------------------------------------------------------
def synth_event_from_sysmon(r: dict) -> dict | None:
    """Turn a sysmon include-rule into a plausible event JSON shaped like VIRGIL's schema."""
    if r["action"] != "include":
        return None
    eid = r["event_id"]
    field = r["field"]
    value = r["value"]
    if not value or len(value) > 200:
        return None
    base = {
        "event_id": eid,
        "event_type": r["event_name"],
        "host_id": "host-{:04d}".format(abs(hash(r["comment"])) % 10000),
        "user": "CORP\\user{}".format(abs(hash(field)) % 200),
        "timestamp": "2026-05-16T{:02d}:{:02d}:{:02d}Z".format(
            abs(hash(value)) % 24, abs(hash(field)) % 60, abs(hash(r["comment"])) % 60
        ),
    }
    if eid == 1:  # ProcessCreate
        base["image"] = value if field == "Image" else "C:\\Windows\\System32\\unknown.exe"
        base["command_line"] = value if field == "CommandLine" else value
        base["parent_image"] = "C:\\Windows\\explorer.exe"
        base["integrity_level"] = "Medium"
    elif eid == 3:  # NetworkConnect
        base["destination"] = value if field == "DestinationHostname" else "10.0.0.1"
        base["destination_port"] = 443
        base["protocol"] = "tcp"
        base["initiating_image"] = "C:\\Windows\\System32\\rundll32.exe"
    elif eid == 11:  # FileCreate
        base["target_filename"] = value if field == "TargetFilename" else value
        base["creating_image"] = "C:\\Windows\\System32\\unknown.exe"
    elif eid == 22:  # DnsQuery
        base["query_name"] = value if field == "QueryName" else value
        base["querying_image"] = "C:\\Program Files\\Unknown\\app.exe"
    else:
        base[field.lower()] = value
    return base


USER_F_TEMPLATES = [
    "The VIRGIL endpoint agent observed this raw event on a workstation. Classify it and recommend next action.\n\n```json\n{event}\n```",
    "Triage this endpoint telemetry event from a managed Windows host:\n\n```json\n{event}\n```\n\nReturn the most likely MITRE technique, a confidence rating, and the recommended response action.",
]


def task_F_records():
    out = []

    # ---- F1: events derived from sysmon include-rules with tagged techniques
    for r in sysmon_rules:
        evt = synth_event_from_sysmon(r)
        if evt is None or not r["comment"]:
            continue
        techs = r["mitre_techniques"]
        if not techs:
            continue
        primary = techs[0]
        t = techniques_by_id.get(primary)
        if not t:
            continue

        user = random.Random(hash(json.dumps(evt, sort_keys=True)) & 0xFFFF).choice(USER_F_TEMPLATES).format(
            event=json.dumps(evt, indent=2),
        )
        reasoning = (
            f"The event is a Sysmon event id {evt['event_id']} ({evt['event_type']}) on host {evt['host_id']}. "
            f"Key indicator: the SwiftOnSecurity baseline includes this exact pattern as a deliberate include-rule, "
            f"annotated as: '{clean_text(r['comment'])}'. "
            f"This pattern aligns with MITRE technique {primary} ({t['name']}), which is part of the "
            f"{', '.join(x['name'] for x in t['tactics']) or 'unspecified'} tactic. "
            f"Technique rationale: {truncate(t['description'], 240)}"
        )
        critical_tactics = {"initial-access", "execution", "privilege-escalation", "credential-access", "impact"}
        any_critical = any((tac.get("short_name") or "") in critical_tactics for tac in t["tactics"])
        severity = "high" if any_critical else "medium"
        action = "isolate_host_and_alert" if any_critical else "raise_alert_for_analyst_review"
        ans = {
            "technique_id": primary,
            "technique_name": t["name"],
            "tactics": [x["short_name"] for x in t["tactics"]],
            "confidence": "medium",
            "severity": severity,
            "recommended_action": action,
            "reasoning_summary": clean_text(r["comment"])[:200],
        }
        assistant = f"<reasoning>{reasoning}</reasoning>\n<answer>{json.dumps(ans, ensure_ascii=False)}</answer>"
        out.append(example("event_to_technique", SYSTEM_PROMPT, user, assistant,
                           [primary, f"sysmon:{r['event_id']}"], split_for(primary)))

    # ---- F2: events synthesized from Sigma rules (much broader coverage)
    out.extend(_sigma_to_event_records())
    return out


def _synth_event_from_sigma(rule: dict) -> dict | None:
    """Build a plausible endpoint event JSON that would trigger this Sigma rule.

    We extract literal field values from the rule's detection block. The
    'detection_yaml' string was rendered by our parser; we walk a re-parsed
    YAML structure to find concrete values without trying to interpret
    Sigma's full operator semantics — we just want a representative event.
    """
    try:
        det = yaml.safe_load(rule["detection_yaml"])  # type: ignore[name-defined]
    except Exception:
        return None
    if not isinstance(det, dict):
        return None

    ls = rule.get("logsource") or {}
    product = (ls.get("product") or "").lower()
    category = (ls.get("category") or "").lower()

    # Pull all (key, scalar_value) pairs from selection-like blocks
    fields: dict[str, object] = {}
    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "condition":
                    continue
                if isinstance(v, (dict, list)):
                    walk(v)
                else:
                    # Sigma field keys can have modifiers like Image|endswith
                    base = str(k).split("|", 1)[0]
                    # Take the first occurrence only (keep events simple)
                    fields.setdefault(base, v)
        elif isinstance(node, list):
            for item in node:
                walk(item)
    walk(det)
    if not fields:
        return None

    # Pick the first scalar value from any list-of-values fields
    def first_scalar(v):
        if isinstance(v, list):
            for x in v:
                if isinstance(x, (str, int, float)):
                    return x
            return None
        if isinstance(v, (str, int, float)):
            return v
        return None
    flat_fields: dict[str, str] = {}
    for k, v in fields.items():
        s = first_scalar(v)
        if s is not None:
            flat_fields[k] = str(s)
    if not flat_fields:
        return None

    # Shape into an event roughly matching VIRGIL's normalized schema
    rid = abs(hash(rule["rule_id"])) % 10000
    evt = {
        "host_id": f"host-{rid:04d}",
        "user": f"CORP\\user{rid % 200}",
        "timestamp": "2026-05-16T{:02d}:{:02d}:{:02d}Z".format(rid % 24, (rid * 7) % 60, (rid * 13) % 60),
        "logsource": {"product": ls.get("product"), "category": ls.get("category"), "service": ls.get("service")},
    }

    # Infer event_type from category + product
    if product == "windows" and category in ("process_creation", "create_process"):
        evt["event_type"] = "ProcessCreate"
        evt["event_id"] = 1
    elif product == "windows" and category in ("network_connection",):
        evt["event_type"] = "NetworkConnect"
        evt["event_id"] = 3
    elif product == "windows" and category in ("file_event", "file_create"):
        evt["event_type"] = "FileCreate"
        evt["event_id"] = 11
    elif product == "windows" and category in ("dns_query", "dns"):
        evt["event_type"] = "DnsQuery"
        evt["event_id"] = 22
    elif product == "windows" and category in ("registry_event", "registry_set", "registry_add"):
        evt["event_type"] = "RegistryEvent"
        evt["event_id"] = 13
    elif product == "linux":
        evt["event_type"] = f"linux.{category or 'audit'}"
    else:
        evt["event_type"] = f"{product or 'generic'}.{category or 'event'}"

    # Attach the literal field values (these would be the triggering observables)
    evt["fields"] = flat_fields
    return evt


def _sigma_to_event_records():
    """Per-Sigma event-classification examples for Task F."""
    out = []
    for r in sigma_rules:
        if not r["mitre_techniques"]:
            continue
        if not r["description"]:
            continue
        primary = r["mitre_techniques"][0]
        t = techniques_by_id.get(primary)
        if not t:
            continue
        evt = _synth_event_from_sigma(r)
        if evt is None:
            continue
        if len(evt.get("fields") or {}) == 0:
            continue

        user = random.Random(hash(r["rule_id"]) & 0xFFFF).choice(USER_F_TEMPLATES).format(
            event=json.dumps(evt, indent=2),
        )
        critical_tactics = {"initial-access", "execution", "privilege-escalation", "credential-access", "impact"}
        any_critical = any((tac.get("short_name") or "") in critical_tactics for tac in t["tactics"])

        # Severity blends Sigma's author-set level with tactic class
        sev_map = {"critical": "critical", "high": "high", "medium": "medium", "low": "low", "informational": "low"}
        author_sev = sev_map.get((r.get("level") or "").lower(), "medium")
        severity = "high" if any_critical and author_sev in ("medium", "high") else author_sev
        action = "isolate_host_and_alert" if severity in ("high", "critical") else "raise_alert_for_analyst_review"

        reasoning = (
            f"The event has logsource product={evt['logsource'].get('product')} "
            f"category={evt['logsource'].get('category')}. "
            f"The observed field values match a known detection pattern: '{r['title']}' "
            f"({truncate(r['description'], 220)}). "
            f"This pattern is tagged for MITRE technique {primary} ({t['name']}), "
            f"under the {', '.join(x['name'] for x in t['tactics']) or 'unspecified'} tactic. "
            f"Author-assigned severity: {r.get('level') or 'unspecified'}."
        )
        ans = {
            "technique_id": primary,
            "technique_name": t["name"],
            "tactics": [x["short_name"] for x in t["tactics"]],
            "matched_detection": {"sigma_rule_id": r["rule_id"], "sigma_title": r["title"]},
            "confidence": "medium" if author_sev in ("medium", "low") else "high",
            "severity": severity,
            "recommended_action": action,
        }
        assistant = f"<reasoning>{reasoning}</reasoning>\n<answer>{json.dumps(ans, ensure_ascii=False)}</answer>"
        out.append(example("event_to_technique", SYSTEM_PROMPT, user, assistant,
                           [primary, r["rule_id"]], split_for(primary)))
    return out


# ---------------------------------------------------------------------------
# Task G: Mitigation recommendation
# ---------------------------------------------------------------------------
USER_G_TEMPLATES = [
    "We've confirmed technique {tid} ({name}) is in use against our environment. What MITRE mitigations should we prioritize?",
    "Recommend mitigations for ATT&CK technique {tid}. Order by impact.",
    "An incident is confirmed mapped to {tid}. Which mitigations from M-codes should the incident commander reference?",
]


def task_G_records():
    out = []
    for t in techniques:
        if not t["mitigations"]:
            continue
        tid = t["id"]
        user = random.Random(hash(tid) & 0xFFFF).choice(USER_G_TEMPLATES).format(tid=tid, name=t["name"])
        mits = t["mitigations"][:6]
        mit_lines = []
        for m in mits:
            full = mitigations_by_id.get(m["id"])
            blurb = (full or {}).get("description", "")
            mit_lines.append(f"- {m['id']} {m['name']}: {truncate(m.get('note') or blurb, 220)}")
        reasoning = (
            f"For technique {tid} ({t['name']}), MITRE lists {len(t['mitigations'])} mitigations. "
            f"The highest-priority ones combine prevention (control surfaces that block the technique) "
            f"and detection (telemetry that surfaces it). Top candidates:\n" + "\n".join(mit_lines)
        )
        ans = {
            "technique_id": tid,
            "mitigations": [{"id": m["id"], "name": m["name"], "note": truncate(m.get("note", ""), 180)} for m in mits],
        }
        assistant = f"<reasoning>{reasoning}</reasoning>\n<answer>{json.dumps(ans, ensure_ascii=False)}</answer>"
        out.append(example("mitigation_recommend", SYSTEM_PROMPT, user, assistant, [tid], split_for(tid)))
    return out


# ---------------------------------------------------------------------------
# Run all tasks
# ---------------------------------------------------------------------------
def main() -> None:
    tasks = {
        "A_technique_explanation": task_A_records,
        "B_procedure_to_technique": task_B_records,
        "C_sigma_to_technique": task_C_records,
        "D_technique_to_detection": task_D_records,
        "E_sysmon_rationale": task_E_records,
        "F_event_to_technique": task_F_records,
        "G_mitigation_recommend": task_G_records,
    }
    all_records = []
    counts = {}
    for name, fn in tasks.items():
        recs = fn()
        counts[name] = len(recs)
        all_records.extend(recs)
        print(f"  {name:<35s} {len(recs):>6d} examples")

    # Shuffle for training, deterministic with seed
    random.Random(42).shuffle(all_records)

    train_path = OUT / "virgil_train.jsonl"
    eval_path = OUT / "virgil_eval.jsonl"
    n_train, n_eval = 0, 0
    with train_path.open("w") as ftrain, eval_path.open("w") as feval:
        for rec in all_records:
            (ftrain if rec["meta"]["split"] == "train" else feval).write(
                json.dumps(rec, ensure_ascii=False) + "\n"
            )
            if rec["meta"]["split"] == "train":
                n_train += 1
            else:
                n_eval += 1

    # Stats summary
    print(f"\nTotal: {len(all_records)} examples ({n_train} train, {n_eval} eval)")
    print(f"  wrote -> {train_path.relative_to(ROOT)}")
    print(f"  wrote -> {eval_path.relative_to(ROOT)}")

    # Per-task split sanity check
    by_task_split: dict[tuple[str, str], int] = defaultdict(int)
    for r in all_records:
        by_task_split[(r["meta"]["task"], r["meta"]["split"])] += 1
    print("\nPer-task counts:")
    for task, total in sorted(counts.items()):
        train = by_task_split.get((task.split("_", 1)[1], "train"), 0)
        evalc = by_task_split.get((task.split("_", 1)[1], "eval"), 0)
        print(f"  {task:<35s} train={train:>5d}  eval={evalc:>4d}")


if __name__ == "__main__":
    main()
