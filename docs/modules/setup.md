# Module: Repository setup (M1, task T0.1)

Owner: TBD (track C, D16 open) · Reviewer: TBD · Phase: A · Last updated: 2026-10-17

## What it does (2–3 sentences, plain language)

Creates the empty but working project: the folder layout from `CLAUDE.md`, a Python backend
managed by `uv`, a React + Vite + TypeScript web app, and a `Makefile` so every teammate installs
and tests the project with the same two commands. Nothing scans links yet; later tasks fill in the
empty packages.

## Inputs and outputs
- Input: a fresh clone of the repo plus uv, Node and make.
- Output: `make setup` installs exact dependency versions from the lock files; `make test` runs
  backend pytest and web vitest.

## How it works (5–10 lines; the steps you would draw on a whiteboard)

1. `make setup` → `cd backend && uv sync --locked` reads `uv.lock` and builds `backend/.venv`
   with Python 3.12 (from `.python-version`). `--locked` fails if the lock file is out of date
   instead of silently changing versions.
2. `make setup` → `cd web && npm ci` installs exactly what `package-lock.json` lists.
3. `make test` → `uv run pytest` (backend), then `npm test` = `vitest run` (web).
4. `backend/app/` holds one package per responsibility (api, contract, core, orchestrator,
   engine/{router,fetcher,detect,scoring}, registry, db); each `__init__.py` docstring says what
   belongs there.
5. `make lint`, `make openapi` and the split targets (`test-backend`, `test-web`, `lint-backend`,
   `lint-web`, used by CI) are real since T0.4/T0.8. Unbuilt targets (`dev`, `test-ssrf`,
   `test-e2e`, `samples`) print the task that will build them and exit 1.

## Why it is designed this way (the decision and the simpler/harder alternative you rejected)

- **Lock files + `--locked` / `npm ci`**: every teammate and CI get identical versions. Rejected:
  `pip install -r requirements.txt` with loose versions (works today, breaks next month).
- **`package = false` in `pyproject.toml`**: the backend is an app we run, not a library we
  publish, so uv only manages the environment. Rejected: building a wheel we would never use.
- **Stub targets fail loudly**: a stub that printed "ok" would make `make lint` look green when no
  linting happened. That would break the "never invent results" rule.
- **Template boilerplate removed** (Vite logos, counter demo, oxlint): less code nobody can explain
  in a viva. ESLint replaced oxlint in T0.8, as `CLAUDE.md` specifies; TypeScript is 5.9, not the
  template's 6, because openapi-typescript needs it (D28).
- **jsdom 29, not the newest 30**: jsdom 30 needs Node 24.15+, and at least one dev machine runs
  Node 24.8. jsdom 29 supports Node 22.13+ and 24.0+.
- **pytest `--import-mode=importlib`**: test files in different folders (unit/, e2e/…) can share a
  name without needing `__init__.py` in every test folder.

## How it is tested (test files, acceptance rows it covers)

- `backend/tests/unit/test_skeleton.py`: every package imports and has a docstring (12 cases).
- `web/src/App.test.tsx`: the app renders its title, which proves React + Vitest + Testing Library work.
- Acceptance "`make setup` succeeds on a clean clone": checked by copying only git-tracked files
  to an empty folder and running `make setup` then `make test` (both exit 0).

## Known limitations

- `make dev`, `samples`, `test-ssrf`, `test-e2e` are stubs until their tasks.
- No docker-compose yet (T2.5).
- Verified on macOS (Apple Silicon) only so far.

## Likely viva questions (and your short answers)

- *Why uv instead of pip?* One tool for the Python version, the virtualenv and a lock file, and it's fast.
  `uv sync --locked` gives everyone identical dependencies.
- *What is the difference between `npm install` and `npm ci`?* `npm ci` installs exactly the lock
  file and fails if `package.json` and the lock disagree; `npm install` may update the lock.
- *Why are stubs made to fail?* So a missing step can never look like a passing one.
- *Why is `.env` ignored but `.env.example` committed?* Secrets stay out of git; the example
  documents every variable with its safe default.
- *Why is `samples/` gitignored?* Samples include generated executables; we regenerate them with a
  script instead of committing binaries.
- *Why does `.gitattributes` mark fixtures binary?* So git never converts line endings in them,
  which would corrupt file signatures the detector depends on.
