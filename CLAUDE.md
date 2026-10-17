# LinkGuard — project context for Claude Code

LinkGuard is a **college major project** built by a small student team. The goal is a complete,
reliable, visually polished, easy-to-demo application whose every part the team can explain in a
viva. Prefer simple, readable code over clever or enterprise-grade solutions.

LinkGuard checks a download link before the user downloads it. A user pastes a public
link; the backend safely fetches the response headers and the first bytes of the file,
works out what the file really is, and returns an honest, explained verdict
(SAFE / SUSPICIOUS / UNSAFE / UNABLE_TO_VERIFY) with reason codes.

**Deployment assumption: the backend runs on localhost only.** It is anonymous, has open CORS
and no rate limits by design (see `docs/decisions.md` D17–D18). Never bind it to a public
interface; any public deployment requires revisiting those decisions first.

**Roadmap** (`docs/roadmap.md`): A Foundations → B Core scanner + web app → C Chrome extension +
UI polish → D Torrent/ZIP inspection → E Known-threat lookup + hardened container → F Results,
report, demo. **Current goal: Phases A and B only** (this semester; "Phase 1" in older docs).
Do not build anything from Phases C–F, and do not add dependencies for them.

## Read these before working

| File | What it holds | When to read |
| --- | --- | --- |
| `docs/roadmap.md` | Phases A–F with Must / Should / Nice labels | To know what is in or out of scope |
| `docs/phase1-spec.md` | Contract v1, module requirements, scoring tables, SSRF table, acceptance matrix | Before any task |
| `docs/ui-style-guide.md` | Colours, type, verdict badges, screen layouts, copy rules | Before any web UI work |
| `docs/phase1-tasks.md` | Ordered task list with acceptance criteria | Pick the next unchecked task |
| `docs/decisions.md` | Decisions already made + open ones | Before making any design choice |
| `docs/report-outline.md` | Report chapters and viva question bank | When a module is finished (add its notes) |
| `docs/modules/_template.md` | Template for the "how this module works" note | After every task |
| `docs/reference/linkguard-implementation-plan.html` | Original plan with ~113 Phase 1 edge-case tables (M1–M7) | When implementing a module: its edge cases are test cases |

If the spec and the original plan disagree, **the spec wins** (it fixes known contradictions
in the plan). If something is unspecified, stop and ask; record the answer in `docs/decisions.md`.

## Non-negotiable rules

Safety
- Downloaded bytes are NEVER executed, imported, decompressed beyond caps, or written to a path derived from remote data.
- Only `backend/app/engine/fetcher/` may open outbound connections to user-supplied URLs. Nothing else may.
- SSRF checks run on the initial URL AND on every redirect hop. Classify RESOLVED addresses, never hostnames. Reject if ANY resolved address is non-public (`ipaddress` `.is_global`, IPv4-mapped IPv6 judged by its IPv4 part).
- Connect to the already-validated IP (pinned). Never resolve twice for one hop.
- TLS verification is never disabled. `trust_env=False` on every HTTP client.
- All remote data (URLs, filenames, headers) is hostile: escape on display, strip control characters in logs, redact query-string values in logs and shared views.
- Secrets only from environment variables. Never commit `.env`.
- The API binds to `127.0.0.1`. In docker-compose, publish ports as `127.0.0.1:8000:8000`, never `8000:8000`.

Honesty (verdict logic)
- Missing evidence is never evidence of safety. Failures → `UNABLE_TO_VERIFY`, never `SAFE`.
- Positive evidence of risk beats missing evidence.
- No negative weights, ever.
- A clean partial scan is displayed as "No issues found in the checked part" (`display_verdict = NO_ISSUES_IN_CHECKED_PART`), never plain "Safe".
- Every result states what was actually read (scope).

Engineering
- The scorer is a pure function: no clock, randomness, network or I/O.
- Every tunable number (caps, timeouts, ports, weights, thresholds) comes from config or the reason-code registry, never hard-coded.
- Every reason code lives in `backend/app/registry/reason_codes.yaml`. A code used in code but missing from the registry must fail tests.
- Tests never touch the real internet. Everything runs against the local demo server or fakes.
- Small, focused functions; each detection check is a separate testable function.
- Explainable code: plain functions and dataclasses/Pydantic models, descriptive names, a short
  docstring saying WHY each check exists. No metaprogramming, plugin frameworks, dependency-injection
  containers or abstraction layers "for later". The team must be able to defend every line in a viva.
- Offline demo: no CDN fonts, scripts or images. Fonts come from npm (`@fontsource/*`).

## Stack (pinned — do not substitute)

- Backend: Python 3.12, FastAPI, Pydantic v2, httpx, idna, SQLite via SQLAlchemy 2 (`create_all` on startup, WAL pragma only, no migrations tool), pytest + pytest-asyncio. Dependency management: `uv` with `uv.lock`.
- Web: React + Vite + TypeScript + Tailwind CSS (tokens from `docs/ui-style-guide.md`), fonts via `@fontsource/ibm-plex-sans` and `@fontsource/ibm-plex-mono`, types generated from the backend OpenAPI with `openapi-typescript`, plain `fetch`, Vitest + React Testing Library. No component library.
- Demo server: separate small Starlette/FastAPI app under `demo/`.
- Dev: docker-compose for backend + web + demo server. CI: GitHub Actions.
- Optional: `python-magic` for logging-only second opinion; the app must work without libmagic.

## Repository layout (target)

```
backend/
  app/
    api/            # FastAPI routers, request/response handling, busy guard
    contract/       # Pydantic models = the API contract (source of OpenAPI)
    core/           # config (profiles: dev, test, demo, prod), logging + safe() helper
    orchestrator/   # scan lifecycle, semaphore + busy guard, executor interface, in-process executor
    engine/
      router/       # input cleaning, link classification (M3)
      fetcher/      # SSRF-safe fetcher (M2) — the ONLY outbound path
      detect/       # file-type detection and mismatch checks (M4)
      scoring/      # scorer v1 (M5), explanation/headline builder
    registry/       # reason_codes.yaml + loader/validator
    db/             # SQLAlchemy model for scans, session
  tests/            # unit/, contract/, ssrf/, golden/, e2e/
demo/               # demo server + make_samples.py (samples generated, never committed)
web/                # React app
docs/               # roadmap, spec, tasks, decisions, style guide, report outline,
                    # limitations, threat model, modules/ (one note per module), reference/
.github/workflows/ci.yml
docker-compose.yml
.env.example
```

## Architecture in one paragraph

`API` validates input, then hands the scan to the `Orchestrator`, which stores the row
(`state=queued`) and runs it through an `Executor` interface. In Phase 1 the executor is
in-process: an asyncio background task gated by `asyncio.Semaphore(4)`; if more than
`LG_MAX_WAITING_SCANS` are already waiting, `POST` returns `503 SERVER_BUSY`. No dedupe, no
cache: every scan is fresh. The executor runs Router → Fetcher → Detectors and returns raw
findings, hops, scope and timings as JSON-serialisable data. The orchestrator validates
that output, runs the scorer, stores the result (`state=done`). Clients poll
`GET /api/scans/{id}`. Phase 2 will swap the executor for a container runner WITHOUT
changing the API, contract, scorer or web app — keep that seam clean (executor input and
output must be plain JSON-compatible models, no shared in-memory objects).

## Commands (create these; keep this section current)

```
make setup        # uv sync; npm ci in web/
make dev          # docker-compose up (api :8000, web :5173, demo :8081/:8443)
make test         # backend pytest (no internet) + web vitest  (= test-backend + test-web)
make test-ssrf    # SSRF table only
make test-e2e     # acceptance matrix against the demo server
make samples      # regenerate samples via demo/make_samples.py
make openapi      # export OpenAPI + regenerate web/src/api/types.ts
make lint         # ruff + mypy (backend), eslint + tsc (web)  (= lint-backend + lint-web)
```

## How to work in this repo

1. Take the next unchecked task in `docs/phase1-tasks.md`. Do one task per branch/PR.
2. Write or extend tests first (edge-case rows from the original plan become test cases).
3. Implement; run `make lint test`. Never mark a task done with failing or skipped tests.
4. Update `docs/phase1-tasks.md` (tick the box), and `docs/decisions.md` / `docs/limitations.md` when relevant.
5. Create or update `docs/modules/<module>.md` from the template: what it does, inputs/outputs,
   how it works in 5–10 lines, how it is tested, known limits, likely viva questions.
6. Stop and summarise the change for the human owner to review. Do not start the next task unasked.
7. If a change touches the contract, bump nothing silently: update models, regenerate OpenAPI and web types, update contract tests, and note it in `docs/decisions.md`.

## Do not

- Add authentication, user/client identity, scan history endpoints, caching, retention jobs,
  rate limiting, queues (Redis/Celery), metrics, health probes or circuit breakers. These were
  cut on purpose (D17).

- Build anything from Phases C–F (extension, reputation APIs, ZIP/torrent/PE/PDF parsing, container hardening) until the roadmap says so.
- Add features the docs do not ask for. Put ideas in `docs/roadmap.md` under "Ideas / future work".
- Use `dangerouslySetInnerHTML` or render any scanned URL as a clickable link.
- Add a global "allow private addresses" switch. The demo exemption is per (hostname, port), demo/test profile only.
- Retry loops beyond a single retry; follow HTML/JS redirects; decode response bodies beyond the byte cap.
- Commit binaries or real installers to the repo.
