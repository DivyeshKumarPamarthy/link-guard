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
| "Safe" means "nothing disguised was found", not "harmless to run" | The whole file was read and its name, headers and real type agree. A genuine program or script (`.exe`, `.elf`, `.bat`, `.ps1`, `.js`) is "Safe"; the report adds the info reason `TYPE_IS_PROGRAM` ("This file is a program. LinkGuard checks that a file is what it claims to be, not what a program does when run.", D86). A Windows program whose name has an extension in none of the mismatch tables, or no extension (`photo.svg`, `index.html`, `download`), gets the same info reason but still no mismatch: an unknown claim is "no signal" (D68). Installers and archives that carry programs (`.msi`, `.jar`, `.apk`, `.zip`) get no such reason | — |
| Each hop is asked twice: HEAD, then GET (D52) | A single-use (one-time) download link can be used up by LinkGuard's own requests: the HEAD may consume it before the body is read, and the scan may consume it before the user downloads the file | — |

## Current implementation (Phase 1 = Phases A + B state)

| Limitation | Effect | Planned |
| --- | --- | --- |
| Scan tasks run in-process on the API event loop (`InProcessExecutor`) | If the server process is killed mid-scan, `queued`/`running` rows are not resumed on restart: they stay `running` for ever. The web app stops polling after 3 minutes (`MAX_POLL_TOTAL_MS`, D83) and shows the server-error screen | Container runner in Phase E |
| SQLite calls are synchronous inside async code | Each write briefly blocks the event loop (milliseconds on a local file) | Acceptable for Phase 1 |
| No migrations tool (D14) | If the `scans` table changes, delete the local `.db` file | — |
| FastAPI's `/docs` page loads Swagger UI from a CDN | API docs don't open with Wi-Fi off; take report screenshots while online | Self-host the assets if needed for the demo |
| Demo `/reset` prints an exception traceback in the demo server's terminal | Expected: it is how the server drops the connection on purpose | — |
| Compression other than gzip/deflate (br, zstd, stacked or corrupt) is not decoded (D61) | Such files are "Unable to verify" | — |
| Only the first validated address of a host is tried | If it is down, the scan is "Unable to verify" rather than trying the next address | — |
| HEAD is sent with `Connection: close` (D52) | One extra connection (and TLS handshake) per hop | — |
| ASCII host names may only use letters, digits, `-`, `_` and `.` | A rare but valid name with other characters is refused as `URL_INVALID` | — |
| Only query values and userinfo passwords are redacted by `safe()` | A secret embedded inside a URL *path* (`/share/<token>/file`) is not redacted in logs | — |
| The web app's recent-scans list keeps each full pasted URL (query string included) in this browser's `localStorage` (T3.2, P1) | A signed link's secret stays on this computer until the list is cleared; it is never sent anywhere or shown to others | — |
| uvicorn's own error logs may include tracebacks with remote data | Possible secrets in the terminal on an unexpected crash. T3.5's log test uses the test client, so it does not cover what real uvicorn prints | — |
| Generated archives (7z, RAR4, RAR5, OLE) are empty, the Mach-O sample is a header only, the MP4 has no `moov` box | They prove the detector, not that real tools open them; checked against the format specifications and our own tests, not with 7-Zip, unrar or Office | — |
| The web tests use hand-written results (`web/src/test/fixtures.ts`), not results captured from the real backend | A difference between a fixture and real backend output would not be caught by the web tests; the generated types only catch a changed field name or type | — |
| The sample hash is pinned in `demo/tests/test_make_samples.py` | Any intentional change to the generator must update `EXPECTED_MANIFEST_SHA256` | — |
| Verified on macOS (Apple Silicon) only | Windows/Linux setup not yet tried by the team | T4.5 fresh-machine check |
| A ZIP whose subtype is unconfirmed never raises `TYPE_MISMATCH_OTHER` (D69) | A large (partial-scope) ZIP named `.pdf` gets no name mismatch; the Content-Type check still runs | Tail read of the ZIP directory in Phase D |
| Mismatch tables cover common extensions and media types only | An extension or Content-Type in no table is "no signal", never a mismatch | Add rows when needed |
