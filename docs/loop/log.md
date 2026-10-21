# Loop log

Append-only. `scripts/loop.py` adds one row per task it finishes or parks. Rows are written
on the task's branch, so they reach `main` when you merge that branch.

| When | Task | Branch | Result | Correction rounds | Cost | Summary |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-10-19 21:24 | T1.5 | task/T1.5 | needs_human | 1 | $4.82 | I added WHY docstrings to `detect_7z`, `detect_png` and `detect_jpeg`. The 135 detection tests and ruff pass. I did not make the reviewer's other two changes (a new decision row in `docs/decisions.md` and ticking T1.5 in `docs/phase1-tasks.md`): both files are on the loop's protected list and the loop bans edits to them, so a human has to make them. (questions in docs/loop/questions.md) |
| 2026-10-19 22:38 | T1.6 | task/T1.6 | done | 0 | $2.79 | I built the web skeleton for T1.6: the home, checking, report (all seven display verdicts) and error screens, with submit and polling (backing off up to 2 s) through plain fetch. Tests cover polling, every error state, and the hostile filename `<img src=x onerror=alert(1)>`, which renders as text. `npm run lint`, `npm run typecheck` and `npm test` (114 tests) all pass. Example links on Home and a Retry-After countdown on the busy screen are not built yet; both are listed under Known limitations in docs/modules/web-app.md. |
| 2026-10-21 16:35 | T2.3 | task/T2.3 | blocked | 1 | $5.55 | claude did not finish: error_max_budget_usd |
