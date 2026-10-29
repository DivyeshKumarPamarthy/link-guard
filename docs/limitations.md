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
| Homoglyphs in file names are not flagged; Unicode category `Cf` includes `ZWJ`/`ZWNJ` (D72) | Legitimate Indic or emoji filenames containing `U+200C`/`U+200D` may trigger `EXT_SPOOFED_NAME` | — |

## Current implementation (Phase 1 = Phases A + B state)

| Limitation | Effect | Planned |
| --- | --- | --- |
| Scan tasks run in-process on the API event loop (`InProcessExecutor`) | If the server process is killed mid-scan, `queued`/`running` rows are not resumed on restart | Container runner in Phase E |
| SQLite calls are synchronous inside async code | Each write briefly blocks the event loop (milliseconds on a local file) | Acceptable for Phase 1 |
| No migrations tool (D14) | If the `scans` table changes, delete the local `.db` file | — |
| FastAPI's `/docs` page loads Swagger UI from a CDN | API docs don't open with Wi-Fi off; take report screenshots while online | Self-host the assets if needed for the demo |
| Demo `/reset` prints an exception traceback in the demo server's terminal | Expected: it is how the server drops the connection on purpose | — |
| Compression other than gzip/deflate (br, zstd, stacked or corrupt) is not decoded (D61) | Such files are "Unable to verify" | — |
| Only the first validated address of a host is tried | If it is down, the scan is "Unable to verify" rather than trying the next address | — |
| HEAD is sent with `Connection: close` (D52) | One extra connection (and TLS handshake) per hop | — |
| ASCII host names may only use letters, digits, `-`, `_` and `.` | A rare but valid name with other characters is refused as `URL_INVALID` | — |
| Only query values and userinfo passwords are redacted by `safe()` | A secret embedded inside a URL *path* (`/share/<token>/file`) is not redacted in logs | — |
