# Module: Database (X1 storage, task T0.6)

Owner: TBD (track C, D16 open) · Reviewer: TBD · Phase: A · Last updated: 2026-10-17

## What it does (2–3 sentences, plain language)

Stores each scan as one row in a SQLite table `scans`. The full `ScanResult` JSON goes in
`result_json`; a few fields (state, status, verdict, URLs, versions, times) are copied into
columns so they can be read without parsing JSON.

## Inputs and outputs
- Input: `LG_DATABASE_URL` (default `sqlite:///./linkguard.db`).
- Output: an engine with the table created and WAL on, and a session factory.

## How it works (5–10 lines; the steps you would draw on a whiteboard)

1. `ScanRow` is a SQLAlchemy 2 typed model with the 13 columns from task T0.6.
2. `make_engine()` creates the engine and registers a "connect" listener that runs `PRAGMA journal_mode=WAL`.
3. `Base.metadata.create_all()` creates the table if missing (safe to run on every startup).
4. `make_session_factory()` gives short sessions; `expire_on_commit=False` keeps objects readable after commit.
5. `ScanStore` (orchestrator) does one short transaction per operation: create queued, mark running, save done, get.

## Why it is designed this way (the decision and the simpler/harder alternative you rejected)

- SQLite: zero setup for a single-user localhost tool. Rejected: PostgreSQL (cut by D17).
- WAL lets the API read while a background scan writes.
- No migrations tool (D14): in Phase 1, delete the `.db` file if the table changes.
- `check_same_thread=False`: FastAPI's worker threads and the async scan task share the engine; each operation opens its own session.

## How it is tested (test files, acceptance rows it covers)

`backend/tests/unit/test_db.py` (5): exact column set, WAL on, write/read round-trip through a
fresh engine (proves data reached the file), a queued row with empty outcome, `create_all` twice.

## Known limitations

- Database calls are synchronous inside async code (milliseconds on a local file).
- No retention: full input URLs, including signed-URL secrets, stay until the file is deleted (D17).
- SQLite returns times without a timezone; the store treats them as UTC.

## Likely viva questions (and your short answers)

- *Why store the whole result as JSON?* The contract is the source of truth; columns are just for quick reads.
- *What is WAL?* Write-ahead logging: writers append to a log, so readers are not blocked during a write.
- *How would you change the schema?* Phase 1: delete the local file. Later: add a migrations tool.
