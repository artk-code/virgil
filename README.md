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

## Quick start

```bash
cp .env.example .env
# Edit POSTGRES_PASSWORD and DATABASE_URL so credentials match.
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
| **python-worker** | Rules/model analysis consumer for `security_events`; writes `security_analysis`/`security_alerts` and DLQ. |
| **python-transformer** | Scheduled ETL job that moves Redis stream data to Postgres with checkpoints. |
| **rust-worker** | Async simulator that publishes normalized security events to Redis streams. |
| **ts-ui** | nginx serves static files and **proxies `/api/*` to `go-api:8080`** (see `ts-ui/nginx.conf`). Replace `index.html` or drop in a built SPA under the same nginx config. |

## nginx `/api` proxy pattern

The browser loads `http://localhost:13000`. Requests to `http://localhost:13000/api/health` are proxied to `http://go-api:8080/health` inside the Docker network. Rename the Compose service **and** the `proxy_pass` upstream in `ts-ui/nginx.conf` if you change `go-api`.

## Security pipeline docs (Phase 1)

- Event contract and stream topology: `docs/security-event-contract.md`
- Rust role split (host sensor vs simulator): `docs/rust-agent-deployment.md`
- API + SQL model summary: `docs/api-data-model.md`

## API endpoints (Phase 1)

- `GET /health`
- `GET /ready`
- `POST /api/v1/agents/checkin`
- `GET /api/v1/agents/{agent_id}/status`
- `GET /api/v1/alerts/recent`
- `GET /api/v1/events/search`

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
| `make up` / `make down` | Start or stop the stack. |
| `make logs` | Tail service logs. |
| `make test` | Run Go, Rust, and Python tests on the **host** (requires toolchains). |
| `make verify` | HTTP smoke test (uses `PYTHON`, default `python3`). |

## License

Set the license policy that fits your organization before distributing.
