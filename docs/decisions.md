# Decision log

Newest first. Status: `decided` (team agreed), `default` (chosen to unblock work; confirm),
`open` (must be answered before the listed task).

| # | Date | Decision | Status | Rationale | Affects |
| --- | --- | --- | --- | --- | --- |
| D35 | 2026-10-19 | Demo server: its own uv project in `demo/` (Starlette, uvicorn, cryptography), not part of the backend; `/redirect/chain?n=` counts redirects (n=1: a.demo.test → b.demo.test/file); `to` must be a path (no open redirect); explicit Content-Type table instead of `mimetypes` (same on every OS); the test CA key is never written to disk | default | Keeps demo-only dependencies out of the backend; deterministic tests | T1.1, T3.3 |
| D34 | 2026-10-19 | Row 22's "wrong host cert" HTTPS listener runs on its own port 8444 (cert for `wrong-host.example`); test/demo config adds 8444 to `LG_ALLOWED_PORTS` and `a.demo.test:8444` to `LG_SSRF_EXEMPT` | default | uvicorn cannot pick a certificate per hostname (SNI) on one port; a second port is the simplest honest setup | T1.1, T1.3, row 22 |
| D33 | 2026-10-19 | Wireframe questions: versions only in report Details; recent scans below "What we check"; no Cancel while checking; score only in Details; "what you can try" hints are web-app copy keyed by reason code; no automatic retry on 503 | default | Team approved the drafts without answering these; simplest honest option chosen for each | T1.6, T3.2 |
| D32 | 2026-10-19 | Wireframes: Claude Code drafts the 7 screens as text wireframes (`docs/wireframes/draft-wireframes.md`) from the style guide; the team corrects and approves them in the file's approval table | default | Faster start; approval stays with the team, so T0.10 is ticked only after it | T0.10 |
| D31 | 2026-10-17 | Open: inside a docker container the API must listen on `0.0.0.0` for a published port to work, but D18 says bind `127.0.0.1`. Proposal: keep the `127.0.0.1` default; compose sets `LG_BIND_HOST=0.0.0.0` inside the container and publishes `127.0.0.1:8000:8000`, so the host still only exposes loopback | open | Needed before T2.5; a loopback-only check in config would break docker-compose | T2.5 |
| D30 | 2026-10-17 | Errors are logged as exception type + `safe(message)`, never as raw tracebacks, because exception text (e.g. from httpx) can contain URLs with secrets | default | Keeps the "every log of remote data goes through safe()" rule; uvicorn's own traceback logging is still to be reviewed in T3.5 | T0.7, T3.5 |
| D29 | 2026-10-17 | `ScanResult` enforces the spec §2/§3 outcome rules in a validator (null outcome until done; verdict only when completed; REJECTED/UNSUPPORTED match status; plain SAFE only for full scope + confidence ≥ medium). Executor failure or invalid executor output → `ANALYSIS_ERROR` / UNABLE_TO_VERIFY (minimal version brought forward from T2.4) | default | Makes a dishonest result impossible to store or return, whatever the code path | T0.4, T0.7, T2.4 |
| D28 | 2026-10-17 | Web tooling: TypeScript 5.9 (openapi-typescript 7 requires TS 5; TS 6 from the Vite template removed; `strict: true` set explicitly), jsdom 29 (jsdom 30 needs Node ≥ 24.15), ESLint 9 + typescript-eslint replaces the template's oxlint (CLAUDE.md says eslint). Backend: pytest-socket blocks all sockets in tests; gitleaks-action for secret scanning (no licence needed on a personal account) | default | Matches the pinned stack and the team's Node versions | T0.1, T0.4, T0.8 |
| D27 | 2026-10-17 | Spec §2's example evidence lacks `detected_label`, but the §8 template needs it: `TYPE_MISMATCH_EXEC` evidence is `claimed_ext, detected, detected_label`. Templates write "a {detected_label}" (matching the §2 example text), so every detector label must read correctly after "a" (e.g. "Windows executable", not "OLE container") | default | Spec examples were inconsistent; the registry validator requires every template key to be declared | T0.5, T1.5 |
| D26 | 2026-10-17 | Rejected and unsupported codes (weight "–" in spec §8) are stored as weight 0, severity `info`; only `risk` codes may have a weight above 0, and every `risk` code must | default | Contract `Reason` needs a weight and severity; enforced by the registry validator | T0.5 |
| D25 | 2026-10-17 | Extra API error codes: `INVALID_REQUEST` (malformed JSON or non-string `url`), `REQUEST_TOO_LARGE` (413), `NOT_FOUND` (404, also for malformed ids), `METHOD_NOT_ALLOWED` (405, e.g. `GET /api/scans`). A missing `url` field → `URL_EMPTY`. FastAPI's 422 is never used; it is also removed from OpenAPI | default | Spec gave codes only for URL errors, busy and 500; every error must still be an ErrorBody | T0.4, T0.7 |
| D24 | 2026-10-17 | `file.family` enum adds `text` and `unknown` to the spec §7 families; `detected_type` stays an open string until T1.5 fixes the type names | default | Needed for non-HTML text (`TYPE_MISMATCH_TEXT`) and undetected files | T0.4, T1.5 |
| D23 | 2026-10-17 | Config variables added to spec §4 (tunable numbers must come from config): `LG_API_PORT`=8000, `LG_MAX_REQUEST_BYTES`=8192 (413 limit), `LG_POLL_AFTER_MS`=500, `LG_MOCK_DELAY_MS`=300. To add later: a grace-period variable for `LG_MIN_THROUGHPUT_BPS` (C1) in T2.1 and a `Retry-After` value in T2.4 | default | Spec named these numbers but gave no variable | T0.2, T0.7 |
| D22 | 2026-10-16 | Contract adds `file.detected_label`, `file.first_bytes_hex` (16 bytes) and `file.signature` | default | Powers the "claimed vs actual" panel, the clearest way to show the core idea in a demo | T0.4, T2.6 |
| D21 | 2026-10-16 | AI tooling: every Claude Code change is reviewed and understood by its track owner before merge; each module gets a `docs/modules/` note; AI use declared per college policy | decided | Viva readiness and academic integrity | All |
| D20 | 2026-10-16 | Roadmap per mentor review: Must = A, B, C (extension + UI polish), F; Should = D (torrent + ZIP), E (one or two free threat databases + one hardened container replacing per-scan sandboxes); dropped magnet, YARA, 7z/RAR, blob uploads | decided | Complete project first, depth second | roadmap.md |
| D19 | 2026-10-16 | Tailwind CSS + IBM Plex Sans/Mono via @fontsource; no component library; no CDN assets | default | Polished, consistent look; works offline on demo day | T0.10 |
| D18 | 2026-10-16 | Backend runs on localhost only (bind 127.0.0.1; compose publishes on 127.0.0.1) | decided | Condition for D17: an anonymous, open-CORS, unlimited backend must not be reachable from other machines | T0.7, T2.5 |
| D17 | 2026-10-16 | Scope cuts: no auth/identity/`client_id`, no history API, no caching/retention/dedupe, no PostgreSQL or migrations tool, no rate limits beyond `Semaphore(4)` + 503 when >20 waiting, no queue infrastructure, no JSON logs/metrics/`/healthz`, no circuit breakers (try/except + 5 s timeout), CORS `*` without credentials, no consent screens (README note that Phase 2 reputation sends URLs to third parties) | decided | Focus effort on the detection and safety engine; acceptable for a localhost academic demo | T0.3, T0.6, T0.7, T2.4, T2.5, T3.2 |
| D16 | 2026-10-19 | Divyesh owns tracks A, B and C until the team splits them; update the module notes when it does | default | Owners needed for review (D21) and the confirm items | All |
| D15 | — | The 16th supported format | open | Plan says 16, lists 15 | T1.5, T2.6 |
| D14 | 2026-10-16 | Python 3.12, `uv`, React + Vite + TS, openapi-typescript; SQLite via SQLAlchemy `create_all` (no Alembic) | default | Matches plan stack; one toolchain for all | T0.1 |
| D13 | 2026-10-16 | ~~Rate limits per client/IP~~ superseded by D17: 4 concurrent scans, 503 above 20 waiting | decided | Simplification | T2.4 |
| D12 | 2026-10-16 | `EXT_SPOOFED_NAME` weight 40, `TYPE_POLYGLOT` weight 30 (confirmed 2026-10-19, C4/C5) | decided | Plan gave no weights | T0.5 |
| D11 | 2026-10-16 | Added rows 21 (valid HTTPS via pinned connect) and 22 (wrong-host cert) | default | Plan had no test for pinned TLS, its riskiest path | T3.3 |
| D10 | 2026-10-16 | Row 20 gzip → SAFE / NO_ISSUES_IN_CHECKED_PART, confidence low, scope partial; `FETCH_UNEXPECTED_ENCODING` weight 0 | default | Plan gave no weight; encoding is a reliability signal, not risk | T2.1, T2.3 |
| D9 | 2026-10-16 | Any HTML body (by header or sniff) → `LINK_IS_WEB_PAGE` → UNABLE_TO_VERIFY. `TYPE_MISMATCH_TEXT` only for non-HTML text | default | Resolves plan row 7 ("SAFE or Unable to Verify") to one outcome | T3.1, row 7 |
| D8 | 2026-10-16 | `REDIR_CROSS_DOMAIN` is informational (weight 0); shortened = redirect to a different hostname | default | Plan had weight 5 in M5 vs "informational" in M3 | T0.5, rows 8–9 |
| D7 | 2026-10-16 | Scope enum adds `none` | default | Plan rows used `none` but enum lacked it | T0.4 |
| D6 | 2026-10-16 | Redirect to `magnet:`/`ftp:`/`intent:` → unsupported; other non-HTTP targets → rejected `REDIR_BAD_TARGET` | default | Plan M2 and M3 disagreed | T1.4 |
| D5 | 2026-10-16 | Reason-code prefixes fixed; `CONTENT_TYPE_MISMATCH` → `TYPE_CONTENT_TYPE_MISMATCH`; `RATE_LIMITED` → HTTP 429 `API_RATE_LIMITED`; Chrome codes will use `BROWSER_` | default | Plan had unprefixed codes and an `EXT_` collision | T0.5 |
| D4 | 2026-10-16 | Backend computes `display_verdict`; clients render only from it | default | Keeps web and future extension consistent | T0.4 |
| D3 | 2026-10-16 | Async contract from day 1: `POST` → 202 + `scan_id`, clients poll; `state` separate from `status` | default | Avoids breaking change when extension/worker arrive | T0.4, T0.7 |
| D2 | 2026-10-16 | Demo SSRF exemption = static-hosts resolver + exact host:port exemptions, test/demo profile only, refused in dev/prod | default | Lets e2e run on loopback without weakening SSRF tests | T0.2, T1.2 |
| D1 | 2026-10-16 | Phase 1 scope = M1–M7 + X1–X5; Phases 2–4 out of scope | default | From the plan audit | All |

## Items to confirm

Every **[CONFIRM Cn]** marker in `docs/phase1-spec.md`. The default applies until the team
confirms or changes it; record the outcome here and in the table above. Confirmed by Divyesh
on 2026-10-19 (owner of all tracks, D16); C3 waits on D15.

| # | Spec | Default in use | Owner | Confirm by | Status |
| --- | --- | --- | --- | --- | --- |
| C1 | §4 `LG_MIN_THROUGHPUT_BPS` | 1024 B/s, enforced after a 5 s grace period | Divyesh | Before T2.1 (week 4) | confirmed 2026-10-19 |
| C2 | §4 `LG_LONG_CHAIN_HOPS` | more than 3 redirects → `REDIR_LONG_CHAIN` | Divyesh | Before T1.4 (week 2) | confirmed 2026-10-19 |
| C3 | §7 format list | the 15 listed formats; 16th format is D15 | Divyesh | Before T1.5 (week 2) | default confirmed 2026-10-19; 16th format open (D15) |
| C4 | §8 `EXT_SPOOFED_NAME` weight | 40 (D12) | Divyesh | Before T2.3 (week 4) | confirmed 2026-10-19 |
| C5 | §8 `TYPE_POLYGLOT` weight | 30 (D12) | Divyesh | Before T2.3 (week 4) | confirmed 2026-10-19 |
| C6 | §13 non-functional targets | p95 < 3 s for ≤ 5 MB on the demo server; deadline + 2 s; memory bounded by the cap; 4 concurrent scans | Divyesh | Before T3.3 (week 6) | confirmed 2026-10-19 |
