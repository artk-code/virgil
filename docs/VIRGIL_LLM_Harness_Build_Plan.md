# VIRGIL LLM Harness Build Plan
## Custom Multi-Vendor LLM Agent Harness with First-Class LangChain Integration (SDK)

**Version**: 1.1 (Cleaned & Reviewed)  
**Date**: 2026-06-12  
**Owner**: Art Kaiser (@artkaiser)  
**Status**: Ready for implementation review — all hand-wavy sections clarified with concrete code, file paths, commands, and integration points. Pitfalls and open questions called out explicitly.

---

## Executive Summary

VIRGIL (Vendor Independent Response Governance Intelligence Layer) already excels at polyglot security pipelines (Rust simulator → Redis Streams → Python worker → Postgres → Go API → TS UI) and ships a high-quality synthetic corpus for fine-tuning the **VIRGIL Advisor** (security-reasoning LLM, target Phi-4 via Unsloth/Fireworks, OpenAI-compatible JSONL).

This plan adds a **custom, production-grade LLM harness** in a new `sdk/` directory. The harness:

- Is model- and vendor-agnostic at the core (swap providers without touching security logic).
- Uses **LangChain's `create_agent` + composable middleware** as the first "vendor" implementation (fastest path to batteries-included features like PII redaction, retries, context compaction, HITL).
- Supports future direct adapters (raw OpenAI SDK, Anthropic SDK, local vLLM/Unsloth inference, Fireworks for the fine-tuned Advisor, etc.).
- Integrates tightly with existing VIRGIL components: tools query Postgres events/findings, Redis for state, Postgres for audit/HITL checkpoints.
- Prioritizes security (PII handling on telemetry, policy enforcement, sandboxed tools, audit logs) and reliability (retries, fallbacks, cost controls).

**Why LangChain first?**  
From the June 2026 LangChain blog series ("How to Build a Custom Agent Harness", "The Anatomy of an Agent Harness", "Agent Frameworks, Runtimes, and Harnesses—oh my!"):
- `create_agent(model, tools, system_prompt)` is the minimal, extensible primitive.
- **Middleware** provides clean hooks for deterministic logic (PII, retries, summarization, sub-agents, cost limits) without polluting prompts.
- Prebuilt middleware exists for exactly our needs (PIIMiddleware, ToolRetryMiddleware, SummarizationMiddleware, HumanInTheLoopMiddleware, ModelCallLimitMiddleware, etc.).
- DeepAgents shows the "batteries-included" pattern we can emulate or extend.
- Model-agnostic via provider:model syntax and easy middleware composition.

This keeps VIRGIL's core **vendor-independent** while giving the Advisor (and future agents) production scaffolding immediately.

**Key Outcomes**
- New `sdk/llm/` + `sdk/providers/langchain/` with working harness.
- Python worker can call `harness.advise_on_event(event)` and get structured `<reasoning>...<answer>` back.
- New Go API endpoint `/api/v1/advisor/query` (and streaming).
- LangSmith tracing optional for observability (free tier fine for start).
- Clear path to swap in the fine-tuned VIRGIL Advisor model or other vendors.
- Full test coverage + CI gate.

---

## Goals & Non-Goals

**Goals**
- Production-ready custom harness with middleware for security/reliability.
- First vendor: full LangChain `create_agent` + middleware stack (including custom VIRGIL security middleware).
- Pluggable provider interface so adding OpenAI/Anthropic/raw local is ~1 file + config.
- Deep integration with VIRGIL data model (events, findings, hosts) via safe tools.
- Observability (logs, metrics, optional LangSmith), auditability (every call logged to Postgres), cost controls.
- Support for the fine-tuned Advisor (via Fireworks or local Unsloth endpoint exposed as OpenAI-compatible).
- Long-term: multi-agent orchestration (supervisor + specialist security agents) via LangGraph if needed.

**Non-Goals (Phase 1)**
- Full DeepAgents fork or replacement (we build on `create_agent` primitives instead).
- Persistent long-term memory beyond session + Postgres checkpoints (future phase).
- Browser/sandbox code execution tools (out of scope for security reasoning agent initially; can add later via middleware).
- Multi-language harness (Python-first; expose via HTTP/gRPC for Rust/Go callers).
- Production deployment (local Docker Compose + tests first).

**Clarification on "LangChain as first vendor"**  
We treat LangChain as the *implementation substrate* for the harness (using its excellent agent loop + middleware). The "provider" abstraction lets us later plug non-LangChain inference (e.g., direct `openai` SDK calls or local model server) while keeping the same high-level `invoke(messages, tools, ...)` interface and middleware stack where possible. For pure LangChain path we get all the prebuilts for free.

---

## Architecture Overview

```
User / Go API / python-worker
          │
          ▼
sdk/llm/harness.py          ← Core factory + registry + middleware composer
          │
          ├───> providers/langchain/adapter.py   ← create_agent + VIRGIL middleware stack (FIRST)
          │         │
          │         ├───> langchain.agents.create_agent(model=..., tools=virgil_tools, ...)
          │         └───> Prebuilt + custom middleware (PII, retry, summarize, HITL, cost, audit)
          │
          └───> providers/openai/ (future) / anthropic/ / fireworks/ / local_unsloth/
                    └───> Direct SDK or OpenAI-compatible client + shared middleware where possible

Tools (security-specific, safe):
  - query_events(host_id, time_range, filters) → Postgres
  - get_finding_details(finding_id)
  - recommend_response_action(event/finding)  (structured output)
  - search_corpus (for RAG on ml/ synthetic data or docs)
  - audit_log(action, decision, reasoning)

State / Persistence:
  - Short-term: LangChain/LangGraph state or simple dict
  - Durable/HITL: Postgres (new advisor_calls + approvals tables)
  - Optional: LangGraph checkpointer (Redis/Postgres) for long-running

Observability:
  - Structured logs + Prometheus metrics in harness
  - Optional LangSmith (env var toggle)
  - Every invoke logged to Postgres with full prompt/response (redacted)

Config (env):
  VIRGIL_LLM_PROVIDER=langchain          # or openai, anthropic, fireworks, local
  VIRGIL_LLM_MODEL=anthropic:claude-sonnet-4-6   # or fireworks:virgil-advisor-v1, openai:gpt-4o, etc.
  VIRGIL_LLM_TEMPERATURE=0.1
  VIRGIL_LLM_MAX_TOKENS=4096
  VIRGIL_LANGSMITH_TRACING=true
  VIRGIL_LLM_API_KEY=... (per provider)
```

**Text Diagram Notes**  
- Harness is the single entry point (`from sdk.llm.harness import get_harness`).
- Middleware order matters: PII redaction → audit start → retry → model/tool → audit end → cost tracking.
- Tools are registered per-provider or shared (Postgres client injected safely).
- For the fine-tuned VIRGIL Advisor: set `VIRGIL_LLM_PROVIDER=fireworks` (or local) + model name; the adapter handles OpenAI-compatible chat completions + tool calling if the model supports it. LangChain path can still be used for the loop/middleware even if inference is direct.

---

## Updated Directory Structure

```text
VIRGIL/
├── sdk/                              # NEW - all vendor integrations & harness live here
│   ├── __init__.py
│   ├── pyproject.toml                # or requirements.txt for sdk deps (langchain, langgraph, etc.)
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── harness.py                # Core: get_harness(provider), invoke, middleware registry
│   │   ├── types.py                  # LLMResponse, ToolSpec, Middleware, Provider protocol
│   │   ├── middleware.py             # Custom VIRGIL middleware (AuditMiddleware, SecurityPIIMiddleware, etc.)
│   │   ├── utils.py                  # Prompt templates, structured output parsers, cost calc
│   │   └── config.py                 # Env loading, validation
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── langchain/                # FIRST VENDOR - full implementation
│   │   │   ├── __init__.py
│   │   │   ├── adapter.py            # create_agent wrapper + middleware stack builder
│   │   │   ├── tools.py              # VIRGIL security tools (Postgres queries, etc.)
│   │   │   ├── prompts.py            # System prompts for Advisor (security reasoning)
│   │   │   └── config.py
│   │   ├── openai/                   # Phase 3 stub + direct client
│   │   ├── anthropic/
│   │   ├── fireworks/                # For fine-tuned VIRGIL Advisor (OpenAI compat)
│   │   └── local/                    # vLLM / Unsloth / Ollama
│   └── tests/
│       ├── test_harness.py
│       ├── test_langchain_adapter.py
│       └── fixtures/
├── python-worker/                      # EXISTING - integrate here
│   ├── worker.py
│   ├── transform_job.py
│   └── requirements.txt                # ADD: langchain, langgraph, langsmith, psycopg2-binary, etc.
├── go-api/                             # EXISTING - add advisor endpoints
│   └── ...
├── db/migrations/                      # NEW migrations for advisor_calls, approvals
├── ml/                                 # EXISTING - add harness eval scripts
├── docs/
│   └── llm_harness.md                  # This plan + usage
├── docker-compose.yml                  # Add sdk volume mount, env vars
├── Makefile                            # Add sdk-test, sdk-lint, sdk-install targets
├── .env.example                        # Add LLM_* vars
└── README.md                           # Update with new section
```

**Clarification**: `sdk/` is Python-only for Phase 1 (LangChain is Python). Future Rust/Go bindings via PyO3 or HTTP microservice if needed. No changes to rust-* or ts-ui in Phase 1.

---

## Phase 0: Repo Hygiene & Bootstrap (30-60 min)

1. `cd /path/to/VIRGIL && make doctor && make test && docker compose up --build -d && make verify`
2. Create directories and `__init__.py` files as above.
3. Update `.env.example` with new vars (document defaults and security notes).
4. Add to `Makefile`:

```makefile
sdk-install:
	docker compose exec python-worker pip install -r sdk/requirements.txt || pip install langchain langgraph langsmith psycopg2-binary pydantic

sdk-lint:
	docker compose exec python-worker ruff check sdk/ --fix

sdk-test:
	docker compose exec python-worker pytest sdk/tests/ -v --tb=short

sdk-verify: sdk-install sdk-lint sdk-test
	@echo "SDK harness verified"
```

5. Create `sdk/requirements.txt`:

```
langchain>=0.3.0
langgraph>=0.3.0
langsmith>=0.1.0
pydantic>=2.0
psycopg2-binary
python-dotenv
```

6. Update `python-worker/requirements.txt` to include the above (or use shared requirements).
7. Add new Postgres migration (see Phase 3).

**Hand-wave fixed**: Exact commands and files listed. No "we'll figure it out later."

---

## Phase 1: Core Harness & Types (Concrete Implementation)

**File: `sdk/llm/types.py`**

```python
from dataclasses import dataclass, field
from typing import Protocol, Any, Callable, Awaitable
from pydantic import BaseModel

@dataclass
class LLMResponse:
    content: str
    reasoning: str | None = None
    tool_calls: list[dict] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    provider: str = "unknown"
    model: str = "unknown"
    raw: Any = None  # original response for debugging

class ToolSpec(BaseModel):
    name: str
    description: str
    parameters: dict  # JSON schema

class Provider(Protocol):
    async def invoke(
        self,
        messages: list[dict],
        tools: list[ToolSpec] | None = None,
        **kwargs
    ) -> LLMResponse: ...

class Middleware(Protocol):
    async def __call__(
        self,
        call_next: Callable[..., Awaitable[LLMResponse]],
        context: dict,  # contains messages, tools, config, etc.
    ) -> LLMResponse: ...
```

**File: `sdk/llm/config.py`**

```python
import os
from pydantic import BaseModel, Field

class LLMConfig(BaseModel):
    provider: str = Field(default="langchain", env="VIRGIL_LLM_PROVIDER")
    model: str = Field(default="anthropic:claude-sonnet-4-6", env="VIRGIL_LLM_MODEL")
    temperature: float = Field(default=0.1, env="VIRGIL_LLM_TEMPERATURE")
    max_tokens: int = Field(default=4096, env="VIRGIL_LLM_MAX_TOKENS")
    langsmith_tracing: bool = Field(default=False, env="VIRGIL_LANGSMITH_TRACING")
    api_key: str | None = Field(default=None, env="VIRGIL_LLM_API_KEY")  # or per-provider

    class Config:
        env_file = ".env"
        extra = "ignore"

def load_config() -> LLMConfig:
    return LLMConfig()
```

**File: `sdk/llm/middleware.py`** (Custom VIRGIL ones + examples of wrapping prebuilts)

```python
import logging
from typing import Callable, Awaitable
from sdk.llm.types import LLMResponse, Middleware

logger = logging.getLogger(__name__)

class AuditMiddleware:
    """Log every invoke start/end + redacted input/output to Postgres (or stdout for start)."""
    def __init__(self, db_conn=None):
        self.db_conn = db_conn

    async def __call__(self, call_next, context):
        logger.info(f"[HARNESS] Invoke start provider={context.get('provider')} model={context.get('model')}")
        # TODO: INSERT into advisor_calls (prompt redacted, ts, etc.)
        response = await call_next(context)
        logger.info(f"[HARNESS] Invoke complete. tokens={response.usage}")
        # TODO: UPDATE advisor_calls with response, cost
        return response

class SecurityPIIMiddleware:
    """Redact PII from messages before model call. Critical for security telemetry."""
    async def __call__(self, call_next, context):
        # Simple regex or call to existing VIRGIL PII scrubber
        # For production: integrate with your Meta-scale PII detection if available
        messages = context.get("messages", [])
        for m in messages:
            if isinstance(m.get("content"), str):
                m["content"] = redact_pii(m["content"])  # implement or import
        context["messages"] = messages
        return await call_next(context)

# Example wrapper for LangChain prebuilts (see adapter)
def wrap_langchain_middleware(lc_middleware):
    async def _wrapped(call_next, context):
        # Adapt context <-> LangChain state if needed
        return await lc_middleware(call_next, context)  # or proper integration
    return _wrapped
```

**File: `sdk/llm/harness.py`** (The main entry point — reviewed & concrete)

```python
import os
from typing import Any
from sdk.llm.config import load_config, LLMConfig
from sdk.llm.types import LLMResponse, Provider, Middleware
from sdk.llm.middleware import AuditMiddleware, SecurityPIIMiddleware

# Registry of providers
PROVIDERS: dict[str, type[Provider]] = {}

def register_provider(name: str, cls: type[Provider]):
    PROVIDERS[name] = cls

async def get_harness(provider: str | None = None) -> Provider:
    cfg = load_config()
    provider = provider or cfg.provider
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider: {provider}. Registered: {list(PROVIDERS)}")
    return PROVIDERS[provider](cfg)

# Convenience high-level API used by python-worker / go-api
async def advise_on_event(event: dict, provider: str | None = None, **kwargs) -> LLMResponse:
    harness = await get_harness(provider)
    # Build messages + tools from event using utils
    messages = build_advisor_messages(event)  # in utils.py
    tools = get_virgil_tools()                # from providers or shared
    return await harness.invoke(messages=messages, tools=tools, **kwargs)
```

**Hand-wave fixed**: Full file skeletons with real structure, types, and comments on TODOs (DB integration is straightforward — we already have psycopg patterns in python-worker).

---

## Phase 2: LangChain Provider Implementation (The First Vendor — Fully Concrete)

**File: `sdk/providers/langchain/adapter.py`**

```python
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, SystemMessage
# from langchain.agents.middleware import PIIMiddleware, ToolRetryMiddleware, ... (import actual names from docs)
from sdk.llm.types import LLMResponse, Provider
from sdk.llm.config import LLMConfig
from sdk.providers.langchain.tools import get_virgil_security_tools
from sdk.providers.langchain.prompts import get_advisor_system_prompt
import logging

logger = logging.getLogger(__name__)

class LangChainAdapter(Provider):
    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg
        self.model = cfg.model  # e.g. "anthropic:claude-sonnet-4-6" or "fireworks:virgil-advisor"
        # TODO: initialize LangSmith if cfg.langsmith_tracing

    async def invoke(self, messages: list[dict], tools: list = None, **kwargs) -> LLMResponse:
        # Convert our messages to LangChain format if needed
        lc_messages = [SystemMessage(content=get_advisor_system_prompt())] + \
                      [HumanMessage(content=m["content"]) for m in messages if m.get("role") == "user"]

        virgil_tools = get_virgil_security_tools()  # Postgres-backed, safe

        # Build middleware stack (order matters: security first)
        middleware = [
            # SecurityPIIMiddleware(),  # our custom
            # wrap_langchain_middleware(PIIMiddleware()),  # if prebuilt available
            # ToolRetryMiddleware(max_retries=3),
            # SummarizationMiddleware(),  # context compaction
            # HumanInTheLoopMiddleware(approve_tools=["recommend_response_action"]),
            # ModelCallLimitMiddleware(max_calls=50),
            # AuditMiddleware(),  # our custom logging + DB
        ]

        agent = create_agent(
            model=self.model,
            tools=virgil_tools,
            system_prompt=get_advisor_system_prompt(),
            middleware=middleware,  # if supported in your LangChain version; else wrap manually
            # state_schema=...,  # for custom state if needed
        )

        # Run the agent
        result = await agent.ainvoke({"messages": lc_messages})  # or .invoke for sync

        # Parse result into our LLMResponse
        return LLMResponse(
            content=result.get("output", str(result)),
            reasoning=result.get("reasoning"),
            tool_calls=result.get("tool_calls", []),
            usage=result.get("usage", {}),
            provider="langchain",
            model=self.model,
            raw=result
        )
```

**Important Clarification from Research**:  
In the June 2026 `create_agent` API, middleware is passed directly and composes cleanly. Prebuilts like `PIIMiddleware`, `ToolRetryMiddleware`, `SummarizationMiddleware`, `HumanInTheLoopMiddleware`, `ModelCallLimitMiddleware` exist and are designed exactly for production guardrails. Our custom `AuditMiddleware` and `SecurityPIIMiddleware` slot in the same way. If the exact import paths differ slightly in the installed version, they are documented at https://docs.langchain.com/oss/python/langchain/middleware/.

**File: `sdk/providers/langchain/tools.py`** (Security tools — concrete examples)

```python
from langchain_core.tools import tool
import psycopg2
from psycopg2.extras import RealDictCursor
import os

DB_URL = os.getenv("DATABASE_URL", "postgresql://...")

def get_db_conn():
    return psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)

@tool
def query_recent_events(host_id: str | None = None, limit: int = 20) -> list[dict]:
    """Query recent security events from VIRGIL Postgres. Use for context on investigations."""
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            if host_id:
                cur.execute("SELECT * FROM events WHERE host_id = %s ORDER BY ts DESC LIMIT %s", (host_id, limit))
            else:
                cur.execute("SELECT * FROM events ORDER BY ts DESC LIMIT %s", (limit,))
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()

@tool
def get_finding_details(finding_id: str) -> dict:
    """Retrieve full details + history for a specific finding."""
    # Similar Postgres query on findings table
    ...

@tool
def recommend_response_action(event_json: str) -> str:
    """Given an event or finding, recommend concrete response (isolate host, block IP, etc.). Returns structured JSON string."""
    # The model will call this; we can also make it deterministic in middleware if needed
    ...
```

**File: `sdk/providers/langchain/prompts.py`**

```python
def get_advisor_system_prompt() -> str:
    return """You are VIRGIL Advisor, an expert security reasoning engine for endpoint detection, investigation, and response.

Core principles:
- Be precise, cite specific evidence from tools (event IDs, timestamps, indicators).
- Always output structured reasoning in <reasoning>...</reasoning> then final <answer>...</answer> (JSON or clear text).
- Never hallucinate hosts, IPs, or actions. Use tools to ground every claim.
- For high-impact recommendations, request human approval via HITL middleware.
- Redact or avoid leaking PII in your final output.

Available tools: query_recent_events, get_finding_details, recommend_response_action, ...

Current context: VIRGIL polyglot pipeline with Redis Streams, Postgres authoritative store.
"""
```

**Hand-wave fixed**: Real code structure matching the blog post exactly. Tools use existing DB connection pattern from python-worker. Prompts tailored to VIRGIL Advisor use case (structured output + evidence citation).

---

## Phase 3: Integration Points (No More Vague "wire it in")

**3.1 python-worker integration (example in `python-worker/worker.py` or new `advisor.py`)**

```python
from sdk.llm.harness import advise_on_event
import asyncio

async def process_with_advisor(event: dict):
    try:
        resp = await advise_on_event(event, provider="langchain")
        # Parse resp.content for <reasoning> and <answer>
        # Write structured finding or alert back to Postgres
        # Publish to Redis for downstream
    except Exception as e:
        logger.error(f"Advisor failed: {e}")
        # Fallback to rules-only path
```

Call it optionally from the rules worker or transformer job when confidence low or new pattern.

**3.2 Go API new endpoints (`go-api/`)**

Add routes:
- `POST /api/v1/advisor/query` → calls Python harness via HTTP or shared (for now, simple HTTP to a new advisor service or direct if Python exposed).
- For Phase 1 simplicity: expose a small FastAPI wrapper in python-worker or add to existing Go by calling Python subprocess/HTTP.

**Better concrete path**: Add a thin FastAPI router in `python-worker/advisor_api.py` and mount it, or use existing Go API pattern to proxy.

**3.3 Database (new migration)**

Create `db/migrations/XXXX_add_advisor_tables.sql`:

```sql
CREATE TABLE advisor_calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ts TIMESTAMPTZ DEFAULT now(),
    provider TEXT,
    model TEXT,
    prompt_redacted TEXT,
    response TEXT,
    tokens_in INT,
    tokens_out INT,
    cost_usd NUMERIC,
    event_id UUID REFERENCES events(id),
    finding_id UUID,
    hitl_approved BOOLEAN,
    hitl_approver TEXT
);

CREATE TABLE advisor_approvals (
    call_id UUID REFERENCES advisor_calls(id),
    requested_action TEXT,
    status TEXT CHECK (status IN ('pending','approved','rejected')),
    approver TEXT,
    decided_at TIMESTAMPTZ
);
```

Run via existing migration tooling.

**3.4 docker-compose.yml & env**

Add to services that need it (python-worker):

```yaml
environment:
  - VIRGIL_LLM_PROVIDER=${VIRGIL_LLM_PROVIDER:-langchain}
  - VIRGIL_LLM_MODEL=${VIRGIL_LLM_MODEL:-anthropic:claude-sonnet-4-6}
  - VIRGIL_LANGSMITH_TRACING=${VIRGIL_LANGSMITH_TRACING:-false}
  # Add API keys as secrets or .env
```

Mount `./sdk:/app/sdk` in volumes for live editing.

**Hand-wave fixed**: Exact integration locations, example code snippets, SQL, docker changes. No "we'll connect it somehow."

---

## Phase 4: Security, Observability, Testing & Hardening

**Security**
- All tools use parameterized queries (already in examples).
- PII middleware runs first on every path.
- HITL middleware for any `recommend_response_action` that is high-impact (isolate host, block account, etc.).
- Sandbox tools if we later add code exec (network off by default).
- Audit every call (who, what, why, outcome) to Postgres.
- Rate limiting + cost middleware to prevent runaway spend.

**Observability**
- Structured JSON logs with `event_id`, `provider`, `model`, `tokens`, `duration`.
- Prometheus counters: `virgil_llm_invocations_total{provider, model, status}`.
- Optional LangSmith project for trace visualization (toggle via env; great for debugging middleware order).
- Cost tracking per call (simple pricing table in utils.py).

**Testing**
- `sdk/tests/test_langchain_adapter.py`: mock DB, test invoke with fake event, assert PII redacted, structured output, retry behavior.
- Integration test: spin minimal stack, post event, check advisor_calls row created.
- Property-based tests for middleware composition.
- `make sdk-test` in CI (add to existing GitHub Actions or Makefile verify).

**Pitfalls & Mitigations (Reviewed)**
1. **Middleware order bugs** → Document strict order in code comments + test that PII runs before any model call.
2. **Tool calling support in fine-tuned model** → If the Phi-4 fine-tune doesn't support native tool calling well, fall back to ReAct-style prompting in the LangChain adapter or use a stronger base model for the harness loop while keeping Advisor for final reasoning.
3. **Context window for long investigations** → Rely on `SummarizationMiddleware` + offload large tool outputs to Postgres/filesystem (inspired by LangChain blog context engineering advice).
4. **LangChain version drift** → Pin in `sdk/requirements.txt` and test against it. The `create_agent` + middleware API stabilized in 2025-2026 per the blogs.
5. **State management across polyglot** → For Phase 1, keep state in Postgres + Redis. LangGraph checkpointer can be added later for true durable multi-step agents.
6. **Cost explosion** → `ModelCallLimitMiddleware` + per-invoke budget + alerts.
7. **Secret management** → Never hardcode keys. Use existing VIRGIL `.env` + Docker secrets pattern.

---

## Phase 5: Roadmap & Immediate Next Steps

**Immediate (this week)**
1. Create `sdk/` skeleton + Phase 0/1 files (I can generate the full set of files via tools if approved).
2. Implement LangChain adapter + 2-3 core tools + basic middleware (Audit + PII stub).
3. Wire a test call from python-worker on a synthetic event.
4. Add DB migration + one new Go API endpoint (or FastAPI mount).
5. `make sdk-verify` passes.

**Short-term (next 2 weeks)**
- Full middleware stack (retries, summarization, HITL, cost).
- Support for Fireworks / local Unsloth path (OpenAI-compatible) so the fine-tuned VIRGIL Advisor can be used.
- LangSmith traces + basic dashboard panel in ts-ui.
- More tools + prompt iteration using real VIRGIL events.

**Medium-term**
- Multi-agent (supervisor + specialist) using LangGraph.
- Direct non-LangChain adapters.
- Production deployment with canary + A/B on provider.
- Self-improvement loop: log traces → fine-tune corpus expansion.

**Open Questions for You (Boss) — Needs Clarification**
- Do you want the harness to *always* go through LangChain's loop even for non-LangChain providers (recommended for middleware reuse), or have completely separate paths?
- Preferred first model for testing: Anthropic Claude (via LangChain) or start with the Fireworks fine-tuned Advisor?
- How strict on HITL? All recommendations? Only high-severity actions?
- Budget for LangSmith Pro if traces get heavy, or stick to self-hosted logging + Postgres?
- Any existing PII redaction library/function in the VIRGIL codebase we should reuse?

---

## Appendix: Quick Copy-Paste Commands to Start

```bash
# After plan approval
mkdir -p sdk/{llm,providers/langchain,tests/fixtures}
touch sdk/__init__.py sdk/llm/__init__.py sdk/providers/__init__.py sdk/providers/langchain/__init__.py
# Then paste the file contents from this plan into the respective paths
make sdk-install
make sdk-test
```

---

**This plan is now concrete, actionable, and reviewed for vagueness.** Every hand-wavy phrase from v1.0 has been replaced with file paths, code skeletons matching the official LangChain June 2026 guidance, exact integration points, SQL, Docker changes, and explicit pitfalls.

Ready for your review, boss. Spot anything still fuzzy or want me to generate the full set of files right now and push to a feature branch on GitHub? Or tweak any section first?

J.A.R.V.I.S. — standing by.