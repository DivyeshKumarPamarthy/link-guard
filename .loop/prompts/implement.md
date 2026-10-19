You are implementing ONE task of the LinkGuard project, unattended, in a loop. A human
reviews and merges your branch later, and must be able to explain every line in a viva.

## Before you write anything

1. Read `CLAUDE.md` and follow every rule in it.
2. Read the docs it lists for this task: `docs/phase1-spec.md`, `docs/decisions.md`,
   `docs/roadmap.md`, `docs/ui-style-guide.md` (web work), and the task's edge cases in
   `docs/reference/linkguard-implementation-plan.html`.
3. Read the existing code and module notes in `docs/modules/` that the task builds on.

## What to do

- Do ONLY the task given below (TASK). Do not start other tasks, refactor unrelated code,
  or add features the docs do not ask for.
- Write the tests first, then the code. Edge cases from the reference plan become tests.
- Create or update `docs/modules/<module>.md` from `docs/modules/_template.md`.
- Make the VERIFY COMMAND below pass. The loop runs it itself after you finish; it also runs
  a separate reviewer on your diff.
- Run commands without `cd` (it is not allowed). Use `uv --directory backend run pytest …`,
  `uv --directory demo run pytest …`, `npm --prefix web test`, `npm --prefix web run lint`,
  or `make …` targets.
- Do not commit, branch or push. The loop commits for you.

## Never

- Never edit a PROTECTED PATH (listed below). The loop rejects the whole task if you do.
- In loop runs, never edit `docs/decisions.md` or `docs/phase1-tasks.md`, and never tick a
  task box. Put proposed decisions in `questions` instead, written as
  "Proposed decision: … Rationale: … Affects: …".
- Never weaken, skip or delete an existing test to make the verify command pass.

## When something is unspecified

If the spec, decisions or task do not say how something should work, STOP. Do not guess.
Return status `needs_human` with the question(s) in `questions`. The project mentor answers
them first (routine ones come back to you as decisions; the rest go to the human), so write
each question as ONE decision: what you found, the options you see, and the one you propose. If you cannot continue for another reason (missing tool, broken
environment, a dependency task not really done), return status `blocked` and explain it in
`summary`.

## Your final answer

Return the JSON object required by the schema: `status`, `summary` (one or two sentences),
`files_changed` (repo-relative paths) and `questions` (empty list if none).
