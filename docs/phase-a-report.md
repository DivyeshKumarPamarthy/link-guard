# Phase A report: Foundations (T0.1–T0.11)

Date: 2026-10-17 · Built with Claude Code (decision D21: every change must be reviewed and
understood by its track owner before merge) · Status: **Phase A done (2026-10-19)**

## 1. Summary

All code tasks of Phase A are built and verified locally. Four tasks cannot be ticked yet
because their acceptance checks need people or GitHub, not code: CI must go green after the
first push (T0.8), owners must be named (T0.9), the team must draw and approve wireframes
(T0.10), and the supervisor must see the problem statement (T0.11).

| Task | What it delivers | Status |
| --- | --- | --- |
| T0.1 Repo skeleton | Layout, uv backend, Vite React TS web, Makefile, README | ✅ Done |
| T0.2 Config profiles | `Settings` from `LG_*` env vars, profile guard, exemption warnings | ✅ Done |
| T0.3 Logging + `safe()` | Strips ANSI/control/bidi characters, redacts URL secrets | ✅ Done |
| T0.4 Contract models | Pydantic models → `openapi.json` → `web/src/api/types.ts` | ✅ Done |
| T0.5 Reason-code registry | 37 codes in YAML, strict validator, code-usage scan | ✅ Done |
| T0.6 Database | SQLite `scans` table, WAL, `create_all` | ✅ Done |
| T0.7 API + mock scanner | `POST`/`GET /api/scans`, 400/404/405/413/500, CORS, 127.0.0.1 | ✅ Done |
| T0.8 CI | 4 GitHub Actions jobs; network blocked in tests | ✅ Done: green on PR #1 |
| T0.9 Docs scaffolding | Threat model, limitations, C1–C6 confirm list | ✅ Done 2026-10-19: owner Divyesh (D16), C1–C6 confirmed (C3 closed by D15) |
| T0.10 Wireframes + tokens | Tailwind tokens, components, `/styleguide` | ✅ Done 2026-10-19: wireframes approved (D32, D33) |
| T0.11 Report skeleton | Draft notes for chapters 1–2 | ✅ Done 2026-10-19 (team approval reported by Divyesh); citations still to add |

## 2. Verification evidence

Everything below was run on 2026-10-17 on macOS (Apple Silicon), Python 3.12.12, Node 24.8.0.

| Check | Result |
| --- | --- |
| Clean-copy check: only git-tracked files copied to an empty folder, then `make setup` → `make lint` → `make test` → `make openapi` | all exit 0 |
| Backend tests (pytest, sockets blocked) | **169 passed**, 0 skipped |
| Web tests (vitest) | **73 passed**, 0 skipped |
| `make lint` | ruff, ruff format, mypy `strict` (37 files), eslint (0 warnings), tsc: all clean |
| `make openapi` run twice | byte-identical `openapi.json` and `types.ts` (needed for the CI contract job) |
| `actionlint` on `ci.yml` | no findings |
| Real server: `uv run python -m app` | listens on `127.0.0.1:8000` only (checked with `lsof`); POST → poll → UNSAFE mock result |
| Production web build | `/styleguide` absent from the bundle (0 occurrences); no CDN references; fonts bundled |
| Visual check (headless Chrome) | `/styleguide` at 1440 px and a true 360 px: all 7 states in light and dark |
| GitHub CI on PR #1 | all 4 jobs green, gitleaks included (https://github.com/DivyeshKumarPamarthy/link-guard/actions/runs/39012343803) |

Test count by area (backend): config 29 · safe/logging 30 · contract models 25 · OpenAPI 3 ·
registry 27 · database 5 · API 34 · skeleton 12 · no-network 2 · hidden characters 2.
Web: contract reader 8 · components 17 · contrast 42 · text helpers 4 · style guide 1 · app 1.

## 3. What was built, task by task

Each module has a note in `docs/modules/` (what, how, why, tests, limits, viva questions).

- **T0.1** (`setup.md`): lock files with `uv sync --locked` / `npm ci`; unbuilt `make` targets exit 1 naming their task.
- **T0.2** (`config.md`): every spec §4 variable plus D23 additions; demo exemptions refused outside `test`/`demo`.
- **T0.3** (`logging.md`): `safe()` handles signed URLs, magnet trackers, userinfo passwords, ANSI CSI/OSC, newline forgery, U+202E and all zero-width/bidi characters.
- **T0.4** (`contract.md`): all enums from spec §2; a validator makes dishonest results impossible (plain SAFE needs full scope and confidence ≥ medium; outcome fields null until done). Web side: tolerant `readScanResult()` that refuses schema 2.x.
- **T0.5** (`registry.md`): YAML matches the spec §8 table exactly (a test compares all 37 rows); refuses duplicates, typos, negative weights, undeclared template keys.
- **T0.6** (`database.md`): 13-column table, WAL, round-trip test through a fresh engine.
- **T0.7** (`api.md`): body limit checked on declared *and* received bytes; executor crashes or dishonest executor output become UNABLE_TO_VERIFY / `ANALYSIS_ERROR`; no list endpoint.
- **T0.8** (`ci.md`): jobs backend · web · contract · secrets (gitleaks).
- **T0.9**: `threat-model.md`, `limitations.md`, decisions D23–D31, confirm items C1–C6.
- **T0.10** (`web-tokens.md`): Tailwind v4 with only the guide's colours; contrast computed from the real CSS in tests; components ready for T1.6.
- **T0.11**: draft notes in `report-outline.md` with every external claim marked **[VERIFY + cite]**; 5 new viva questions.

## 4. Decisions to review (in `docs/decisions.md`, status `default` unless noted)

| # | Decision | Why it needs your eye |
| --- | --- | --- |
| D23 | New config vars: `LG_API_PORT`, `LG_MAX_REQUEST_BYTES`, `LG_POLL_AFTER_MS`, `LG_MOCK_DELAY_MS` | Spec named the numbers but not the variables |
| D24 | `family` enum adds `text`, `unknown` | Contract change vs spec §7 |
| D25 | Extra error codes `INVALID_REQUEST`, `REQUEST_TOO_LARGE`, `NOT_FOUND`, `METHOD_NOT_ALLOWED`; no 422 | Contract change vs spec §2 |
| D26 | Rejected/unsupported codes: weight 0, severity info | Spec said "–" |
| D27 | Templates say "a {detected_label}"; evidence must include `detected_label` | Spec examples contradicted each other |
| D28 | TypeScript 5.9, jsdom 29, ESLint 9 (not the template's TS 6 / oxlint) | Tooling compatibility |
| D29 | Outcome rules enforced in the contract; minimal `ANALYSIS_ERROR` path brought forward from T2.4 | Slight scope pull-forward, for honesty |
| D30 | Errors logged as type + `safe(message)`, no raw tracebacks | Less debugging detail in logs |
| D31 | **open**: docker needs `0.0.0.0` inside the container vs D18 "bind 127.0.0.1" | Must be decided before T2.5 |

## 5. Findings worth knowing

1. **Hidden characters slipped into source files.** While writing code, the AI tooling turned
   several escape sequences (U+202E and similar) into the real invisible characters in four
   files. Tests still passed, but this is the "Trojan Source" pattern (CVE-2021-42574). All were
   converted back to visible escapes, and a new test now fails if any source or doc file contains
   such a character. It has already caught one more case. Review AI-written code with this in mind.
2. **Spec inconsistencies fixed by decision:** the §2 example `scan_id` is not a valid UUID;
   the §2 evidence lacks the key the §8 template needs (D27); "–" weights (D26).
3. **Accessibility gap in the style guide:** the `line` colour is 1.29:1 against `paper`, too
   faint as the only outline of a text input (WCAG 1.4.11 needs 3:1). Inputs use `muted` (5.3:1).
   Please add this rule to `docs/ui-style-guide.md`.
4. **Any website can use the local API** because CORS is `*` (D17). SSRF checks still protect the
   network, but a page could make LinkGuard fetch public URLs. Documented as a residual risk;
   revisit in Phase C.
5. **FastAPI `/docs` needs internet** (Swagger UI from a CDN): take report screenshots while online.
6. **Signed URLs are stored in full** in `linkguard.db` with no retention (D17). Now in the README.
7. **uvicorn's own crash logs** can still print tracebacks with remote data; T3.5 must handle them.
8. **TypeScript 5.9 vs 6:** TS 6 turns on `strict` by default and 5.9 doesn't. `strict` and `DOM.Iterable` are now set explicitly.

## 6. What the team must do to pass gate G0

*Update 2026-10-19: done. Owners D16, C1–C6 confirmed, wireframes approved (D33), Phase A merged to `main` via PR #1. Still open: D31 (docker bind, before T2.5), and sources for the [VERIFY + cite] items before the final report.*

1. ~~Commit, push, CI green~~ done 2026-10-17 (PR #1); review and merge PR #1.
2. **Decide D16** (owners of tracks A, B, C); fill the Owner lines in `docs/modules/*.md` and C1–C6.
3. **Confirm or change C1–C6** and D23–D30; decide **D31** before T2.5 (decided 2026-10-19); D15 decided 2026-10-19 (the §7 table is final).
4. **Wireframes**: sketch the 7 screens into `docs/wireframes/`, approve them → tick T0.10.
5. **Report**: rewrite the chapter 1–2 notes in your own words, find sources for every [VERIFY + cite], show the supervisor → tick T0.11.
6. **Tag contract v1** after merging (e.g. `git tag contract-v1`).
7. On GitHub: protect `main` and require the CI checks.

## 7. Committing this work

CLAUDE.md asks for one task per branch. This phase was built in one pass in one working tree,
and several files are shared between tasks (Makefile, `pyproject.toml`, `package.json`,
`decisions.md`), so clean per-task commits are not possible after the fact. Recommended:
commit the kit docs on `main`, then put all of Phase A on one branch `phase-a` as one pull
request, reviewed module by module using the notes in `docs/modules/`. From Phase B on, go back to
one task per branch.

## 8. Next task

**T1.1 Demo server v1** (start of Phase B, sprint 1), then T1.2 (URL validation + SSRF table).
