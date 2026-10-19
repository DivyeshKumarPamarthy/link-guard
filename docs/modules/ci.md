# Module: Continuous integration (M7, task T0.8)

Owner: Divyesh (track C, D16) · Reviewer: TBD · Phase: A · Last updated: 2026-10-19

## What it does (2–3 sentences, plain language)

GitHub Actions runs four jobs on every push to `main` and every pull request: backend lint and
tests, web lint, typecheck and tests, a contract check, and secret scanning. A pull request
should only be merged when all four are green.

## Inputs and outputs
- Input: `.github/workflows/ci.yml`, the Makefile targets, the lock files.
- Output: pass/fail per job on GitHub.

## How it works (5–10 lines; the steps you would draw on a whiteboard)

1. **backend**: `uv sync --locked` → `make lint-backend` (ruff check, ruff format --check, mypy strict) → `make test-backend`.
2. Tests cannot use the network: pytest-socket (`--disable-socket --allow-unix-socket`) is in the
   pytest config, so this holds locally too. Unix sockets stay allowed because asyncio uses a socketpair.
3. **web**: `npm ci` → `make lint-web` (eslint, tsc) → `make test-web` (vitest).
4. **contract**: `make setup` → `make openapi` → fail if `openapi.json` or `types.ts` changed.
5. **secrets**: gitleaks over the whole git history (no licence needed on a personal account).
6. CI calls the same `make` targets developers run, so "works on my machine" and CI agree.

## Why it is designed this way (the decision and the simpler/harder alternative you rejected)

- Jobs in parallel give separate red/green signals per area.
- Network blocked in the test config, not only in CI, so a test that touches the internet fails on a laptop first.
- Rejected: pre-commit hooks only (easy to skip) or a paid secret scanner.

## How it is tested (test files, acceptance rows it covers)

- `actionlint` on the workflow: no findings.
- Every job's commands pass locally (`make lint`, `make test`, `make openapi` twice → byte-identical files).
- `backend/tests/unit/test_no_network.py` proves sockets are blocked.
- **Green on GitHub** for PR #1 (all 4 jobs): https://github.com/DivyeshKumarPamarthy/link-guard/actions/runs/39012343803. The first run failed because `astral-sh/setup-uv` has no
  `v10` tag; it is now pinned to `v10.3.0`.

## Known limitations

- If the repo moves to a GitHub organisation, gitleaks-action needs a free licence key (`GITLEAKS_LICENSE` secret).
- `ubuntu-latest` moves to Ubuntu 26 from 2026-10-19; if a job breaks then, pin `ubuntu-24.04`.
- No branch protection yet; set "require status checks" on `main` in the GitHub settings.

## Likely viva questions (and your short answers)

- *How do you know tests don't use the internet?* pytest-socket blocks sockets; a test proves it.
- *What does the contract job catch?* A model change without regenerated OpenAPI/web types.
- *What is secret scanning?* Searching commits for keys and tokens, so a leaked secret is caught before or right after it is pushed.
