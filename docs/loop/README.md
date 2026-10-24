# The loop: unattended tasks with headless Claude Code

`scripts/loop.py` works through `docs/phase1-tasks.md` one task at a time using `claude -p`.
It implements, checks, reviews and commits each task **on its own branch**. It never merges
and never pushes: you read the diff and the module note, then merge.

## Before you run it

- Claude Code **2.1.295 or later** (`claude --version`; the version verified with `--tools`,
  `--strict-mcp-config` and `--json-schema`); the loop checks this and stops if older.
- You are on `main`, the working tree is clean, and `main` is up to date.
- Every `task/*` branch from an earlier run is merged or deleted (see "Stop messages").
- Gates you have checked are marked under their heading, e.g. `gate: G0 passed 2026-10-20`.

## Running it

```zsh
# what would run, without calling Claude or changing anything
uv run --no-project --python 3.12 python scripts/loop.py --dry-run

# run up to 3 tasks (the default), $8 budget per task (the default)
uv run --no-project --python 3.12 python scripts/loop.py

# one specific task, with a bigger budget, printing every command
uv run --no-project --python 3.12 python scripts/loop.py --task T1.5 --budget 5 --verbose
```

| Option | Meaning |
| --- | --- |
| `--max-tasks N` | Stop after N tasks (default 3) |
| `--task ID` | Run only this task (must be `auto`, unticked, dependencies ticked on `main`) |
| `--budget USD` | Spending limit per task across all its Claude calls (default 8) |
| `--dry-run` | Print the tasks that would run; no Claude calls, no git changes (it still reads `git status` and the branch list) |
| `--verbose` | Print every command the loop runs |

## What happens for each task

1. **Pick:** the next unticked `auto` task whose `depends` are all ticked **on `main`**. `pair`
   and `human` tasks are skipped; you do them yourself.
2. **Branch:** `git switch -c task/<ID> main`.
3. **Implement:** `claude -p` with `.loop/prompts/implement.md`, the task text, its verify
   command and the protected paths. Allowed tools: Read, Edit, Write, Grep, Glob and Bash for
   `make`, `uv`, `npm`, `npx`, `git status`, `git diff`. Nothing prompts; anything else is denied.
4. **Questions → mentor:** if Claude stops (`needs_human` or `blocked`) with questions, a
   read-only mentor session answers them (see "The mentor"). If none is escalated, the
   implementing session resumes with the answers (one correction round). Otherwise the task
   stops here.
5. **Protected paths:** every path changed on the branch (new files too) is checked against
   `.loop/protected.txt`. Any hit rejects the task.
6. **Verify:** the loop runs the task's `verify:` command itself. On failure it resumes the same
   Claude session with `.loop/prompts/fix.md` and the last 200 lines of output.
7. **Review:** a separate, read-only `claude -p` session (only Read, Grep, Glob) gets the diff and
   `.loop/prompts/review.md`. "changes_needed" sends the problems back to the implementing session.
8. Fix, review and mentor rounds share one limit: **3 correction rounds**, then the task is blocked.
9. **Approve:** the loop ticks the box, appends to `docs/loop/log.md` and
   `docs/loop/digest.md`, commits
   `"<ID>: <summary>"` on the branch and switches back to `main`.

## Stop messages

Every run ends with a line starting `STOP:`.

A parked task (blocked or rejected) does **not** end the run: its branch is kept, the tasks
that depend on it are skipped, and the next independent task runs. The run stops only for an
escalation (questions for you), Claude's usage limit, a gate, nothing left to run, or
`--max-tasks` (parked tasks count). The last line lists every task parked in the run; the exit
code is 1 when anything was parked.

| Message | Meaning | What to do |
| --- | --- | --- |
| `The working tree is not clean` | Uncommitted changes | Commit or stash them |
| `You are on '<branch>'. Switch to main first.` | Not on main | `git switch main` |
| `Claude Code X is too old` | Version below 2.1.295 | Update Claude Code |
| `Gate G<n> is not passed (...)` | Tasks after a gated section are waiting | Check the gate's criteria, then add `gate: G<n> passed <date>` under that heading on `main` |
| `T<x> needs T<y>, which is committed on unmerged branch task/T<y>` | A dependency is done but only on its branch; boxes are ticked on branches, so it does not count yet | Review and merge `task/T<y>`, then run again |
| `T<x> is committed on unmerged branch task/T<x>` | That task already has a branch | Merge it, or delete the branch to redo the task |
| `T<x> needs T<y>, a pair/human task` | You have to do T<y> yourself | Do it, tick it on `main`, run again |
| `No unticked auto tasks left.` | Nothing for the loop to do | |
| `reached --max-tasks N` | Normal end of a run | Review and merge the new `task/*` branches |
| `T<x> has questions for you` | The mentor escalated at least one question (or failed) | See "Answering questions" |
| `Claude's usage limit was reached during T<x>` | Your Claude account's session or usage limit; every later call would fail | Wait for the reset, delete `task/T<x>`, run again |
| `T<x> is parked on task/T<x>; continuing…` (not a stop) | Blocked (3 rounds, budget, no JSON answer) or rejected (protected path) | After the run: read the branch's last log row and WIP commit |
| `Parked in this run: …` | Summary line after any stop | Review each listed branch |

A stopped task's branch is kept with everything committed on it (`WIP <ID> (<status>): …`),
so `main` stays clean. Its log row and questions are in that commit.

## The mentor

`.claude/agents/mentor.md` is a read-only project mentor (model opus) that follows
`docs/decision-policy.md`: it decides routine questions (naming, step order, defaults,
choosing among existing reason codes) and escalates anything about verdicts, security
checks, scope, dependencies, gates or budget, and anything it is unsure about.

- The loop calls it with `.loop/prompts/mentor.md`, tools `Read,Grep,Glob`, and
  `.loop/mentor.schema.json` (`decision`, `rationale`, `escalate` per question). Its cost
  comes out of the task's budget.
- **Fails closed:** a failed call, a used-up budget, a wrong number of answers, a missing
  `escalate` flag or an empty decision escalates every question.
- **None escalated:** the task resumes with `.loop/prompts/answered.md` and the answers.
- **Any escalated:** the task stops. `questions.md` gets every question: escalated ones with
  an empty **A:** and the mentor's recommendation, the others pre-filled as
  `(mentor-default)`.
- Mentor decisions go to `docs/loop/digest.md` only, never to `docs/decisions.md` (D36, D39).
  When you merge a branch, copy its "Decided by the mentor" rows into `docs/decisions.md`
  with status `mentor-default`.

## The digest

`docs/loop/digest.md` has one `## <date>` section per day and one block per task: whether
its branch is ready for review, the mentor's decisions, and escalated questions. The loop
writes it only when a task finishes or is parked, like the log row. `.gitattributes` merges
`log.md`, `questions.md` and `digest.md` with `merge=union` (both sides kept), so parallel
task branches do not conflict there; after merging two branches from the same day you may
see the date heading twice. The union rule applies to merges made with `git` locally; if
GitHub's merge button reports a conflict in these files, merge the branch locally instead.

## Answering questions

1. `git switch task/<ID>` and open `docs/loop/questions.md`. The newest section lists the
   questions; escalated ones have an empty **A:** and the mentor's recommendation, and the
   others show the mentor's `(mentor-default)` answer.
2. Decide. Write each answer after its **A:**, and record agreed decisions in
   `docs/decisions.md` yourself (on `main`).
3. Then either delete the branch (`git switch main && git branch -D task/<ID>`) so the loop
   redoes the task with your decisions in place, or finish the task by hand on the branch.

## Protections

- **Protected paths** (`.loop/protected.txt`): `CLAUDE.md`, the spec, decisions, the
  decision policy, roadmap, style guide, `docs/phase1-tasks.md`, `.claude/**`, `backend/tests/ssrf/**`, `backend/tests/e2e/**`,
  `.loop/**`, `scripts/loop.py`, `.github/**`. Only the loop ticks task boxes, after verify
  and review pass.
- The loop runs the verify command itself; Claude's own claim of success is not trusted.
- `--permission-prompts none`: anything outside the allowed tools is refused without asking.
- No merge, no push, no `git commit` by Claude (the tool list does not allow it).
- **Read-only sessions are enforced, not requested:** the reviewer and the mentor run with
  `--tools Read,Grep,Glob` (no other built-in tool exists for them) and
  `--disallowedTools Bash,Edit,Write,NotebookEdit,WebFetch,WebSearch`. `--allowedTools` alone
  was not enough: Claude Code auto-approves read-only shell commands, and the T2.2 mentor ran
  `ls`/`grep`/`cat` that way (2026-10-19).
- **No MCP servers** in any loop session (`--strict-mcp-config`): connected services such as
  Notion or Drive could otherwise be written to.
- **A reply without the JSON answer** names its cause: "Claude usage limit reached: …" (stops
  the run) or "claude ended without the required JSON answer: …" (parks the task). T2.2's
  "claude did not finish: success" (2026-10-19) was the account's session limit; on
  2026-10-23 a weekly limit ("You've hit your weekly limit") was missed by the first pattern and
  is now recognised too (any "hit your … limit" text).
- Budget per task via `--max-budget-usd`, passing what is left of `--budget` to each call.
  This is a **soft** limit: Claude Code checks it between its own steps, so one call can go
  over (the first T1.5 run spent $4.82 of $3). The loop makes no new call once the budget is used.

## Files

| File | Purpose |
| --- | --- |
| `scripts/loop.py` | The loop (standard library only) |
| `scripts/tests/test_loop.py` | Unit tests with git and Claude faked: `make test-loop` |
| `.loop/prompts/implement.md`, `fix.md`, `review.md` | Prompts |
| `.loop/prompts/mentor.md`, `answered.md` | Mentor prompt; how its answers are handed back |
| `.loop/result.schema.json`, `review.schema.json`, `mentor.schema.json` | Structured output Claude must return |
| `.claude/agents/mentor.md`, `docs/decision-policy.md` | The mentor's role and rulebook (shared with interactive sessions) |
| `.loop/protected.txt` | Paths Claude must never change |
| `docs/loop/log.md`, `questions.md`, `digest.md` | Append-only records, written on task branches |

## Known limits

- Ctrl-C or a crash during a task parks it like any other stop (WIP commit, back to `main`).

- Verify commands that start with `cd` are run by the loop through `sh -c`; Claude itself runs
  the equivalent `uv --directory …` / `npm --prefix …` forms, because `cd` is not in its tool list.
- The review sees the diff against `main`; a very large diff makes the review call expensive.
- Log rows and questions reach `main` only when you merge the task's branch.
