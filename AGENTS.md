# Agent instructions (polyglot-stack-template)

Use this file when extending the template with an automated coding agent.

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
cd go-api && go test ./...
cd ../rust-worker && cargo test
cd ../python-worker && pip install -r requirements.txt -r requirements-dev.txt && pytest -q
```

Python tests live in `python-worker/tests/`; `pytest.ini` sets `testpaths` and `pythonpath`.

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
