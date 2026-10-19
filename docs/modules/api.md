# Module: API and mock scanner (M1 + X1, task T0.7)

Owner: Divyesh (track B, D16) · Reviewer: TBD · Phase: A · Last updated: 2026-10-19

## What it does (2–3 sentences, plain language)

`POST /api/scans` checks the submitted text, stores a queued scan and returns `202` with a
`scan_id` straight away; the scan runs in the background. `GET /api/scans/{scan_id}` returns the
current `ScanResult`. For now a `MockExecutor` always answers UNSAFE after 300 ms, so the web app
can be built against the real API before the engine exists.

## Inputs and outputs
- Input: JSON `{"url": "..."}` (max 8 KB body).
- Output: `202 ScanAccepted`, `200 ScanResult`, or an `ErrorBody` with 400/404/405/413/500.

## How it works (5–10 lines; the steps you would draw on a whiteboard)

1. `BodySizeLimit` (ASGI middleware) refuses a declared Content-Length over 8 KB, and counts
   bytes of chunked bodies as they arrive, raising 413 if the total goes over.
2. FastAPI parses JSON into `ScanRequest`; malformed JSON or a non-string `url` → 400 `INVALID_REQUEST`.
3. `check_submission()`: trim; empty → `URL_EMPTY`; over `LG_MAX_URL_LENGTH` → `URL_TOO_LONG`;
   two or more link-like tokens → `URL_MULTIPLE`. No scan is created on any of these.
4. `Orchestrator.submit()` writes a `queued` row and starts an asyncio task; the API replies 202.
5. The task marks the row `running`, awaits `executor.run(url)` (plain JSON data back), merges the
   result into the scan and validates it against the contract, then stores `done`.
6. If the executor raises or returns a dishonest result, the scan becomes UNABLE_TO_VERIFY with `ANALYSIS_ERROR`.
7. Error handlers turn every exception into an ErrorBody; CORS `*` without credentials is the outermost layer.
8. `python -m app` runs uvicorn on `LG_BIND_HOST` (127.0.0.1) and `LG_API_PORT` (8000).

## Why it is designed this way (the decision and the simpler/harder alternative you rejected)

- Async contract from day one (D3): the extension and slow scans need polling anyway.
- The executor returns plain JSON-compatible data, so Phase 2 can swap in a container runner without touching the API.
- `create_app()` builds everything, so tests use their own settings and a temporary database.
- Rejected: returning the verdict from POST directly; it would block for up to 20 s and change the contract later.

## How it is tested (test files, acceptance rows it covers)

`backend/tests/unit/test_api.py` (34): 202 → poll → done; not done before the mock delay; no
dedupe; unknown fields ignored; every 400 code including boundaries (exactly 2048 chars accepted,
2049 refused, length measured after trimming); malformed bodies; 404 for unknown and malformed
ids; 405 for the missing list endpoint; 413 declared and chunked; executor crash → ANALYSIS_ERROR
without leaking details; dishonest executor output refused; 500 without stack trace; CORS
preflight and CORS on errors; default bind 127.0.0.1:8000. Also checked by hand: `python -m app`
listens on 127.0.0.1 only and a real POST → GET returns the mock verdict.

## Known limitations

- Mock only; no semaphore, busy guard (503), overall timeout or scorer yet (T2.4).
- SQLite calls block the event loop briefly.
- `/docs` (Swagger UI) loads from a CDN, so it needs internet.

## Likely viva questions (and your short answers)

- *Why 202 and polling instead of waiting?* Scans can take up to 20 s; polling keeps requests short and works for the extension.
- *How do you stop a huge request?* The 8 KB body limit, checked on the declared length and on the bytes actually received.
- *What happens if the scanner crashes?* The scan is stored as "Unable to verify" with `ANALYSIS_ERROR`, never Safe, and no details leak.
