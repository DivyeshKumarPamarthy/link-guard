# Report outline and viva question bank

Fill this as the project progresses: each finished module adds its notes from `docs/modules/`.
Adjust chapter names to your college's report template.

## Chapters

1. **Introduction**: problem (disguised downloads, shortened links hide malware), objectives, scope (Must / Should from `roadmap.md`), what is out of scope and why.
2. **Literature survey / existing systems**: VirusTotal (judges known files, needs upload or hash), Chrome Safe Browsing (reputation of URLs/files), URL expanders (show destination, no file check). Table: feature × system, ending with the gap LinkGuard fills (structure-based, explained, before download).
3. **Requirements**: functional (paste link, verdict with reasons, redirect chain, extension pause/allow/block); non-functional (never executes files, offline demo, honest verdicts, response time on local demo).
4. **System design**: architecture diagram, data flow of one scan, API contract, verdict rules (Safe / Suspicious / Unsafe / Unable to verify, partial scans), threat model (`threat-model.md`), UI design (wireframes, style guide).
5. **Implementation**: one section per module from `docs/modules/` (router, safe fetcher, detector, verdict engine, API, web app, extension, then D/E modules if built).
6. **Testing and results**: test strategy, SSRF test table, acceptance matrix output, results table (caught / missed / false alarms / median scan time), screenshots.
7. **Limitations and future work**: partial reads, cloaking, no behavioural analysis, format list; ideas from `roadmap.md`.
8. **Conclusion**.
- References; Appendix: API docs (FastAPI `/docs` screenshots), user guide, setup guide.

State the use of AI coding tools as your college policy requires (decision D21).

## Draft notes for chapters 1–2 (T0.11)

*Draft notes by Claude Code (2026-10-17), not report text. The team rewrites these in its own
words. Every claim about another system is marked **[VERIFY + cite]** and needs a source from
the official documentation or a paper before it goes in the report.*

### Chapter 1: Introduction

**Problem statement (one paragraph to write).** People download files from links they find in
chats, forums and emails. Two tricks make this risky: (1) the file is not what its name says
(a Windows program named `movie.mp4`, or `invoice.pdf.exe`), and (2) shortened or redirecting
links hide where the download really comes from. Checking a file usually means downloading it
first, and existing tools mostly answer "is this file or site already known to be bad?". They
say little about *why*, and little about files nobody has reported yet.

**Objectives (Phases A–B, this semester).**
1. Check a public download link *before* the user downloads it, by reading only the response
   headers and the first bytes (at most 5 MB).
2. Identify the file's real type from its signature (magic bytes) and flag mismatches with the
   claimed name, extension and Content-Type.
3. Follow redirect chains safely and show every hop.
4. Never let the checker itself be abused to reach internal network addresses (SSRF).
5. Give an honest, explained verdict (Safe / Suspicious / Unsafe / Unable to verify) with
   reasons and a statement of how much of the file was read.
6. A polished web app that runs fully offline for the demo.

**Scope.** Must: Phases A, B, C, F; Should: D, E (from `roadmap.md`). Out of scope this
semester: the Chrome extension, torrent/ZIP inspection, reputation lookups, containers.
Out of scope entirely: running files, malware signatures, YARA, user accounts. Say *why* for
each (time, safety, focus on the explainable core).

### Chapter 2: Existing systems (literature survey outline)

| Feature | VirusTotal | Google Safe Browsing / Chrome download protection | URL expanders (e.g. unshorten-style sites) | LinkGuard |
| --- | --- | --- | --- | --- |
| Main question answered | Do known engines flag this file or URL? [VERIFY + cite] | Is this URL/file on a known-bad list or of bad reputation? [VERIFY + cite] | Where does this short link lead? | Is this file what it claims to be, and is the link safe to fetch? |
| Needs the file first | For file scans, an upload or a hash lookup [VERIFY + cite] | Works in the browser during/after download [VERIFY + cite] | No | No: reads headers and first bytes only |
| New, never-reported files | Depends on engine detections [VERIFY + cite] | Reputation may be unknown [VERIFY + cite] | Not checked | Structural check works without prior reports |
| Explains why | Engine names and labels [VERIFY + cite] | Short warning [VERIFY + cite] | Shows destination only | Reason list, claimed-vs-actual bytes, redirect chain |
| Privacy | Uploaded files may be shared with security partners [VERIFY + cite: check VirusTotal terms] | Hash-prefix lookups designed for privacy [VERIFY + cite] | URL sent to the service | Runs locally; nothing leaves the laptop in Phases A–B |
| Checks the file type | Yes, as part of analysis [VERIFY + cite] | Not described publicly in detail [VERIFY] | No | Yes, core feature |

**The gap LinkGuard fills (closing paragraph).** A local, explainable, *structure-based* check that
works before download and without relying on someone having reported the file, plus honest
reporting of what could not be checked. LinkGuard complements reputation services; it does not
replace them (Phase E adds a reputation lookup as one more signal).

**Sources to find (team task).** VirusTotal documentation and terms of service; Google Safe
Browsing API documentation and the Chrome download-protection description; one or two papers on
file-type identification by magic bytes; OWASP SSRF Prevention Cheat Sheet; one survey on
URL shorteners and malicious redirects.

## Draft notes for chapters 3–7 (T4.4)

### Chapter 3: Requirements

**Functional requirements (Phase 1 = Phases A + B):**
1. **Link submission and cleaning (M3):** Accept a pasted URL (`POST /api/scans`, max 2048 chars, max 8 KB request body), trim wrappers (`"..."`, `<...>`, trailing punctuation), prepend `https://` when missing, and reject empty (`URL_EMPTY`), over-long (`URL_TOO_LONG`) or multi-link (`URL_MULTIPLE`) submissions with HTTP 400.
2. **Link classification (M3):** Route `http`/`https` downloads to the fetcher; classify `magnet:`, `ftp:`, `intent:` and `.torrent` links as `unsupported` (`LINK_TYPE_UNSUPPORTED`); reject `file:`, `gopher:`, `data:`, `javascript:` and `blob:` schemes (`URL_SCHEME_UNSUPPORTED`).
3. **SSRF-safe redirect following and head fetch (M2):** Validate every hop before connecting; resolve DNS once per hop and reject any non-public IP (`URL_PRIVATE_ADDRESS` / `SSRF_BLOCKED_AT_HOP`); pin the TCP/TLS connection to the validated IP while sending the original `Host` header and TLS `sni_hostname`; stream at most `LG_HEAD_FETCH_BYTES` (5 MB) under `LG_TOTAL_DEADLINE_S` (20 s) and `LG_MIN_THROUGHPUT_BPS` (1024 B/s after a 5 s grace period).
4. **Magic-byte detection and mismatch checks (M4):** Identify all formats in the spec §7 table (PE, DOS MZ, ELF, Mach-O/Java class, ZIP, DOCX, XLSX, JAR, APK, 7z, RAR4/RAR5, PDF, OLE, MP4, MP3, PNG, JPEG, plain text) and compare against the claimed filename (`Content-Disposition` → final URL → input URL) and `Content-Type` header (`TYPE_MISMATCH_EXEC`, `TYPE_MISMATCH_TEXT`, `TYPE_MISMATCH_OTHER`, `EXT_DOUBLE`, `EXT_RISKY`, `EXT_SPOOFED_NAME`, `TYPE_CONTENT_TYPE_MISMATCH`, `TYPE_POLYGLOT`).
5. **Explainable scoring and honest verdicts (M5):** Pure scoring function (`score = min(100, sum over groups of max(weight))`) with thresholds 30 (`SUSPICIOUS`) and 60 (`UNSAFE`), hard rule `TYPE_MISMATCH_EXEC -> UNSAFE`, and strict honesty rules (`UNABLE_TO_VERIFY` on missing evidence, `NO_ISSUES_IN_CHECKED_PART` on partial reads).
6. **Web inspection slip UI (M6):** Render all 7 screens (Home, Checking, Report, Unable to verify, Rejected, Unsupported, Error/Busy), including the 16-byte highlighted hex strip, redirect chain, collapsed details, and browser-local recent scans (`localStorage`).

**Non-functional requirements (spec §13, C6):**
- **Safety:** Never execute, import, or write downloaded bytes to paths derived from remote data; bind only to `127.0.0.1` (`D18`).
- **Performance & bounded memory:** Latency p95 < 3 s on the local demo server for files ≤ 5 MB; overall termination within `LG_TOTAL_DEADLINE_S + 2 s`; Python memory bounded near the 5 MB cap even against a 200 MB stream; concurrency capped at `asyncio.Semaphore(4)` with HTTP 503 `SERVER_BUSY` above 20 waiting scans.
- **Offline determinism & accessibility:** Zero CDN assets (`@fontsource/ibm-plex-sans`, `@fontsource/ibm-plex-mono`); WCAG AA contrast verified in automated tests; works down to 360 px width.

### Chapter 4: System design

**Architecture and data flow of one scan (`CLAUDE.md`):**
1. **`API` (`backend/app/api/`):** `BodySizeLimit` middleware enforces the 8 KB cap; `check_submission()` validates input; `POST /api/scans` calls `Orchestrator.submit(url)` and returns `202 Accepted` (`{scan_id, state: "queued", poll_after_ms: 500}`).
2. **`Orchestrator` (`backend/app/orchestrator/scans.py`):** Persists the `queued` row in SQLite (WAL mode), gates execution with `asyncio.Semaphore(4)`, transitions to `running`, and invokes `Executor.run(url)` across a JSON-serializable seam (`RawScanReport`).
3. **`InProcessExecutor` (`backend/app/orchestrator/executor.py`):**
   - **Router (`engine/router/`):** Cleans URL and runs pure `classify(url)`.
   - **Fetcher (`engine/fetcher/`):** Per hop, runs `check_target()` (URL checks → IDNA UTS-46 + strict WHATWG IP-literal parser → single DNS lookup via `Resolver` → `is_public()` with D40 IPv6/NAT64 rules), opens a fresh `httpx.AsyncClient` pinned to `target.ip` with `sni_hostname=target.punycode_host`, sends `HEAD` (`Connection: close`) then `GET` with `Range: bytes=0-5242879`, and streams up to 5 MB.
   - **Detectors (`engine/detect/`):** Runs `detect_type()` on `body_head`, refines full-scope ZIP subtypes via `zipfile.ZipFile.namelist()` (`refine_zip_subtype`, D75), extracts `claimed_name()` (RFC 6266 / RFC 5987), and runs all mismatch checks (`run_mismatch_checks()`).
4. **`Scorer` (`engine/scoring/`):** Pure function `score_scan(findings, read_facts, registry, thresholds)` computes `status`, `verdict`, `display_verdict`, `score`, `confidence`, `scope`, `headline`, and sorted `reasons`. `ScanResult` model validators (`D29`) enforce that no partial or low-confidence scan can ever return `display_verdict = SAFE`.
5. **Threat model (`docs/threat-model.md`):** Mitigates SSRF (IP literal normalization, DNS pinning, per-hop TLS client isolation `D41`), DoS/zip bombs (5 MB raw + decoded byte cap, 20 s deadline, 1 KB/s throughput floor, 4-scan semaphore), XSS (React text nodes only, no clickable scanned URLs, `\uXXXX` escaping of bidi/control characters), and log injection/leakage (`safe()` strips control/ANSI/bidi chars and redacts query values).

### Chapter 5: Implementation (module summary from `docs/modules/`)

- **Configuration & Registry (`core/config.py`, `registry/`):** `pydantic-settings` with profile guard refusing `LG_STATIC_HOSTS`, `LG_SSRF_EXEMPT`, and `LG_EXTRA_CA_BUNDLE` in `dev`/`prod`. 38 reason codes in `reason_codes.yaml` verified at startup and against all source files.
- **SSRF-Safe Fetcher (`engine/fetcher/`):** `ip_literals.py` parses decimal (`2130706433`), octal (`0177.0.0.1`), hex (`0x7f.1`), and short IPv4 forms; `targets.py` enforces D40 address rules; `pinned.py` pins the IP and TLS SNI per hop; `redirects.py` enforces manual redirect limits, loop detection, and hop recording; `fetch.py` and `response_rules.py` handle Range verification, capped gzip/deflate decoding, 429 single-retry, and throughput enforcement.
- **Router (`engine/router/`):** `clean_url()`, `classify()`, 1 KB HTML body sniff (`is_html_body()`), cloud-share page detection (`cloud_share_service()`), and mixed-script/confusable IDN detection (`is_homograph_host()`).
- **File-Type Detector & Mismatch Engine (`engine/detect/`):** `signatures.py` implements magic-byte detectors ordered riskiest-family-first plus in-memory ZIP central-directory listing (`refine_zip_subtype()`); `names.py` implements RFC 6266/5987 filename extraction; `mismatch.py` implements equivalence-class comparisons, double-extension sets (`D71`, `D77`), Unicode `Cc`/`Cf` spoofed-name detection (`D72`), and narrow polyglot detection (`D73`).
- **Scorer & Orchestrator (`engine/scoring/`, `orchestrator/`):** Pure `score_scan()` + `build_scope()`, and `Orchestrator` + `InProcessExecutor` with `RawScanReport` validation.
- **Web App (`web/src/`):** React 19 + TypeScript 5.9 + Tailwind v4 inspection-slip UI, `pollUntilDone()` with 1.5× backoff up to 2 s, `ClaimedVsActual` + 16-byte `HexStrip`, and `localStorage` recent scans.
- **Demo Server & Sample Kit (`demo/`):** Deterministic `make_samples.py` (fixed seed `20261016`, 24 files with `SHA256SUMS`) and 3-listener Starlette server (`:8081` HTTP, `:8443` valid TLS, `:8444` wrong-host TLS).

### Chapter 6: Testing and results

- **Automated test suites (all offline, network sockets blocked by `pytest-socket`):**
  - **Backend unit, contract, SSRF, golden, and integration tests:** > 1,100 tests covering all 45+ SSRF rows (`tests/ssrf/`), 17 golden scoring files (`tests/golden/`), all format signatures and mismatch rules (`tests/unit/`), OpenAPI contract parity (`tests/contract/`), and log safety (`tests/integration/test_log_safety.py`).
  - **End-to-end acceptance matrix (`tests/e2e/test_acceptance_matrix.py`):** All 22 rows of spec §12 (24 test runs including 18a/18b/18c) pass against the local demo server:
    - Caught disguised executables / risky names: **100%** (rows 3, 4, 9).
    - False alarms on genuine samples: **0%** across all generated formats (`test_detect_samples.py`, rows 1, 8, 21).
    - SSRF attempts blocked with zero outbound connections to private targets: **100%** (rows 11, 12 + 45 SSRF table rows).
    - Partial/failed scans never shown as plain `SAFE`: **100%** (rows 2, 7, 10, 13–20, 22).
  - **Web Vitest suite (`web/`):** 120 tests across 10 test files (polling backoff, API error mapping, WCAG AA contrast across all light/dark token pairs, hostile XSS/bidi filenames, full row-9 report rendering, and `localStorage` recent scans).
  - **Demo server & automation loop tests:** 91 demo server tests + loop unit tests.

### Chapter 7: Limitations and future work

Summarise `docs/limitations.md`:
- **By design in Phase 1:** Only the first 5 MB are read (tail reads arrive in Phase D); magic-byte structural verification only (no behavioral sandbox or antivirus signatures); web pages and cloud-share pages are not scraped; `.torrent` and ZIP interior inspection arrive in Phase D; reputation lookups and hardened container execution arrive in Phase E; the Chrome MV3 download-interceptor extension arrives in Phase C.

## Viva question bank (prepare a 2–3 sentence answer each; add new ones after every rehearsal)

| Question | Key points |
| --- | --- |
| How do you stop DNS rebinding? | Resolve once, connect to the checked IP, send the original name as SNI and check the certificate against it (D43); one client per hop because httpx pools connections by IP, not by name (D41) |
| Why not just use VirusTotal? | It judges known files; LinkGuard catches disguised/new files from structure, explains why, works before download |
| What is SSRF and how do you prevent it? | Tricking a server into requesting internal addresses; every resolved IP on every redirect hop is checked, connection pinned to the checked IP, localhost-only backend |
| Do you run or open the file? | Never; only the first bytes are read and compared with signatures |
| What are magic bytes? Give examples | Fixed bytes at the start of a format: MZ (Windows exe), %PDF-, PNG's 89 50 4E 47 |
| What if the malware is after the first 5 MB? | Scope is reported; partial scans never shown as "Safe"; documented limitation |
| How is the score computed? Why those weights? | Highest weight per group, summed, capped at 100; thresholds 30/60; starter weights checked on the test set; hard rule for executables disguised as media |
| Why "Unable to verify" instead of Safe on errors? | Missing evidence is not evidence of safety |
| How does the extension stop a download? | MV3 can't block synchronously; it pauses on creation, checks, then resumes or cancels; small files may finish first, handled honestly |
| Why no login or database of users? | Single-user local tool, no personal data, nothing reachable from outside the laptop |
| Why SQLite, why FastAPI, why React? | Zero-setup, Python parsing tools + auto API docs, standard UI stack with typed client |
| What are the limitations? | Partial reads, cloaking servers, no behavioural analysis, limited formats |
| How did you test it without real malware? | Generated harmless samples and disguised copies, local demo server imitating good/bad/broken servers |
| What did each team member build? | Each owner explains their module from their note |
| How do you stop the scanner being used to attack your own network? | SSRF checks on resolved IPs at every hop; demo exemptions only exact host:port in test/demo profiles, refused at startup otherwise |
| What stops a wrong "Safe"? | Contract validator refuses plain SAFE for partial or low-confidence scans; crashes become Unable to verify (ANALYSIS_ERROR) |
| How do backend and web app agree on the data format? | Pydantic models → OpenAPI → generated TypeScript types; CI fails if they drift |
| Is the UI accessible? | Word + icon for every verdict; contrast computed from the real CSS in tests (WCAG AA); keyboard focus ring |
| What is a "Trojan Source" attack and could it affect your code? | Hidden bidi characters make code read differently from how it runs; a test fails if any source file contains one |
| How would you extend it? | More analyzers behind the same findings interface; run scans in separate containers |
| How does LinkGuard distinguish a `.docx` from a plain `.zip` safely? | Both start with `PK\x03\x04`; if the whole file was read (`full` scope), `refine_zip_subtype` inspects `ZipFile.namelist()` in memory (capped at 10,000 entries, never extracting bytes) for `[Content_Types].xml` and `word/` (D75) |
| What happens when a server ignores `Range` and sends a 200 MB file? | `Fetcher.stream` counts raw bytes from `aiter_raw()`, slices at 5 MB, and closes the connection immediately without draining the remaining 195 MB (D55) |
| Why does `safe()` scan inside exception strings for URLs? | `httpx` and other libraries embed the request URL inside exception messages; redacting embedded URLs prevents signed-URL query tokens from leaking into error logs (D30, T3.5) |
