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

### T1.4 · task/T1.4 · interactive session (pair task)

Decided by the mentor:

| Question | Decision | Rationale |
| --- | --- | --- |
| Which responses are redirects? | 301/302/303/307/308 with a non-empty Location; anything else is final (D45) | Fetch standard's redirect statuses |
| Order of checks per hop? | urljoin, drop fragment, too-many, unsupported/bad scheme, loop, then check_target (D46) | Cheapest first; nothing contacted before the pure checks |
| Codes for refusals at a hop? | private → SSRF_BLOCKED_AT_HOP; invalid/scheme → REDIR_BAD_TARGET; port/userinfo keep their codes; DNS → FETCH_DNS_ERROR (D47) | Honest messages; choosing among existing codes |
| Hop records and numbering? | One record per checked URL; refused = blocked/null status; hop n = n-th redirect (D48) | Every record states what happened |
| Downgrade / long chain / cross-domain? | Reported whenever they happened, even if the chain stops (D49) | True facts; cannot make a result Safe |
| Redirect to a .torrent URL? | Unsupported, never contacted; shared `unsupported_link_kind()` (D50) | Same answer as pasting the torrent link |

Escalated, answered by Divyesh (2026-10-21):

- SSRF rows at a redirect hop and the `tests/demo_server.py` layout approved; D45–D50 upgraded to decided
- Changes: hosts compared in ASCII form (D49); `REDIR_BAD_TARGET` message reworded (D51); new rows for `//127.0.0.1/`, an over-long `Location` and two different `Location` headers
## 2026-10-19

### T1.6 · task/T1.6 · ready for review
