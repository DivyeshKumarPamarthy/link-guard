# LinkGuard developer commands (see CLAUDE.md "Commands").
# Targets not built yet exit with an error that names the task that will build them,
# so a stub can never look like a passing step.

.PHONY: setup dev demo-server test test-backend test-web test-demo test-ssrf test-e2e samples \
	openapi lint lint-backend lint-web lint-demo

setup:  ## Install backend + demo (uv, from uv.lock) and web (npm, from package-lock.json)
	cd backend && uv sync --locked
	cd demo && uv sync --locked
	cd web && npm ci

test: test-backend test-web test-demo  ## Backend pytest (sockets blocked), web vitest, demo pytest

test-backend:
	cd backend && uv run pytest

test-web:
	cd web && npm test

test-demo:  ## Demo server smoke tests (loopback only)
	cd demo && uv run pytest

lint: lint-backend lint-web lint-demo  ## ruff + mypy (backend, demo), eslint + tsc (web)

lint-backend:
	cd backend && uv run ruff check && uv run ruff format --check && uv run mypy

lint-web:
	cd web && npm run lint && npm run typecheck

lint-demo:
	cd demo && uv run ruff check && uv run ruff format --check && uv run mypy

demo-server:  ## Run the demo server: HTTP :8081, HTTPS :8443, wrong-cert HTTPS :8444
	cd demo && uv run python -m demo_server

openapi:  ## Export backend/openapi.json, then regenerate web/src/api/types.ts from it
	cd backend && uv run python -m scripts.export_openapi
	cd web && npm run openapi

dev:
	@echo "make dev: not implemented yet (docker-compose arrives in T2.5)"; exit 1

test-ssrf:
	@echo "make test-ssrf: not implemented yet (SSRF table arrives in T1.2)"; exit 1

test-e2e:
	@echo "make test-e2e: not implemented yet (acceptance matrix arrives in T3.3)"; exit 1

samples:
	@echo "make samples: not implemented yet (samples generator arrives in T2.6)"; exit 1
