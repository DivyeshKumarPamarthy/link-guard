# LinkGuard developer commands (see CLAUDE.md "Commands").
# Targets not built yet exit with an error that names the task that will build them,
# so a stub can never look like a passing step.

.PHONY: setup dev demo-server test test-backend test-web test-demo test-ssrf test-e2e samples \
	openapi check-openapi lint lint-backend lint-web lint-demo test-loop

setup:  ## Install backend + demo (uv, from uv.lock) and web (npm, from package-lock.json)
	cd backend && uv sync --locked
	cd demo && uv sync --locked
	cd web && npm ci

test: test-backend test-web test-demo test-loop  ## Backend pytest (sockets blocked), web vitest, demo pytest, loop unit tests

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

# Regenerate both contract files into a temp folder and diff them against the working tree.
# Writes nothing in the repo, so it is safe as a verify step.
check-openapi:  ## Fail if backend/openapi.json or web/src/api/types.ts are out of date
	@test -f backend/scripts/export_openapi.py || { echo "check-openapi: no OpenAPI export yet. Run T0.4 first (make openapi)."; exit 1; }
	@tmp=$$(mktemp -d); \
	status=0; \
	(cd backend && uv run python -m scripts.export_openapi --output "$$tmp/openapi.json") && \
	(cd web && npx openapi-typescript "$$tmp/openapi.json" -o "$$tmp/types.ts" > /dev/null) && \
	diff -u backend/openapi.json "$$tmp/openapi.json" && \
	diff -u web/src/api/types.ts "$$tmp/types.ts" || status=1; \
	rm -r "$$tmp"; \
	if [ $$status -ne 0 ]; then echo "check-openapi: contract files are out of date. Run 'make openapi' and commit."; exit 1; fi; \
	echo "check-openapi: openapi.json and types.ts are up to date"

test-loop:  ## Unit tests for the automation loop (scripts/loop.py), standard library only
	uv run --no-project --python 3.12 python -m unittest discover -s scripts/tests -t . -v

dev:  ## docker compose: api :8000, web :5173, demo :8081/:8443/:8444, all on 127.0.0.1 only
	docker compose up --build

test-ssrf:  ## SSRF table only (fake resolver, socket guard; no network)
	cd backend && uv run pytest tests/ssrf -q

test-e2e:
	@echo "make test-e2e: not implemented yet (acceptance matrix arrives in T3.3)"; exit 1

samples:  ## Regenerate the harmless sample files into samples/ (same bytes every run)
	cd demo && uv run python make_samples.py
