# Loop digest

Append-only. One `## <date>` section per day. Under it, one block per task the loop finished
or stopped (written on the task's branch by `scripts/loop.py`), and one block per mentor
decision taken in an interactive session. Each block lists:

- **Decided by the mentor:** question, decision, rationale (copy these into
  `docs/decisions.md` as `mentor-default` rows when you merge the branch);
- **Escalated:** questions waiting for you in `docs/loop/questions.md`;
- the branch and whether it is ready for review.

See `docs/decision-policy.md` and `docs/loop/README.md`, "The mentor".
