# Loop digest

Append-only. One `## <date>` section per day. Under it, one block per task the loop finished
or stopped (written on the task's branch by `scripts/loop.py`), and one block per mentor
decision taken in an interactive session. Each block lists:

- **Decided by the mentor:** question, decision, rationale (copy these into
  `docs/decisions.md` as `mentor-default` rows when you merge the branch);
- **Escalated:** questions waiting for you in `docs/loop/questions.md`;
- the branch and whether it is ready for review.

See `docs/decision-policy.md` and `docs/loop/README.md`, "The mentor".

## 2026-10-20

### T1.3 · task/T1.3 · interactive session (pair task)

Decided by the mentor:

| Question | Decision | Rationale |
| --- | --- | --- |
| httpx reuses a pooled connection verified for another host on the same IP: how to prevent it? | One `httpx.AsyncClient` per hop, closed after the hop (D41) | Safety first and simplest to explain: one hop, one client, one certificate check; also keeps cookies from crossing sites |
| Code shape of `fetcher/pinned.py`? | `tls_context`, `new_client`, `build_pinned_request` (no I/O; T2.1 streams it) (D42) | Small testable functions (CLAUDE.md); TLS setup testable without a network |

Escalated, answered by Divyesh (2026-10-20):

- Test harness: approved as D44 (subprocess on 127.0.0.1 only, `integration` marker, demo `uv sync` in CI)
- Recording: D43 decided, with one change: CAs from `certifi`, never the system store. D41 and D42 upgraded to decided
