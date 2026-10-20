# LinkGuard threat model (Phase 1)

One page. Scope: the backend, web app and demo server running on one laptop (decision D18).
Revisit before any public deployment, the Chrome extension (Phase C) or reputation lookups (Phase E).

## Assets

| Asset | Why it matters |
| --- | --- |
| The user's machine and local network | The backend makes outbound requests. If it can be steered to `127.0.0.1`, `10.x`, `169.254.169.254` or other internal addresses, it becomes a proxy into places the attacker cannot reach (SSRF). |
| The honesty of the verdict | Users act on it. A wrong "Safe" is worse than no answer. |
| Submitted URLs | Signed URLs carry secrets in their query strings (`?token=`, `X-Amz-Signature=`). |
| The developer's terminal and logs | Hostile text in logs can forge lines, hide text or leak secrets. |
| The repository | Secrets committed by mistake are public: the repo is public. |

## Attackers

1. **Malicious link author** (main attacker). Controls the server behind the link: the file, the headers, the filename, redirects, DNS answers and timing.
2. **Any website the user visits.** The API is anonymous, has open CORS (D17) and listens on `127.0.0.1:8000`, so JavaScript on any page can submit scans and read their results.
3. **A teammate's mistake.** Committed secrets, a port published on all interfaces, a demo exemption left on in dev.

## Threats and mitigations

| Threat | Mitigation | Where |
| --- | --- | --- |
| **SSRF**: link or redirect points at an internal address, written as decimal/octal/hex/IPv6/IPv4-mapped forms, or via DNS answers | Real URL parser; only `http`/`https`, no userinfo, port allow-list; strict IP-literal parsing; resolve then classify **every** address with `ipaddress.is_global` (IPv4-mapped judged by the IPv4 part); reject if any address is non-public; checks repeated on **every redirect hop**; only the fetcher may make outbound connections | `engine/fetcher` (T1.2, T1.4) |
| **DNS rebinding**: first lookup public, second private | Resolve once per hop and connect to the validated IP (pinned), with SNI and certificate checked against the original hostname; one HTTP client per hop so no connection verified for one host is reused for another (D41, D43) | `engine/fetcher/pinned.py` (T1.3) |
| **Demo exemption abused** | Exemptions are exact `host:port` pairs, accepted only in the `test`/`demo` profiles; startup fails in `dev`/`prod`; each active exemption is logged as a WARNING | `core/config.py` (T0.2) |
| **Resource exhaustion (DoS)**: huge files, slow-drip servers, endless redirects, big request bodies, many scans | 5 MB byte cap counting bytes actually read; total deadline and minimum throughput; max 5 redirects with loop detection; 8 KB request body limit (413); 4 concurrent scans and 503 above 20 waiting | T2.1, T1.4, T0.7, T2.4 |
| **Code execution from downloaded bytes** | Bytes are never executed, imported, written to a path derived from remote data, or decompressed beyond caps; detection only compares bytes with signatures | All engine code |
| **XSS** via filenames, URLs or headers shown in the web app | React escaping only; no `dangerouslySetInnerHTML`; scanned URLs are never clickable; control and bidi characters shown escaped | Web app (T1.6, T3.2) |
| **Log injection and secret leaks** | `safe()` strips ANSI escapes, control and bidi characters and redacts URL query values and passwords; errors are logged as type + `safe(message)`, never raw tracebacks (D30); body bytes are never logged; responses never contain stack traces | `core/log.py` (T0.3), `api/errors.py` |
| **Dishonest verdicts** (bug turns "couldn't check" into "safe") | Missing evidence → UNABLE_TO_VERIFY; the contract refuses a plain SAFE for partial or low-confidence scans and any outcome before `done`; executor failures become `ANALYSIS_ERROR` | `contract/models.py` (D29), scorer (T2.3) |
| **Backend reachable from other machines** | Binds `127.0.0.1` by default; compose publishes `127.0.0.1:…` only (CI check in T2.5) | T0.7, T2.5 |
| **Committed secrets** | Config from environment only; `.env` gitignored, `.env.example` committed; gitleaks in CI | T0.1, T0.8 |

## Residual risks (accepted for a localhost academic demo)

- **Any website can use the local API.** Because CORS is `*` (D17), a page the user visits can make LinkGuard fetch public URLs from the user's IP and read the results. SSRF checks still apply, so it cannot reach internal addresses through LinkGuard. Restricting CORS to the web app's origin (and later the extension's) would close this; revisit in Phase C.
- **Pinned TLS fallback: not needed.** T1.3 proved the preferred approach (D43), so no rebinding window remains between the check and the connection.
- **Cloaking.** A server can send LinkGuard a clean file and the browser a malicious one. The honest user agent makes this easy for an attacker; documented as a limitation.
- **Signed URLs are stored.** Full input URLs, secrets included, sit in the local SQLite file without retention (D17). They are redacted in logs only.
- **uvicorn's own error logging** may still print tracebacks with remote data to the terminal; reviewed in T3.5.
