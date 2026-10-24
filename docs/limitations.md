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
| Generated archives (7z, RAR4, RAR5, OLE) are empty, the Mach-O sample is a header only, the MP4 has no `moov` box | They prove the detector, not that real tools open them; checked against the format specifications and our own tests, not with 7-Zip, unrar or Office | — |
| The report's "every field" test uses a hand-written row-9 result | Until the real executor exists, a mismatch between it and real backend output would not be caught by the web tests | Captured result in T3.2 (after T2.4) |
| The sample hash is pinned in `demo/tests/test_make_samples.py` | Any intentional change to the generator must update `EXPECTED_MANIFEST_SHA256` | — |
| Demo `/reset` prints an exception traceback in the demo server's terminal | Expected: it is how the server drops the connection on purpose | — |
| The fetcher is complete (T1.2–T2.1) but scans still run on the `MockExecutor` | No real scan contacts a URL yet | T2.4 (executor) |
| Compression other than gzip/deflate (br, zstd, stacked or corrupt) is not decoded (D61) | Such files are "Unable to verify" | — |
| Only the first validated address of a host is tried | If it is down, the scan is "Unable to verify" rather than trying the next address | — |
| HEAD is sent with `Connection: close` (D52) | One extra connection (and TLS handshake) per hop | — |
| ASCII host names may only use letters, digits, `-`, `_` and `.` | A rare but valid name with other characters is refused as `URL_INVALID` | — |
| Verified on macOS (Apple Silicon) only | Windows/Linux setup not yet tried by the team | T4.5 fresh-machine check |
