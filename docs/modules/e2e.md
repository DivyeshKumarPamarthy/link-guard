# Module: Acceptance matrix end-to-end tests and log safety (M7, tasks T3.3, T3.5)

Owner: Divyesh ( tracks A & C, D16) · Reviewer: team · Phase: B · Last updated: 2026-10-29

## What it does (2–3 sentences, plain language)

Runs the complete LinkGuard backend (API, orchestrator, in-process executor, router, SSRF-safe
fetcher, detectors, scorer, and SQLite) against the local demo server across all 22 rows of the
Phase 1 acceptance matrix (spec §12), and verifies that logs and error responses never leak
query secrets, control characters, body bytes or stack traces.

## Inputs and outputs
- Input: the generated sample files in `samples/` (`make samples`) and the session-scoped `Demo` server subprocess (`tests/demo_server.py`).
- Output: automated pytest verification of all 22 acceptance rows (`make test-e2e`) and log safety (`backend/tests/integration/test_log_safety.py`).

## How it works (5–10 lines; the steps you would draw on a whiteboard)

1. `make samples` generates the 19 genuine samples and 5 disguised samples deterministically into `samples/`.
2. The `demo` session fixture starts `demo_server` on three loopback ports (HTTP, HTTPS with a fresh test CA, and wrong-host HTTPS) and `populate_demo_samples` copies `samples/` into the fixture's directory.
3. For each row of spec §12, `run_scan()` creates a fresh FastAPI `TestClient` in the `test` profile (with `a.demo.test`, `b.demo.test`, `c.demo.test` mapped to `127.0.0.1` and exempted only on the demo ports), `POST`s the URL to `/api/scans`, and polls `GET /api/scans/{id}` until `state == "done"`.
4. Each test validates the JSON response against `ScanResult` and asserts `status`, `verdict`, `display_verdict`, `confidence`, `scope.mode`, and required reason codes.
5. `test_log_safety.py` runs scans carrying secret query parameters (`?token=...`), RTL overrides (`/cd/rtl`), NUL bytes (`/cd/nul`), and simulated crashes, asserting that `SECRET_TOKEN`, control/bidi characters, file body contents, and tracebacks never appear in logs or responses.

## Why it is designed this way (the decision and the simpler/harder alternative you rejected)

- **Real sockets on loopback only (`allow_hosts(["127.0.0.1"])`, D44):** tests exercise real TCP, HTTP framing, Range headers, chunked transfer, and TLS certificate pinning (`sni_hostname` + `certifi` + `LG_EXTRA_CA_BUNDLE`) while `pytest-socket` blocks all external network access.
- **Assert reason codes and verdicts, never exact scores (spec §12):** weights are starter hypotheses tuned in Phase F; asserting verdicts and required codes keeps the acceptance tests stable when weights are calibrated.

## How it is tested (test files, acceptance rows it covers)

- `backend/tests/e2e/test_acceptance_matrix.py`: rows 1–22 (24 test cases including 18a/18b/18c).
- `backend/tests/integration/test_log_safety.py`: log redaction, control/bidi character stripping, no body bytes in logs, and crash response safety.

## Known limitations

- Requires local loopback socket binding (`127.0.0.1`), which works in standard local terminals, Docker, and GitHub Actions CI.

## Likely viva questions (and your short answers)

- *How do you test SSRF and HTTPS certificate pinning without the internet?* The demo server runs on loopback with three listeners; `a.demo.test` is resolved via `LG_STATIC_HOSTS` and exempted only for `(a.demo.test, port)` in the `test` profile, while `127.0.0.1` itself and `169.254.169.254` remain blocked.
- *Why does Row 20 (gzip-encoded PDF) return `NO_ISSUES_IN_CHECKED_PART` with low confidence?* Because the server sent `Content-Encoding: gzip` despite `Accept-Encoding: identity`; LinkGuard decodes up to 5 MB safely, flags `FETCH_UNEXPECTED_ENCODING`, and marks scope `partial` and confidence `low` (D10, D56).
