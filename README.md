# fsecai

`fsecai` is a polyglot security-agent platform starter for endpoint and server
monitoring. The Phase 1 implementation provides a practical pipeline:

- Rust producer simulates host telemetry and pushes normalized events to Redis streams.
- Python worker applies heuristics/model scoring and emits analysis + alerts.
- Python transformer periodically persists stream data to Postgres for long-term storage.
- Go API exposes check-in/status and query endpoints over the SQL store.
- nginx serves UI/static content and proxies `/api` to the Go API.

The design intentionally keeps Redis as a transport layer and Postgres as the
authoritative long-term store.

## Current status (May 2026)

Implemented and validated in the current branch:

- API query hardening for alerts/events (`limit`/`offset` validation, severity guardrails, pagination metadata, structured query errors).
- Worker observability upgrades (structured lifecycle logs + periodic metrics counters).
- DLQ replay tooling (`scripts/replay_dlq.py`) with dry-run default and bounded replay controls.
- First dashboard slice in `ts-ui` (health, recent alerts, event search) using same-origin `/api/*` calls.

## Quick start

```bash
cp .env.example .env
# Edit POSTGRES_PASSWORD and DATABASE_URL so credentials match.
make bootstrap
docker compose up --build -d
```

- **UI (nginx + static):** http://localhost:13000  
- **Go API (direct):** http://localhost:18080/health  
- **Postgres (host port → container 5432):** `localhost:15432`  
- **Redis (host port → container 6379):** `localhost:16379`  

Host ports **15432** and **16379** avoid collisions with other stacks (for example a local Redis already bound to 6379).

## Architecture at a glance

1. Rust host/simulator emits events to `security_events`.
2. Python rules engine consumes `security_events`, scores data, emits:
   - `security_analysis`
   - `security_alerts`
   - `security_dlq` on failures
3. Python ETL job moves stream data into Postgres tables:
   - `security_events`
   - `security_findings`
   - `hosts`
   - `agent_heartbeats`
   - `etl_checkpoints`
4. Go API serves operational endpoints and historical query APIs backed by Postgres.

## Running next to SecMCP

Default host bindings are chosen so this template can run alongside SecMCP’s Compose stack (which uses **3000**, **8080**, and **6379** on the host; SecMCP does not expose Postgres).

| Purpose | This template (host) | SecMCP (host) |
|--------|----------------------|---------------|
| Web UI | **13000** | **3000** |
| HTTP API | **18080** | **8080** |
| Postgres | **15432** | — |
| Redis | **16379** | **6379** |

After the stack is healthy:

```bash
make verify
# Windows without `python3` on PATH:
py -3 scripts/verify_stack.py
```

## What each service does

| Service | Role |
|--------|------|
| **postgres** | Relational store; credentials from `.env` / compose interpolation. |
| **redis** | Cache / pub-sub / streams placeholder; workers read `REDIS_URL`. |
| **go-api** | HTTP edge: `/health` and `/ready` ping Redis and Postgres when configured. Extend with routes, auth, and domain logic in `go-api/`. |
| **python-worker** | Rules/model analysis consumer for `security_events`; writes `security_analysis`/`security_alerts` and DLQ. Emits structured lifecycle logs (`event_id`, `stream_id`, `host_id`, `attempt`, `outcome`) and periodic metrics counters. |
| **python-transformer** | Scheduled ETL job that moves Redis stream data to Postgres with checkpoints. |
| **rust-worker** | Async simulator that publishes normalized security events to Redis streams. |
| **ts-ui** | nginx serves static files and **proxies `/api/*` to `go-api:8080`** (see `ts-ui/nginx.conf`). Current dashboard includes health, recent alerts, and event search panels. |

## nginx `/api` proxy pattern

The browser loads `http://localhost:13000`.

- `http://localhost:13000/api/health` is proxied to `http://go-api:8080/health`.
- `http://localhost:13000/api/v1/*` is proxied to `http://go-api:8080/api/v1/*`.

Rename the Compose service **and** the `proxy_pass` upstreams in `ts-ui/nginx.conf` if you change `go-api`.

## Security pipeline docs (Phase 1)

- Event contract and stream topology: `docs/security-event-contract.md`
- Rust role split (host sensor vs simulator): `docs/rust-agent-deployment.md`
- API + SQL model summary: `docs/api-data-model.md`
- Next implementation checklist: `docs/next-build-plan.md`

## DLQ replay utility

Use the DLQ replay tool to safely requeue failed worker messages from `security_dlq`.

Dry-run (default, no writes):

```bash
python3 scripts/replay_dlq.py --limit 50
```

Execute replay writes:

```bash
python3 scripts/replay_dlq.py --execute --limit 50
```

Execute + delete successfully replayed DLQ entries:

```bash
python3 scripts/replay_dlq.py --execute --delete-replayed --limit 50
```

Useful flags:

- `--from-id <stream-id>`: resume from a specific DLQ stream ID.
- `--target-stream <name>`: force destination stream for all replays.
- `--fallback-stream <name>`: destination if DLQ entry source stream is missing/invalid.

By default the tool reads `REDIS_URL`, `SECURITY_DLQ_STREAM`, and `SECURITY_EVENTS_STREAM` from environment.

## API endpoints (Phase 1)

- `GET /health`
- `GET /ready`
- `POST /api/v1/agents/checkin`
- `GET /api/v1/agents/{agent_id}/status`
- `GET /api/v1/alerts/recent?limit=20&offset=0`
- `GET /api/v1/events/search?host_id=&event_type=&severity=&limit=50&offset=0`

Query endpoint notes:

- `alerts/recent`: `limit` must be `1..100`, `offset` must be `0..10000`.
- `events/search`: `limit` must be `1..250`, `offset` must be `0..10000`.
- `events/search` `severity` filter must be one of: `low`, `medium`, `high`, `critical`.
- Both endpoints now return a `pagination` block with `limit`, `offset`, `returned`, and `has_more`.
- Invalid query params return `400` with `{ "error_code": "invalid_query", "message": "...", "details": { ... } }`.

## Renaming services

1. In `docker-compose.yml`, change `container_name` and **service keys** (e.g. `go-api:` → `api:`).  
2. Update **every** reference: `depends_on`, `environment`, and nginx `proxy_pass http://<service>:<port>/`.  
3. Rebuild affected images: `docker compose up --build -d`.

## Secrets and credentials

### Never commit `.env`

- **`.env` is gitignored.** It is the local place for Postgres passwords, `DATABASE_URL`, and any API keys.  
- **`.env.example`** is safe to commit: placeholders only. The default password there is **for local development only**; it is weak by design so you notice and replace it.

### What `.gitignore` is meant to catch

Besides `.env`, the repo ignores common leak paths: TLS private keys, `secrets/`, cloud credential JSON, `.pgpass`, Docker override files that often hold local paths, build artifacts, and editor noise. **Review before every push**; `.gitignore` is not a security product.

### Local development vs GitHub

- **Local:** copy `.env.example` → `.env`, iterate freely.  
- **GitHub / CI:** inject secrets via your CI provider’s secret store or OIDC—**not** by committing `.env`. PR branches should never add real credentials to tracked files.

### Rotating the Postgres password

1. Change `POSTGRES_PASSWORD` in `.env`.  
2. Update `DATABASE_URL` so the password in the URL matches **exactly** (URL-encode special characters if needed).  
3. If Postgres already initialized the data volume with the old password, either rotate inside Postgres (`ALTER USER … PASSWORD`) or **reset the volume** (destructive):  
   `docker compose down -v` then `docker compose up --build -d` (this wipes the named volume—only for dev).

### `DATABASE_URL` must match `.env`

`go-api` uses `DATABASE_URL` for `sql.Open`. `POSTGRES_*` variables configure the **postgres** container. If user/password/db do not align between those settings and `DATABASE_URL`, health checks will show `postgres: error`.

### Production secret management (recommended vendor)

For enterprise production workloads, use a dedicated secret manager with audit, rotation, and fine-grained access—**HashiCorp Vault** is a common choice. This template **does not** integrate Vault; inject runtime secrets via your platform (Kubernetes secrets + external secrets operator, ECS task secrets, etc.) or your CI/CD vault integration instead of flat files in the image.

## Makefile targets

| Target | Purpose |
|--------|---------|
| `make bootstrap` | Ensure `.env` exists and verify local prerequisites (`docker`, `docker compose`, `make`). |
| `make doctor` | Print local toolchain versions and whether `go` / `cargo` / `python3` / Docker are available. |
| `make up` / `make down` | Start or stop the stack. |
| `make logs` | Tail service logs. |
| `make test` | Run Go, Rust, and Python tests on the **host**; missing toolchains are skipped with a notice. |
| `make verify` | HTTP smoke test (uses `PYTHON`, default `python3`). |

## Next build plan (current focus)

Most initial Phase 2 milestones are now complete. Recommended next order:

1. **Transformer safety (`ART-14`)**  
   Add idempotency and checkpoint resume hardening tests in `python-worker/transform_job.py`.
2. **CI baseline (`ART-15`)**  
   Add workflow gates for `make doctor`, `make test`, and compose smoke verification.

Detailed checklist and milestone state live in `docs/next-build-plan.md`.

## License

Set the license policy that fits your organization before distributing.
