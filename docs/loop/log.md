# Loop log

Append-only. `scripts/loop.py` adds one row per task it finishes or parks. Rows are written
on the task's branch, so they reach `main` when you merge that branch.

| When | Task | Branch | Result | Correction rounds | Cost | Summary |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-10-19 21:24 | T1.5 | task/T1.5 | needs_human | 1 | $4.82 | I added WHY docstrings to `detect_7z`, `detect_png` and `detect_jpeg`. The 135 detection tests and ruff pass. I did not make the reviewer's other two changes (a new decision row in `docs/decisions.md` and ticking T1.5 in `docs/phase1-tasks.md`): both files are on the loop's protected list and the loop bans edits to them, so a human has to make them. (questions in docs/loop/questions.md) |
