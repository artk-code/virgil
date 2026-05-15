# Agent instructions (VIRGIL)

Use this file when extending **VIRGIL** (Vendor-neutral Incident Response Graph
& Intelligence Layer) with an automated coding agent.

## Where business logic lives

| Language | Path | Notes |
|----------|------|--------|
| Go | `go-api/` | Add handlers and packages alongside `main.go`; keep Docker build with `go mod download` before full `COPY`. |
| Python | `python-worker/worker.py` | Sidecar/cron-style worker; add modules under `python-worker/` and import from `worker.py`. |
| Rust | `rust-worker/src/main.rs` | Async Tokio entrypoint; binary name follows `Cargo.toml` package name. |
| Front door | `ts-ui/` | Static assets + `nginx.conf` for `/api` → Go upstream. |

## Environment variables

- **Postgres:** `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` (compose + `.env`).  
- **Apps:** `DATABASE_URL` (must match Postgres credentials). `REDIS_URL` for Redis clients.  
- All services load `.env` via Compose `env_file` where configured; see `docker-compose.yml`.

## Tests (host)

From repo root:

```bash
make doctor
make test
```

Python tests live in `python-worker/tests/`; `pytest.ini` sets `testpaths` and `pythonpath`.

`make test` now degrades gracefully when a host toolchain is missing (prints `Skipping ...`), so agents should still run it by default and report skipped stacks explicitly.

## Smoke test after `docker compose up`

```bash
make verify
```

`Makefile` sets `PYTHON ?= python3` for the `verify` target. On Windows, if `python3` is not on your PATH, run the script directly (recommended):

```bash
py -3 scripts/verify_stack.py
```

If your `py` launcher already defaults to Python 3, `make verify PYTHON=py` may work; otherwise use the command above.

The script checks `http://localhost:18080/health` and `http://localhost:13000/api/health` and expects Redis and Postgres status `ok` in the JSON body.

## Operational hints

- Do **not** commit `.env`.  
- After renaming Compose services, update `ts-ui/nginx.conf` `proxy_pass`.  
- Prefer `docker compose logs <service>` when debugging healthcheck failures.
- Use `python3 scripts/replay_dlq.py` for safe DLQ requeue workflows (dry-run by default).

## Current baseline snapshot (May 2026)

- Phase 0 branding is moving this repository from the original `fsecai` starter
  toward **VIRGIL**. Avoid broad runtime renames unless that is the explicit task.
- Compose stack boots healthy with `make up` and passes smoke checks with `make verify`.
- Host tests exist for Go (`go-api/main_test.go`), Python (`python-worker/tests/`), and Rust (`rust-worker/src/main.rs`).
- Bootstrap and environment prep are centralized in `make bootstrap` and `scripts/bootstrap.sh`.
- The active execution checklist for next milestones lives in `docs/next-build-plan.md`.
- Worker observability now emits structured JSON lifecycle logs and periodic metrics counters; avoid adding raw payload logging that could leak sensitive command content.
- API query contracts, DLQ replay tooling, and the first dashboard slice are implemented and validated.

## Next-build execution guidance for agents

When asked to "continue building" without strict scope, prioritize in this order:

1. **Transformer safety (`ART-14`) first**  
   Harden checkpoint resume and idempotency behavior in `python-worker/transform_job.py`.
2. **CI baseline (`ART-15`) second**  
   Add workflow gates for `make doctor`, `make test`, and compose smoke verification.
3. **Then remaining product increments**  
   Any additional UI or API expansion should follow after backend correctness + CI gates are in place.

## Linear workflow for agents

- Use the Linear project `fsecai` for milestone tracking until it is renamed to
  VIRGIL.
- Before starting implementation, set the issue to `In Progress` and post a short plan comment.
- After implementation, post a completion comment with:
  - what changed
  - validation commands/results
  - any operator notes
- Only move issue to `Done` after runtime verification passes (`make test`, `make verify`, and relevant endpoint/UI smoke checks).
- Keep `docs/next-build-plan.md` in sync with Linear state when milestones are completed.

Suggested "first command" sequence for new agent sessions:

```bash
make doctor
make test
docker compose up --build -d
make verify
```
