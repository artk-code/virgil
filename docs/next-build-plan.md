# Next Build Plan

**Note (gbuild - Grok Build):** All new LLM Harness & Advisor work is happening exclusively on the `gbuild` branch. Core SDK structure + LangChain provider already implemented and pushed. Updates below reflect progress on gbuild only. Main branch untouched.

## LLM Harness & Multi-Vendor Advisor Integration (gbuild only)

- [x] Core `sdk/llm/` (types, config, middleware, harness, utils) + `sdk/providers/langchain/` (adapter, tools, prompts) pushed to gbuild.
- [x] `sdk/requirements.txt` and basic structure added.
- [ ] Update Makefile, docker-compose.yml, python-worker/requirements.txt on gbuild (in progress).
- [ ] Add `db/migrations/` for advisor_calls / approvals tables.
- [ ] Build `sdk/tests/` with pytest (use team experts for regression prevention vs VIRGIL pipeline).
- [ ] Wire advisor calls optionally in python-worker/transform_job.py or worker.py.
- [ ] Add Go API endpoint or FastAPI mount for /api/v1/advisor/query.
- [ ] Update docs/ plan + this file as changes land on gbuild.
- [ ] Full middleware stack (PII, retry, summarization, HITL, cost) + LangSmith toggle.
- [ ] Support for Fireworks/local fine-tuned VIRGIL Advisor path.

**Done when (gbuild)**

- [ ] `make sdk-verify` passes cleanly on gbuild.
- [ ] Harness can be called from python-worker without breaking existing event flow.
- [ ] Docs (this file + VIRGIL_LLM_Harness_Build_Plan.md) stay in sync with every push.

## Existing Milestones (unchanged, continue on gbuild where relevant)

## Milestone 1: API hardening and query controls

- [ ] Add stricter query validation for `GET /api/v1/alerts/recent` and `GET /api/v1/events/search`.
- [ ] Add pagination strategy (cursor or stable offset contract) and document response shape.
- [ ] Add negative-path tests for invalid filters, limits, and route patterns.
- [ ] Confirm API contract examples in `docs/api-data-model.md`.

**Done when**

- [ ] API endpoints reject malformed input consistently with clear JSON errors.
- [ ] Go tests cover happy path + validation path for query endpoints.

## Milestone 2: worker reliability and observability

- [x] Add structured log fields (event_id, stream_id, host_id, retry_count, outcome) in `python-worker/worker.py`.
- [x] Add dead-letter replay script for `security_dlq` events under `scripts/`.
- [x] Add metrics counters/log summaries for processed, retried, dropped, and DLQ events.
- [ ] Add tests for dedupe + retry behavior around transient failures.

**Done when**

- [x] Operators can trace a single event through worker processing from logs.
- [x] Replay flow exists for DLQ events without manual Redis command crafting.

## Next Linear execution sequence

After ART-12 completion, recommended order is:

1. `ART-14` (transformer checkpoint/idempotency hardening)
2. `ART-15` (CI doctor/test/compose verify gates)
3. `ART-13` (first dashboard slice after backend/CI stabilization)

## Milestone 3: transformer safety and idempotency

- [ ] Add tests for checkpoint resume in `python-worker/transform_job.py`.
- [ ] Add behavior tests for partial batch failures and retry safety.
- [ ] Validate no duplicate inserts for the same event/analysis payload.
- [ ] Document ETL operational expectations and recovery notes.

**Done when**

- [ ] Transformer can stop/restart without event loss or duplicate writes.
- [ ] ETL checkpoints are validated in tests for both streams.

## Milestone 4: UI first dashboard slice

- [x] Replace static `ts-ui/index.html` placeholder with a small SPA shell.
- [x] Add health panel using `/api/health`.
- [x] Add recent alerts panel using `/api/v1/alerts/recent`.
- [x] Add basic event search form using `/api/v1/events/search`.

**Done when**

- [x] UI renders health + alerts + search results from live API.
- [x] Browser traffic uses same-origin `/api/*` through nginx proxy.

## Milestone 5: CI baseline and release gate

- [ ] Add CI workflow to run `make doctor`.
- [ ] Add CI workflow to run `make test`.
- [ ] Add compose smoke gate (`docker compose up --build -d` + `make verify`).
- [ ] Publish test and smoke status in PR checks.

**Done when**

- [ ] New PRs fail fast on broken tests or unhealthy stack startup.
- [ ] A green pipeline implies the repo is in a runnable baseline state.

## Suggested execution order

1. Milestone 1 (API contract stability)
2. Milestone 2 and 3 (pipeline correctness and safety)
3. Milestone 4 (UI integration)
4. Milestone 5 (automation gate)

## Agent kickoff checklist

Run this at the start of each new implementation session:

```bash
make doctor
make test
docker compose up --build -d
make verify
```

**gbuild-specific kickoff (add this when working on LLM harness):**
```bash
make sdk-verify
```
