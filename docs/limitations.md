# Known limitations

Keep this current: every module note's "Known limitations" section feeds it, and report
chapter 7 is written from it. "Planned" names the task or phase that changes it.

## By design (Phase 1 scope)

| Limitation | Effect | Planned |
| --- | --- | --- |
| Only the first 5 MB are read (`LG_HEAD_FETCH_BYTES`) | Anything hidden later in a large file is not seen; such scans show "No issues found in the checked part", never plain "Safe" | Tail reads in Phase D |
| Detection compares signatures (magic bytes) only | No behavioural analysis, no malware signatures, no look inside archives, PE, PDF or Office files | Phases D–E |
| Only the formats in the spec §7 table are recognised (D15: final list) | Other formats are reported as unknown type | — |
| Cloaking servers | A server can send LinkGuard a clean file and a browser a different one | Documented only |
| Web pages are not followed | HTML/JS redirects and download buttons on pages are not followed; the result is "Unable to verify" | — |
| `magnet:`, `ftp:` and `.torrent` links | Reported as "Not supported yet" | Torrent files in Phase D |
| No accounts, history API, caching or rate limits (D17) | Every scan is fresh; anyone who can reach the API can use it, which is why it is localhost-only (D18) | — |
| Any website the user visits can call the local API (CORS `*`) | See `threat-model.md`, residual risks | Revisit in Phase C |
| Scan results are stored with no retention, including full input URLs | Signed-URL secrets stay in the local `linkguard.db`; delete the file to clear it | — |

## Current implementation (Phase A state)

| Limitation | Effect | Planned |
| --- | --- | --- |
| Scans run on the `MockExecutor` | Every scan returns the same fixed UNSAFE result after 300 ms | Real executor in T2.4 |
| No concurrency limit or busy guard yet | Unlimited background scans; no 503 | T2.4 |
| SQLite calls are synchronous inside async code | Each write briefly blocks the event loop (milliseconds on a local file) | Acceptable for Phase 1 |
| No migrations tool (D14) | If the `scans` table changes, delete the local `.db` file | — |
| uvicorn's own error logs may include tracebacks with remote data | Possible secrets in the terminal on an unexpected crash | T3.5 |
| docker-compose not written yet; bind address inside a container is open (D31) | `make dev` is a stub | T2.5 |
| FastAPI's `/docs` page loads Swagger UI from a CDN | API docs don't open with Wi-Fi off; take report screenshots while online | Self-host the assets if needed for the demo |
| Demo endpoints `/disguised`, `/cd/{variant}` and `/index` not built yet | Rows needing disguised samples or Content-Disposition variants can't run yet | T1.5 / T2.6 |
| Demo `/reset` prints an exception traceback in the demo server's terminal | Expected: it is how the server drops the connection on purpose | — |
| Verified on macOS (Apple Silicon) only | Windows/Linux setup not yet tried by the team | T4.5 fresh-machine check |
