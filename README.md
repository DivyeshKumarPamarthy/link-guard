# LinkGuard

LinkGuard checks a download link before you download it. You paste a public link; the backend
safely fetches the response headers and the first bytes of the file, works out what the file
really is, and returns an explained verdict: Safe, Suspicious, Unsafe or Unable to verify.

College major project. Scope, design and task list live in [`docs/`](docs/); start with
[`docs/roadmap.md`](docs/roadmap.md) and [`docs/phase1-spec.md`](docs/phase1-spec.md).

## Quick start

Prerequisites (macOS shown; any OS with these tools works):

| Tool | Version | Install |
| --- | --- | --- |
| Python | 3.12 | `uv python install 3.12` (uv installs it for you) |
| uv | recent (tested with 0.11) | `brew install uv` |
| Node.js + npm | Node 24 (or 22.13+) | `brew install node@24` |
| make | any | included with the Xcode Command Line Tools: `xcode-select --install` |

```zsh
git clone https://github.com/DivyeshKumarPamarthy/link-guard.git
cd link-guard
make setup     # installs backend and web dependencies from the lock files
make test      # runs backend (pytest) and web (vitest) tests
```

`make lint` runs ruff + mypy and eslint + tsc; `make openapi` regenerates the API contract files.
Other targets (`dev`, `samples`, `test-ssrf`, `test-e2e`) are listed in `CLAUDE.md`; until their
task is done they print which task will build them and exit with an error.

Web app: `cd web && npm run dev`, then open <http://localhost:5173/> (the dev-only style guide
is at `/styleguide`).

Configuration comes from environment variables; see `.env.example`. Never commit `.env`.

Run the API (mock scanner for now): `cd backend && uv run python -m app`, then open
<http://127.0.0.1:8000/docs>. Scans are stored in `backend/linkguard.db`, **including the full
links you submit**. Signed links (`?token=…`) keep their secrets there; logs show them as
`REDACTED`. Delete the file to clear it.

## Localhost only

The backend must run on `127.0.0.1` only and must never be exposed on a public interface.
It has no authentication, open CORS and no rate limits by design (decisions D17 and D18 in
`docs/decisions.md`), and it makes outbound requests to whatever link it is given. Exposed
publicly, anyone could use it to make requests on your behalf.

## Repository layout

```
backend/   FastAPI app (app/) and tests (tests/)
web/       React + Vite + TypeScript app
demo/      local demo server and sample generator (from T1.1)
docs/      roadmap, spec, tasks, decisions, style guide, module notes
```
