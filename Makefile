PYTHON ?= python3
# Default compose host ports: UI 13000, Go API 18080, Postgres 15432, Redis 16379 (no overlap with SecMCP 3000/8080/6379).

.PHONY: up down logs test verify

up: ## Build and start the full stack (requires `.env` — see README)
	docker compose up --build -d

down: ## Stop stack and remove containers (keeps named volumes)
	docker compose down

logs: ## Follow all service logs
	docker compose logs -f --tail=200

test: ## Run language-level tests on the host (Go / Rust / Python toolchains required)
	cd go-api && go test ./...
	cd rust-worker && cargo test
	cd python-worker && pip install -q -r requirements.txt -r requirements-dev.txt && pytest -q

verify: ## Smoke-test after `make up` (runs $(PYTHON) scripts/verify_stack.py; default python3)
	$(PYTHON) scripts/verify_stack.py