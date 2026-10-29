# Module: Orchestrator and in-process executor (X1, task T2.4)

Owner: Divyesh (track B, D16) · Reviewer: team · Phase: B · Last updated: 2026-10-29

## What it does (2–3 sentences, plain language)

Manages the lifecycle of every scan (`queued` → `running` → `done`), caps how many scans can
run or wait at once, runs the engine pipeline (`Router` → `Fetcher` → `Detectors`) inside an
in-process executor, validates the raw findings, runs the pure scorer (`score_scan`), and saves
the final `ScanResult` to SQLite.

## Inputs and outputs
- Input: a trimmed URL string from `POST /api/scans`, `Settings`, `Registry`, and an `Executor`.
- Output: a persisted `ScanResult` (or `ServerBusyError` → HTTP 503 `SERVER_BUSY` with `Retry-After` when more than `LG_MAX_WAITING_SCANS` are already waiting).
- Code: `backend/app/orchestrator/scans.py`, `backend/app/orchestrator/executor.py`.

## How it works (5–10 lines; the steps you would draw on a whiteboard)

1. `Orchestrator.submit(url)` checks `waiting_count >= LG_MAX_WAITING_SCANS` (20); if full, it raises `ServerBusyError` (HTTP 503 `SERVER_BUSY`, `Retry-After: 5`) before touching the database.
2. Otherwise it writes a `queued` row to SQLite and schedules `Orchestrator._run()` as an `asyncio` background task.
3. `_run()` waits on `asyncio.Semaphore(LG_MAX_CONCURRENT_SCANS)` (4), then marks the row `running`.
4. Under an overall deadline (`LG_TOTAL_DEADLINE_S` + grace), it calls `executor.run(url)`.
5. `InProcessExecutor` runs `clean_url` → `classify` → `fetch` → `detect_type` + `refine_zip_subtype` → `run_mismatch_checks`, returning a JSON-serializable `RawScanReport` (`findings`, `ReadFactsRecord`, `FileInfo`, `redirects`, `timings_ms`).
6.Per decision D59 and spec §8, `FETCH_INTERRUPTED` is dropped only when the partial bytes already identify a file type (`detect_type(...).type != "unknown"`), so the scan can be evaluated as a partial scan (`SCAN_PARTIAL`, `NO_ISSUES_IN_CHECKED_PART` at best).
7. `Orchestrator._finish()` validates `RawScanReport` before scoring, runs `score_scan()`, logs any unknown codes via `log_unknown_codes()`, validates the merged `ScanResult`, and saves `state=done`.
8. Any exception, timeout or validation failure is caught, logged through `safe()`, and stored as `UNABLE_TO_VERIFY` with `ANALYSIS_ERROR`.

## Why it is designed this way (the decision and the simpler/harder alternative you rejected)

- **Clean JSON seam (`RawScanReport`) between executor and orchestrator:** Phase 2 can replace `InProcessExecutor` with a container worker without changing the API, contract, orchestrator or scorer.
- **Semaphore + waiting cap instead of Redis/Celery or per-IP rate limits (D13, D17):** 4 concurrent scans and 20 waiting is simple to explain in a viva and bounds memory (`4 × 5 MB` cap).
- **Config-only executor swap (`LG_EXECUTOR=inprocess|mock`):** API contract tests can run against `MockExecutor` while production/demo runs `InProcessExecutor`.

## How it is tested (test files, acceptance rows it covers)

- `backend/tests/unit/test_orchestrator.py`: semaphore concurrency cap (peak concurrent scans ≤ limit, excess queued scans stay `queued` until a slot opens), 503 `SERVER_BUSY` when waiting count reaches `LG_MAX_WAITING_SCANS`, overall timeout → `ANALYSIS_ERROR`, exception path with secret URL redaction, malformed raw executor output rejected before scoring, unknown reason code logged and treated as `unable`, `FETCH_INTERRUPTED` drop/keep rule (D59), full-scope ZIP subtype refinement (D75), and config-only swap between `MockExecutor` and `InProcessExecutor`.
- `backend/tests/unit/test_api.py`: 503 `SERVER_BUSY` response body, `Retry-After` header, and CORS header exposure.

## Known limitations

- Scan tasks run in the API process's event loop; if the process is killed mid-scan, `queued`/`running` rows in `linkguard.db` are not resumed on restart.
- No deduplication or caching (D17): submitting the same link twice runs two fresh scans.

## Likely viva questions (and your short answers)

- *How do you stop 100 concurrent requests from exhausting memory?* `asyncio.Semaphore(4)` allows at most 4 scans to fetch bytes at once (`4 × 5 MB = 20 MB` max buffer), and once 20 more are waiting, `POST /api/scans` immediately returns HTTP 503 `SERVER_BUSY`.
- *Why doesn't the executor call the scorer itself?* Keeping scoring in the orchestrator means a future isolated container worker only returns raw findings and cannot forge a `SAFE` verdict.
- *What happens if an unexpected bug crashes a detector?* The orchestrator catches every `Exception`, logs the type and `safe(exc)`, and saves `UNABLE_TO_VERIFY` with `ANALYSIS_ERROR` — never `SAFE` and never a stuck `running` scan.
