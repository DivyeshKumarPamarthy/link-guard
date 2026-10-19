# Phase A + B task list ("Phase 1")

Work top to bottom. One task per branch/PR. A task is done only when its acceptance checks
pass in CI. Track letters: A = fetcher and safety, B = detection, scoring, orchestrator,
C = web, test kit, CI. Spec references point to `docs/phase1-spec.md`.

## Phase A — Foundations (week 1). Gate G0: contract v1 tagged, CI green, wireframes agreed.

- [x] **T0.1 Repo skeleton (C).** Create the layout from `CLAUDE.md`, `.gitignore` (incl. `samples/`, `.env`, `*.db`), `.gitattributes` (binary fixtures), `.env.example`, `.python-version` (3.12), `uv` project in `backend/`, Vite React TS app in `web/`, `Makefile` with the targets listed in `CLAUDE.md` (stubs allowed).
  Accept: `make setup` succeeds on a clean clone; README "Quick start" section exists.
- [x] **T0.2 Config profiles (C).** `backend/app/core/config.py` with every variable in spec §4 (pydantic-settings), profile guard that refuses test/demo-only settings in `dev`/`prod`, WARNING log of active exemptions.
  Accept: unit tests for defaults, env override, and the profile guard.
- [x] **T0.3 Logging + `safe()` helper (A).** Plain `logging` setup; `safe(value)` strips control/ANSI characters and, for URLs, replaces query values with `REDACTED`.
  Accept: unit tests incl. signed-URL, ANSI-escape and RTL-override cases.
- [x] **T0.4 Contract models (B).** Pydantic models for request, `ScanResult`, error body, all enums (spec §2). Export OpenAPI to `backend/openapi.json`; `make openapi` generates `web/src/api/types.ts`.
  Accept: example JSON from spec §2 validates; unknown extra fields tolerated on the client side test.
- [x] **T0.5 Reason-code registry (B).** `reason_codes.yaml` with every code in spec §8, loader + validator (prefixes, groups, weights ≥ 0, templates render).
  Accept: validator tests; a test that greps the backend for `[A-Z]+_[A-Z_]+` codes used in code and fails if any is missing from the registry.
- [x] **T0.6 Database (C).** SQLAlchemy model `scans` (id, state, status, verdict, display_verdict, input_url, final_url, result_json, schema_version, engine_version, rules_version, created_at, completed_at); `create_all` on startup; WAL pragma.
  Accept: write/read round-trip test on a temp DB.
- [x] **T0.7 API + mock scanner (B).** `POST /api/scans` and `GET /api/scans/{id}` (spec §2) with a `MockExecutor` returning a fixed `UNSAFE` result after 300 ms; input error codes; `413`; CORS `*` without credentials; API binds to `127.0.0.1`.
  Accept: API tests for 202 → poll → done, 400 codes, 404 for an unknown id.
- [x] **T0.8 CI (C).** GitHub Actions: backend lint (ruff, mypy) + pytest with network disabled (`pytest-socket` or equivalent), web lint + tsc + vitest, contract check that `web/src/api/types.ts` is up to date with `openapi.json`, secret scanning.
  Accept: CI green on the skeleton.
  *Done 2026-10-17: all 4 jobs green on PR #1 (https://github.com/DivyeshKumarPamarthy/link-guard/actions/runs/39012343803).*
- [x] **T0.9 Docs scaffolding (all).** `docs/threat-model.md` (one page: assets, attackers, SSRF/DoS/XSS/log-leak mitigations, residual risks), `docs/limitations.md`, confirm or edit every **[CONFIRM]** item in the spec and record it in `docs/decisions.md`.
  Accept: no open **[CONFIRM]** without an owner and date in `decisions.md`.
  *Done 2026-10-19: owner Divyesh for all tracks (D16); C1, C2, C4–C6 confirmed; C3 has an owner and date and waits on D15.*
- [x] **T0.10 Wireframes + Tailwind tokens (C).** Team sketches the 7 screens listed in `docs/ui-style-guide.md` (paper or Figma, photos/exports into `docs/wireframes/`). Claude Code then sets up Tailwind with the guide's colour, type and radius tokens, light + dark, and a `/styleguide` dev-only page showing every verdict badge and the claimed-vs-actual panel with mock data.
  Accept: team approves wireframes; `/styleguide` renders all states in light and dark mode; contrast checked (WCAG AA).
  *Done 2026-10-19: tokens, components and `/styleguide` with contrast tests; wireframes for all 7 screens approved by the team (`docs/wireframes/draft-wireframes.md`, D32, D33).*
- [x] **T0.11 Report skeleton + literature survey outline (team, no code).** Fill `docs/report-outline.md` chapter 1–2 headings with notes: problem statement, objectives, comparison with VirusTotal, Chrome Safe Browsing and URL expanders.
  Accept: supervisor has seen the problem statement and scope.
  *Marked done 2026-10-19 on Divyesh's confirmation that the team approved it. Draft notes for chapters 1–2 are in `report-outline.md`; the [VERIFY + cite] items still need sources before the final report.*

## Phase B, sprint 1 — Weeks 2–3

- [x] **T1.1 Demo server v1 (C).** `demo/` app with HTTP 8081 + HTTPS 8443, local test CA generation script (`demo/certs/`), endpoints from spec §11 needed by the fetcher: `/f`, `/big`, `/slow`, `/reset`, `/chunked`, `/gzip`, `/redirect/*`, `/status/*`, `/page`, `/empty`, and a "wrong host cert" HTTPS listener (for row 22).
  Accept: smoke tests hitting each endpoint directly.
  *Done 2026-10-19: 59 smoke tests (in-process + real sockets incl. both TLS listeners); wrong-cert listener on :8444 (D34). `/disguised`, `/cd`, `/index` come with the samples (T2.6) and detection (T1.5) work.*
- [ ] **T1.2 URL validation + IP classification (A).** Parser, scheme/userinfo/port/length checks, host normalization (IDNA, trailing dot), strict IP-literal parsing (decimal/octal/hex/short/full-width), `Resolver` interface (system + static-hosts + fake for tests), classification with `ipaddress`, exemption logic (exact host:port, test/demo only).
  Accept: every SSRF table row in spec §5 that does not need a redirect passes with a socket guard asserting zero connections.
- [ ] **T1.3 Pinned-TLS spike (A). Time-box: 2 days.** Prove a request to the validated IP with SNI + certificate verification against the original hostname, using the 8443 demo listener and the test CA. Record the chosen approach in `docs/decisions.md`; if the fallback is used, record the residual rebinding risk in `docs/limitations.md`.
  Accept: valid cert → 200; wrong-host cert → TLS error; resolver called exactly once.
- [ ] **T1.4 Redirect handling (A).** Manual redirects (max 5), relative Location, visited-set loop detection, full re-validation per hop, downgrade flag, hop records, rejected-at-hop with chain so far, non-HTTP targets (unsupported vs rejected per spec §6).
  Accept: remaining SSRF rows pass; unit tests for loop, too-many, downgrade, bad target.
- [ ] **T1.5 Detection on fixtures (B).** Signature table and `detect_type` for spec §7; claimed-name extraction incl. RFC 5987; extension chain analysis. Works on byte fixtures, no network.
  Accept: every format detected from generated genuine samples; Content-Disposition variants parsed safely.
- [ ] **T1.6 Web skeleton on the mock (C).** Home, submit, polling, report rendering from the mock, error states, all using the Tailwind tokens and layouts from the style guide.
  Accept: vitest for polling and the error states; renders a hostile filename `<img src=x onerror=alert(1)>` as text.

## Phase B, sprint 2 — Weeks 4–5

- [ ] **T2.1 Streaming fetch (A).** HEAD → GET-with-Range fallback, `Accept-Encoding: identity`, byte cap counting bytes actually read, total deadline + min throughput, Range verification (206 + Content-Range), ignore-Range handling, unexpected encoding, error-status mapping (401/403/429/404/410/5xx), one retry max for 429 with short Retry-After, empty body, interrupted stream, DNS and TLS errors. Returns `FetchResult` (spec §5).
  Accept: fetcher integration tests against the demo server for each endpoint; a 200 MB stream stops at 5 MB within seconds with stable memory.
- [ ] **T2.2 Mismatch checks (B).** All checks in spec §7 as separate functions with equivalence classes; DOCX/XLSX subtype via in-memory listing for full-scope ZIPs only.
  Accept: one positive and one negative test per check; clean samples of every format produce no mismatch codes.
- [ ] **T2.3 Scorer v1 + explanations (B).** Pure scorer (spec §9), outcome rules, scope, confidence, display verdict, headline (spec §3); golden tests.
  Accept: golden tests for thresholds 29/30/59/60, hard rule, grouping, unable vs risk precedence, partial never shows SAFE.
- [ ] **T2.4 Orchestrator + in-process executor (B).** Executor interface (JSON-compatible input/output), in-process executor running router → fetcher → detectors as an asyncio background task, `asyncio.Semaphore(LG_MAX_CONCURRENT_SCANS)`, waiting counter → 503 `SERVER_BUSY` above `LG_MAX_WAITING_SCANS`, overall timeout, state transitions persisted, output validated before scoring, `ANALYSIS_ERROR` on exceptions. No dedupe.
  Accept: unit tests for busy (503), timeout, exception path; swapping `MockExecutor` for the real one is config only.
- [ ] **T2.5 Localhost-only exposure (A).** Default bind `127.0.0.1`; docker-compose publishes `127.0.0.1:8000:8000` (and the same for web and demo); README states the backend must not be exposed publicly and why.
  Accept: a test or CI check that fails if compose publishes any port without the `127.0.0.1:` prefix.
- [ ] **T2.6 Samples generator + report page (C).** `make_samples.py` (fixed seeds; hello PE generated by script), disguised variants; web report page complete (spec §10) including the claimed-vs-actual hex panel; first real endpoint wired by end of week 4.
  Accept: `make samples` reproducible (hash-stable); report renders every field from a real result.

## Phase B, sprint 3 — Weeks 6–7. Gate G1: all acceptance rows green, feature freeze for Phase B.

- [ ] **T3.1 Router (A).** Input cleaning, `classify()` pure function, unsupported types, shortened detection, web-page detection (header + sniff), redirect-chain view model; P1: cloud-share hint, homograph flag.
  Accept: table-driven tests covering the M3 edge cases in the reference plan.
- [ ] **T3.2 Wire web to real backend (C).** Polling with backoff, REJECTED / UNSUPPORTED / UNABLE / busy screens, 360 px layout, keyboard and focus, dark mode. P1: localStorage recent-scans list.
  Accept: manual checklist in `docs/` passes; vitest for each screen.
- [ ] **T3.3 Acceptance matrix e2e (C).** One pytest per row of spec §12 running the backend against the demo server with the test profile.
  Accept: all 22 rows green in CI with network disabled except loopback.
- [ ] **T3.4 Contract-gap fixes (B).** Anything integration surfaced; regenerate types; note changes in `decisions.md`.
  Accept: contract check green.
- [ ] **T3.5 Log and error review (A).** No stack traces in responses; every log call that includes remote data uses `safe()`.
  Accept: test that captures logs from the e2e run and finds no raw query values, control characters or body bytes.

## Phase B, sprint 4 — Weeks 8–10. Gate G2: Phase 1 review/submission done.

- [ ] **T4.1 Bug fixes only.** No new features after G1.
- [ ] **T4.2 One-command demo.** `make demo` starts everything offline; demo script in `docs/demo-script.md` with expected results for each step.
- [ ] **T4.3 Rehearsal + backup video.** Network off; record.
- [ ] **T4.4 Phase 1 report.** Fill chapters 3–6 of `docs/report-outline.md` from the module notes: architecture, threat model, what is built, test results (acceptance matrix output), known limitations. Screenshots of every screen in light mode.
- [ ] **T4.7 Viva prep.** Each owner presents their module notes to the others; update the viva question bank with any question nobody could answer.
- [ ] **T4.5 Fresh-machine check.** Someone who did not write the README starts the stack in under 15 minutes.
- [ ] **T4.6 Tag `v1.0.0`.**
