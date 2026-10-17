# LinkGuard developer commands (see CLAUDE.md "Commands").
# Targets not built yet exit with an error that names the task that will build them,
# so a stub can never look like a passing step.

.PHONY: setup dev test test-backend test-web test-ssrf test-e2e samples openapi \
	lint lint-backend lint-web

setup:  ## Install backend (uv, from uv.lock) and web (npm, from package-lock.json) dependencies
	cd backend && uv sync --locked
	cd web && npm ci

test: test-backend test-web  ## Backend pytest (network sockets blocked) + web vitest

test-backend:
	cd backend && uv run pytest

test-web:
	cd web && npm test

lint: lint-backend lint-web  ## ruff + mypy (backend), eslint + tsc (web)

lint-backend:
	cd backend && uv run ruff check && uv run ruff format --check && uv run mypy

lint-web:
	cd web && npm run lint && npm run typecheck

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
