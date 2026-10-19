The loop checked your work on this task and it is not finished yet. The details are below:
either the verify command failed (its output is included) or the reviewer listed problems.

- Fix the code, not the tests. Do not weaken, skip or delete tests, and do not change the
  verify command, Makefile targets or test configuration to make the check pass.
- If a test itself is wrong because it contradicts the spec or a decision, do not change
  it: return status `needs_human` and explain the conflict in `questions`.
- All rules from the first message still apply (protected paths, no decisions.md or
  phase1-tasks.md edits, no `cd`, no commits).

Return the same JSON object as before: `status`, `summary`, `files_changed`, `questions`.
