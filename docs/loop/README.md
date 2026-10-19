# The loop: unattended tasks with headless Claude Code

`scripts/loop.py` works through `docs/phase1-tasks.md` one task at a time using `claude -p`.
It implements, checks, reviews and commits each task **on its own branch**. It never merges
and never pushes: you read the diff and the module note, then merge.

## Before you run it

- Claude Code **2.1.259 or later** (`claude --version`); the loop checks this and stops if older.
- You are on `main`, the working tree is clean, and `main` is up to date.
- Every `task/*` branch from an earlier run is merged or deleted (see "Stop messages").
- Gates you have checked are marked under their heading, e.g. `gate: G0 passed 2026-10-20`.

## Running it

```zsh
# what would run, without calling Claude or changing anything
uv run --no-project --python 3.12 python scripts/loop.py --dry-run

# run up to 3 tasks (the default), $3 budget per task (the default)
uv run --no-project --python 3.12 python scripts/loop.py

# one specific task, with a bigger budget, printing every command
uv run --no-project --python 3.12 python scripts/loop.py --task T1.5 --budget 5 --verbose
```

| Option | Meaning |
| --- | --- |
| `--max-tasks N` | Stop after N tasks (default 3) |
| `--task ID` | Run only this task (must be `auto`, unticked, dependencies ticked on `main`) |
| `--budget USD` | Spending limit per task across all its Claude calls (default 3) |
| `--dry-run` | Print the tasks that would run; no Claude calls, no git changes (it still reads `git status` and the branch list) |
| `--verbose` | Print every command the loop runs |

## What happens for each task

1. **Pick:** the next unticked `auto` task whose `depends` are all ticked **on `main`**. `pair`
   and `human` tasks are skipped; you do them yourself.
2. **Branch:** `git switch -c task/<ID> main`.
3. **Implement:** `claude -p` with `.loop/prompts/implement.md`, the task text, its verify
   command and the protected paths. Allowed tools: Read, Edit, Write, Grep, Glob and Bash for
   `make`, `uv`, `npm`, `npx`, `git status`, `git diff`. Nothing prompts; anything else is denied.
4. **Protected paths:** every path changed on the branch (new files too) is checked against
   `.loop/protected.txt`. Any hit rejects the task.
5. **Verify:** the loop runs the task's `verify:` command itself. On failure it resumes the same
   Claude session with `.loop/prompts/fix.md` and the last 200 lines of output.
6. **Review:** a separate, read-only `claude -p` session gets the diff and
   `.loop/prompts/review.md`. "changes_needed" sends the problems back to the implementing session.
7. Fix rounds and review rounds share one limit: **3 correction rounds**, then the task is blocked.
8. **Approve:** the loop ticks the box, appends to `docs/loop/log.md`, commits
   `"<ID>: <summary>"` on the branch and switches back to `main`.

## Stop messages

Every run ends with a line starting `STOP:`.

| Message | Meaning | What to do |
| --- | --- | --- |
| `The working tree is not clean` | Uncommitted changes | Commit or stash them |
| `You are on '<branch>'. Switch to main first.` | Not on main | `git switch main` |
| `Claude Code X is too old` | Version below 2.1.259 | Update Claude Code |
| `Gate G<n> is not passed (...)` | Tasks after a gated section are waiting | Check the gate's criteria, then add `gate: G<n> passed <date>` under that heading on `main` |
| `T<x> needs T<y>, which is committed on unmerged branch task/T<y>` | A dependency is done but only on its branch; boxes are ticked on branches, so it does not count yet | Review and merge `task/T<y>`, then run again |
| `T<x> is committed on unmerged branch task/T<x>` | That task already has a branch | Merge it, or delete the branch to redo the task |
| `T<x> needs T<y>, a pair/human task` | You have to do T<y> yourself | Do it, tick it on `main`, run again |
| `No unticked auto tasks left.` | Nothing for the loop to do | |
| `reached --max-tasks N` | Normal end of a run | Review and merge the new `task/*` branches |
| `T<x> is needs_human` | Claude stopped with questions | See "Answering questions" |
| `T<x> is blocked` | Unfixable after 3 rounds, budget used up, or Claude failed | Read the branch's last log row and the WIP commit |
| `T<x> is rejected` | The branch touched a protected path | Inspect the branch; delete it and run again, or do the task as `pair` |

A stopped task's branch is kept with everything committed on it (`WIP <ID> (<status>): …`),
so `main` stays clean. Its log row and questions are in that commit.

## Answering questions

1. `git switch task/<ID>` and open `docs/loop/questions.md`. The newest section lists Claude's
   questions and any "Proposed decision" lines.
2. Decide. Write each answer after its **A:**, and record agreed decisions in
   `docs/decisions.md` yourself (on `main`).
3. Then either delete the branch (`git switch main && git branch -D task/<ID>`) so the loop
   redoes the task with your decisions in place, or finish the task by hand on the branch.

## Protections

- **Protected paths** (`.loop/protected.txt`): `CLAUDE.md`, the spec, decisions, roadmap,
  style guide, `docs/phase1-tasks.md`, `backend/tests/ssrf/**`, `backend/tests/e2e/**`,
  `.loop/**`, `scripts/loop.py`, `.github/**`. Only the loop ticks task boxes, after verify
  and review pass.
- The loop runs the verify command itself; Claude's own claim of success is not trusted.
- `--permission-prompts none`: anything outside the allowed tools is refused without asking.
- No merge, no push, no `git commit` by Claude (the tool list does not allow it).
- Budget per task via `--max-budget-usd`, passing what is left of `--budget` to each call.
  This is a **soft** limit: Claude Code checks it between its own steps, so one call can go
  over (the first T1.5 run spent $4.82 of $3). The loop makes no new call once the budget is used.

## Files

| File | Purpose |
| --- | --- |
| `scripts/loop.py` | The loop (standard library only) |
| `scripts/tests/test_loop.py` | Unit tests with git and Claude faked: `make test-loop` |
| `.loop/prompts/implement.md`, `fix.md`, `review.md` | Prompts |
| `.loop/result.schema.json`, `review.schema.json` | Structured output Claude must return |
| `.loop/protected.txt` | Paths Claude must never change |
| `docs/loop/log.md`, `questions.md` | Append-only records, written on task branches |

## Known limits

- Ctrl-C or a crash during a task parks it like any other stop (WIP commit, back to `main`).

- Verify commands that start with `cd` are run by the loop through `sh -c`; Claude itself runs
  the equivalent `uv --directory …` / `npm --prefix …` forms, because `cd` is not in its tool list.
- The review sees the diff against `main`; a very large diff makes the review call expensive.
- Log rows and questions reach `main` only when you merge the task's branch.
