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

## 2026-10-21

### T2.3 · task/T2.3 · stopped (blocked): claude did not finish: error_max_budget_usd

## 2026-10-21

### T2.1 · task/T2.1 · interactive session (pair task)

Decided by the mentor:

| Question | Decision | Rationale |
| --- | --- | --- |
| Proposed decision: the verdict thresholds come from config as LG_SUSPICIOUS_SCORE=30 and LG_UNSAFE_SCORE=60 (both inclusive). Startup fails unless the suspicious threshold is below the unsafe one. score_scan() receives them as a Thresholds value, so the scorer stays pure. The other option was a `thresholds` key in reason_codes.yaml, which would version them with rules_version but changes the registry loader and its two-top-level-keys test. Rationale: CLAUDE.md requires tunable numbers to come from config or the registry; this follows the D23/D37 precedent with no loader change. Affects: T2.3, T2.4, config. | Approved. Keep LG_SUSPICIOUS_SCORE=30 and LG_UNSAFE_SCORE=60 in config, both inclusive. Startup fails unless suspicious < unsafe, and the scorer receives them as a Thresholds value. Do not add a `thresholds` key to reason_codes.yaml. The values must stay exactly as spec §9 gives them; any change to them goes to Divyesh. Record this in decisions.md as mentor-default, with a note that the threshold values are spec-fixed and not a default. | Only where the numbers live is decided here, not their values. CLAUDE.md says tunables come from config, and D23/D37 set that pattern, so no loader change is needed. The policy escalates changes to threshold values, and 30/60 stay unchanged from spec §9. |
| Proposed decision: the headline of an UNABLE_TO_VERIFY result comes only from `unable` codes, extending D49 (rejected and unsupported results keep their own headline). Example: for REDIR_LOOP + REDIR_CROSS_DOMAIN the headline is 'The link redirects in a loop', not the cross-domain one that alphabetical order would pick. Example: for FETCH_TIMEOUT + EXT_RISKY (score 15) the headline is the timeout one. SAFE, SUSPICIOUS and UNSAFE use the top reason as spec §3 says. NO_ISSUES always uses 'No issues found in the checked part ({label})'. Rationale: the headline should explain the verdict shown. Affects: T2.3, web report. | Approved. For UNABLE_TO_VERIFY, the headline is the top `unable` code, ranked by weight, then severity, then code alphabetically. Rejected and unsupported results keep their own headline (D49). SAFE, SUSPICIOUS and UNSAFE use the top reason across all codes. NO_ISSUES always uses the scope template. All reasons stay in `reasons`. Keep the REDIR_LOOP+REDIR_CROSS_DOMAIN and FETCH_TIMEOUT+EXT_RISKY golden cases. | This extends D49 and fills a gap in spec §3 by following the honesty rule: the headline must explain the verdict actually shown. A risky-extension headline above an UNABLE verdict would mislead. The verdict and the reasons list do not change. |
| Proposed decision: scope labels are 'Whole file checked (47 KB)'; 'First 5 MB of 200 MB'; 'First 4 KB (total size unknown)'; '3 KB read, but sent compressed' (unexpected encoding); 'Only the server's headers were read' (metadata-only); 'Nothing was read' (none, the same text the web fixtures already use). Sizes use 1024-based units with integer KB and one decimal for MB and GB. The label goes into the NO_ISSUES headline unchanged, which gives '(First 5 MB of 200 MB)' with a capital F; the wireframe draft shows lowercase. Rationale: the spec only gives the full-scope example. Affects: T2.3, web report. | Approved as proposed: 1024-based units, integer KB, one decimal for MB and GB. Put the label into the NO_ISSUES headline unchanged, capital letter included, exactly as spec §3's {scope.label} template says. Update the wireframe draft in ui-style-guide.md so its example matches; don't lower-case the label in code. The label text is a string value, so the contract schema doesn't change. | This is wording within a spec gap, and the simplest explainable option is one label string used everywhere. The spec template wins over a wireframe draft. |
| Proposed decision: a reason code missing from the registry is scored with weight 0 and counted as an `unable` outcome, so it can never produce SAFE. Its message is generic and names the code. It is returned in ScoreOutcome.unknown_codes, and the orchestrator calls log_unknown_codes() to write the ERROR log, so score_scan() itself does no I/O. A missing evidence key renders as 'unknown' instead of crashing. Rationale: spec §9 says weight 0, ERROR log, no crash, but gives no outcome; the honesty rule says missing evidence is never safety. Affects: T2.3, T2.4. | Approved. An unknown code scores weight 0 and counts as `unable`, so it can never produce SAFE. It gets a generic message that names the code and goes into ScoreOutcome.unknown_codes. The orchestrator (T2.4) calls log_unknown_codes() to write the ERROR log, so score_scan() stays pure. A missing evidence key renders as 'unknown'. The registry-completeness test still fails on any code that is used but not registered, so this path only runs if there is a bug. | This is the policy's own DECIDE ALONE example: a spec gap resolved by 'missing evidence is never evidence of safety'. It keeps spec §9's weight 0, ERROR log and no crash, and the scorer stays pure as CLAUDE.md requires. |
| Proposed decision: the scorer's input is ReadFacts(bytes_read, total_size, range_supported, ended, headers_only). It mirrors the FetchResult fields in spec §5 plus a `headers_only` flag, needed because spec §3 metadata-only (body deliberately not read) cannot be told apart from none (0 bytes) using FetchResult alone. If both a rejected and an unsupported code are present, the status is rejected. It reuses the existing Finding dataclass from engine/fetcher/redirects.py. Rationale: T2.1 and T2.4 must produce this shape. Affects: T2.1, T2.4. | Approved. ReadFacts(bytes_read, total_size, range_supported, ended, headers_only) is the scorer's input. It must be a plain dataclass or Pydantic model with JSON-compatible fields, because it crosses the executor seam. When both a rejected and an unsupported code are present, the status is rejected. Reusing the existing Finding dataclass is fine. T2.1 and T2.4 must produce this shape. Note it in decisions.md and in the scoring module note. This is internal, not the API contract. | headers_only is needed to tell spec §3's metadata-only scope apart from none. Rejected wins because safety comes first: the target was unsafe to contact. It keeps the executor output plain JSON as the CLAUDE.md architecture requires, and the API models are untouched. |

### T2.3 · task/T2.3 · finished by hand (2026-10-21, interactive session)

The parked work passed its verify command; review fixes: scope full only for a known length
(D54), thresholds in their own validator plus a startup log and a spec-value test (D62), the
scope-label example moved to `docs/ui-style-guide.md` (D64). The 5 decisions above are D62–D66;
T2.2's 9 decisions are recorded as D67–D75 so the T2.2 rerun follows them.
| HEAD fallback? | HEAD, then always one GET with Range (trusted); HEAD redirects followed without GET (D52) | Plan M2: trust the GET |
| Web page before the body? | Checked on the GET's headers; the fetcher adds LINK_IS_WEB_PAGE, metadata-only (D53) | A metadata-only result must never score Safe |
| Range handling and full scope? | 206 + valid Content-Range starting at 0; full only when bytes read equal a known length (D54) | Spec §3; under-claim when unsure |
| How is the cap counted? | Raw bytes actually read; Content-Length never trusted (D55) | Plan M2 |
| gzip/deflate bodies? | Decoded, never past the cap; FETCH_UNEXPECTED_ENCODING; partial (D56) | D10; decompression bombs |
| Error statuses and 429? | 401/403 auth, 429 one short retry, others HTTP error (D57) | Spec §8; no retry loop |
| Timeouts? | Total deadline + min throughput after a 5 s grace; bytes kept (D58) | C1, row 14 |
| Errors without a status? | FETCH_INTERRUPTED; TLS by exception chain; FETCH_EMPTY for 0 bytes (D59) | Honest messages |
| Headers, timings, test layout? | Whitelist from the trusted response; `fetch`/`first_byte`; integration + helper tests (D60) | Spec §5 |

Escalated, answered by Divyesh (2026-10-21):

- `FETCH_UNSUPPORTED_ENCODING` approved (D61); the two config variables added to spec §4; D52, D53, D55–D60 upgraded to decided
- D54 changed: a chunked body that ends cleanly (terminating chunk) is the whole file; a body read until close with no length stays partial
- Module note: T3.1 must reuse the fetcher's web-page check and never add `LINK_IS_WEB_PAGE` twice

## 2026-10-24

### T2.2 · task/T2.2 · stopped (blocked): review failed: claude did not finish: error_max_budget_usd
