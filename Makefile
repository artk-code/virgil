PYTHON ?= python3
# Default compose host ports: UI 3000, Go API 8080, Postgres 5432, Redis 6379.

.PHONY: bootstrap doctor up down logs test verify sdk-install sdk-lint sdk-test sdk-verify

bootstrap: ## Prepare local env and check prerequisites
	./scripts/bootstrap.sh

doctor: ## Print local toolchain + docker compose versions
	@echo "Tooling check:"
	@printf "  go:      " && (command -v go >/dev/null 2>&1 && go version || echo "missing")
	@printf "  cargo:   " && (command -v cargo >/dev/null 2>&1 && cargo --version || echo "missing")
	@printf "  rustc:   " && (command -v rustc >/dev/null 2>&1 && rustc --version || echo "missing")
	@printf "  $(PYTHON): " && (command -v $(PYTHON) >/dev/null 2>&1 && $(PYTHON) --version || echo "missing")
	@printf "  docker:  " && (command -v docker >/dev/null 2>&1 && docker --version || echo "missing")
	@printf "  compose: " && (command -v docker >/dev/null 2>&1 && docker compose version || echo "missing")

up: ## Build and start the full stack (requires `.env` — see README)
	docker compose up --build -d

down: ## Stop stack and remove containers (keeps named volumes)
	docker compose down

logs: ## Follow all service logs
	docker compose logs -f --tail=200

test: ## Run host tests; skip missing toolchains with a notice
	@if command -v go >/dev/null 2>&1; then \
		echo "Running Go tests..."; \
		cd go-api && go test ./...; \
	else \
		echo "Skipping Go tests (go not found)."; \
	fi
	@if command -v cargo >/dev/null 2>&1; then \
		echo "Running Rust tests..."; \
		cd rust-worker && cargo test; \
	else \
		echo "Skipping Rust tests (cargo not found)."; \
	fi
	@if command -v $(PYTHON) >/dev/null 2>&1; then \
		echo "Running Python tests..."; \
		cd python-worker && $(PYTHON) -m pip install -q -r requirements.txt -r requirements-dev.txt && $(PYTHON) -m pytest -q; \
	else \
		echo "Skipping Python tests ($(PYTHON) not found)."; \
	fi

verify: ## Smoke-test after `make up` (runs $(PYTHON) scripts/verify_stack.py; default python3)
	$(PYTHON) scripts/verify_stack.py

# === SDK / LLM Harness targets (gbuild only - Grok Build) ===
sdk-install: ## Install SDK deps into python-worker env
	docker compose exec python-worker $(PYTHON) -m pip install -q -r /app/sdk/requirements.txt || pip install -r sdk/requirements.txt

sdk-lint: ## Lint SDK code
	docker compose exec python-worker ruff check /app/sdk/ --fix || ruff check sdk/ --fix

sdk-test: ## Run SDK harness tests (prevents regressions on VIRGIL pipeline)
	docker compose exec python-worker $(PYTHON) -m pytest /app/sdk/tests/ -v --tb=short || $(PYTHON) -m pytest sdk/tests/ -v --tb=short

sdk-verify: sdk-install sdk-lint sdk-test
	@echo "SDK harness verified on gbuild"