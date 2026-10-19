# Decision policy: what the mentor decides and what goes to Divyesh

The mentor (`.claude/agents/mentor.md`) answers routine project questions so work does not
stop for them. This file is its rulebook. A question that matches **ALWAYS ESCALATE** goes to
Divyesh, even if it also matches **DECIDE ALONE**. When in doubt, escalate.

Every mentor decision is recorded: as a `mentor-default` row in `docs/decisions.md` (by the
session that asked, or at merge for loop runs) and in `docs/loop/digest.md`. A
`mentor-default` stands until the team confirms or changes it.

## DECIDE ALONE

| Kind of question | Example from this project |
| --- | --- |
| Spec gaps resolved consistently with CLAUDE.md principles: honesty (missing evidence never means safe), safety first, the simplest explainable option | A fetch fails in a way the spec does not name → `UNABLE_TO_VERIFY`, never `SAFE` |
| Default values for tunables (recorded with status `default`), except scoring weights and verdict thresholds | `LG_TEXT_SAMPLE_BYTES=4096` (D37) |
| Choosing among existing reason codes | A zone ID in an IPv6 host → `URL_INVALID` rather than `URL_PRIVATE_ADDRESS` (D38) |
| Naming | Function, module, test and config-variable names |
| Test layout | Which file a test lives in; parametrised table vs separate tests |
| Step order within a task | Implement T1.2 as parsing → host → resolvers → classification |
| Commit structure | One commit per step, or one per task |
| Small additions consistent with existing decisions | One more `detected_type` name following D37's pattern |

## ALWAYS ESCALATE

| Kind of question | Why |
| --- | --- |
| Changing what a verdict or status means, or when "Safe" is shown | The honesty rules are the product |
| Scoring weights, verdict thresholds, hard rules (`hard_min_verdict`) | They decide when "Safe" is shown |
| A new reason code, or changing a code's `outcome` | Changes what users are told (see D38) |
| Anything touching the contract (API models, OpenAPI, web types) | CLAUDE.md: bump nothing silently |
| Weakening or removing any security check, SSRF or e2e row, or a protected file | Safety first; protected files are listed in `.loop/protected.txt` |
| New features, new dependencies, or cutting Must Have scope | Scope is set by `docs/roadmap.md` |
| Gates (`gate: G<n> passed`) | The team checks the gate criteria |
| Merging `pair` task branches | Divyesh pairs on these and merges them |
| Spending over a task's budget | Money is Divyesh's call |
| Two principles conflict, or the mentor's confidence is low | Exactly the cases a human should judge |

## Always shown to Divyesh, whatever the mentor says

- New or changed security tests (SSRF, e2e), **before** implementing against them.
- The end of every task.
