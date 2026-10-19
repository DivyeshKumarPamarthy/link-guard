# LinkGuard Phase 1 specification (roadmap Phases A + B)

Status: authoritative for Phase 1. Supersedes `docs/reference/linkguard-implementation-plan.html`
where they disagree. Items marked **[CONFIRM Cn]** are defaults chosen to unblock work; the team
should confirm or change them and log the result in `docs/decisions.md` (section "Items to confirm").

## 1. Scope

In scope (modules from the plan): M1 setup + contract, M2 SSRF-safe fetcher, M3 link router,
M4 file-type detection and mismatch, M5 scoring v1, M6 web app v1, M7 test kit + demo server.
Added cross-cutting modules: X1 orchestrator, X2 reason-code registry, X3 security baseline
(threat model, localhost-only binding, `safe()` logging helper), X4 environments (config
profiles, docker-compose).

Deliberately cut (decision D17): authentication and identity, `client_id`, scan history API,
caching and retention, in-flight dedupe, rate limiting, queue infrastructure, structured/JSON
logging, metrics, `/healthz`, PostgreSQL, migrations tooling. These cuts assume the backend
runs on localhost only (D18).

Link types handled: HTTP/HTTPS direct file links and redirect chains ("shortened" links).
`magnet:`, `ftp:` and URLs ending in `.torrent` return `unsupported`.

Out of scope: Chrome extension, Docker worker, reputation services, caching with TTLs, PE/ZIP/
PDF/Office/script/torrent inspection, accounts.

Phase demo (must work offline from one laptop): clean file is Safe; renamed .exe flagged;
shortened URL resolved with chain shown; SSRF rejected including via redirect; large file shows
the partial-scan label; unreachable and login-required links give Unable to Verify.

## 2. API contract v1

All responses carry `schema_version: "1.0"`. Pydantic models in `backend/app/contract/` are the
source of truth; OpenAPI is generated from them and web types from OpenAPI.

### Endpoints

| Method | Path | Purpose | Success |
| --- | --- | --- | --- |
| POST | `/api/scans` | Submit a link | `202` `{schema_version, scan_id, state, poll_after_ms}`; `503` when busy |
| GET | `/api/scans/{scan_id}` | Poll one scan | `200` ScanResult; `404` if unknown |

There is no list or history endpoint. `scan_id` is a random UUIDv4; knowing it is the only
way to read a result.

### Request: `POST /api/scans`

```json
{ "url": "https://short.example/abc" }
```

- `url`: string, required; raw user text (router cleans it). Max 2048 chars after trimming.
- Unknown fields are ignored (so Phase 2 can add optional fields without breaking clients).
- Request body larger than 8 KB → `413`.

### Input errors (no scan is created)

HTTP `400` with `{ "schema_version": "1.0", "error": { "code": "...", "message": "..." } }`.
Codes: `URL_EMPTY`, `URL_TOO_LONG`, `URL_MULTIPLE`.
Too many scans waiting → `503` with code `SERVER_BUSY` and `Retry-After: 5`.
Unexpected server error → `500` with code `INTERNAL_ERROR`; never a stack trace.

### Response: `ScanResult`

```json
{
  "schema_version": "1.0",
  "scan_id": "9f3c2d1e-…",
  "state": "done",
  "status": "completed",
  "input_url": "https://short.example/abc",
  "normalized_url": "https://short.example/abc",
  "final_url": "https://files.example/movie.mp4",
  "display_host": "files.example",
  "punycode_host": "files.example",
  "link_type": "shortened",
  "verdict": "UNSAFE",
  "display_verdict": "UNSAFE",
  "score": 70,
  "confidence": "high",
  "scope": { "mode": "full", "bytes_analyzed": 48213, "total_bytes": 48213, "range_supported": true, "label": "Whole file checked (47 KB)" },
  "headline": "Blocked: file named .mp4 is actually a Windows executable",
  "file": { "claimed_name": "movie.mp4", "name_source": "content-disposition", "content_type": "video/mp4", "detected_type": "pe-executable", "detected_label": "Windows executable", "family": "executable", "detection_confidence": "certain",
            "first_bytes_hex": "4d5a90000300000004000000ffff0000", "signature": { "offset": 0, "length": 2, "name": "MZ (Windows executable)" } },
  "redirects": [
    { "url": "https://short.example/abc", "status": 302, "address_class": "public" },
    { "url": "https://files.example/movie.mp4", "status": 200, "address_class": "public" }
  ],
  "reasons": [
    { "code": "TYPE_MISMATCH_EXEC", "severity": "high", "weight": 70, "group": "type",
      "message": "The file is named .mp4 but its content is a Windows executable.", "evidence": {"claimed_ext": "mp4", "detected": "pe-executable"} },
    { "code": "REDIR_CROSS_DOMAIN", "severity": "info", "weight": 0, "group": "redirect",
      "message": "The link ended on a different site: files.example.", "evidence": {"final_host": "files.example"} }
  ],
  "unavailable_signals": [],
  "timings_ms": { "total": 812, "fetch": 640 },
  "engine_version": "1.0.0",
  "rules_version": "1.0.0",
  "created_at": "2026-10-16T10:15:00Z",
  "completed_at": "2026-10-16T10:15:01Z"
}
```

Enums:
- `state`: `queued | running | done`. While not `done`, outcome fields (`status`, `verdict`, `display_verdict`, `score`, `confidence`, `headline`, `reasons`, `file`) are `null`.
- `status` (when done): `completed | rejected | unsupported`.
- `verdict` (only when `status=completed`, else `null`): `SAFE | SUSPICIOUS | UNSAFE | UNABLE_TO_VERIFY`.
- `display_verdict`: `SAFE | NO_ISSUES_IN_CHECKED_PART | SUSPICIOUS | UNSAFE | UNABLE_TO_VERIFY | REJECTED | UNSUPPORTED`. Computed by the backend; clients render from this field only.
- `confidence`: `high | medium | low`, or `null` when status is not `completed`.
- `scope.mode`: `full | partial | metadata-only | none`.
- `link_type`: `http | shortened` (Phase 1); `torrent | magnet | ftp | other` appear only with `status=unsupported`.
- `severity`: `info | low | medium | high`.
- `address_class`: `public | private | blocked`.

`file.first_bytes_hex` is the first 16 bytes as lowercase hex (or fewer if the body is shorter);
`file.signature` marks which of those bytes identified the type (null when unknown or beyond 16
bytes). These drive the "claimed vs actual" panel in the UI (`docs/ui-style-guide.md`).

Clients MUST ignore unknown fields and render unknown reason codes with a generic card
(code + message). Breaking changes bump `schema_version` major.

## 3. Outcome rules

Status:
- `rejected`: the target is unsafe to contact (SSRF codes, blocked scheme, userinfo, blocked port, bad redirect target). No verdict.
- `unsupported`: link type not handled in Phase 1 (`magnet:`, `ftp:`, `.torrent` URL, redirect ending at `magnet:`/`ftp:`/`intent:`). No verdict.
- `completed`: everything else, including all fetch failures.

Verdict (status `completed`):
1. Compute score (Section 6).
2. If any hard rule fired → at least that verdict.
3. Else if score ≥ 60 → `UNSAFE`; ≥ 30 → `SUSPICIOUS`.
4. Else (score < 30): if any `outcome: unable` code is present (fetch failures, web page, redirect loop) → `UNABLE_TO_VERIFY`; otherwise `SAFE`.

So risk evidence always wins over missing data, and missing data never becomes `SAFE`.

Scope:
- `full`: the whole body was read (stream ended before the cap and bytes read equals Content-Length when known).
- `partial`: some body bytes read but not all (cap hit, interrupted, timed out after bytes, unexpected encoding).
- `metadata-only`: decided from headers alone (e.g. `text/html` page; body not read).
- `none`: no body bytes read (rejected, unsupported, HTTP errors, loops, empty body).

Confidence (status `completed`):
- `high`: scope `full`.
- `medium`: scope `partial` with Range support confirmed (206 + valid Content-Range) and total size known.
- `low`: everything else (partial without Range, unknown size, unexpected encoding, metadata-only, none, any `UNABLE_TO_VERIFY`).

Display verdict: `SAFE` only when verdict `SAFE` AND scope `full` AND confidence ≥ medium.
Verdict `SAFE` with any other scope → `NO_ISSUES_IN_CHECKED_PART`. Other verdicts map 1:1;
`rejected` → `REJECTED`, `unsupported` → `UNSUPPORTED`.

Headline: top reason by weight (ties: severity, then code alphabetical); templates live in
the registry. No reasons + SAFE → "No problems found in the whole file". NO_ISSUES →
"No issues found in the checked part ({scope.label})".

## 4. Configuration (environment variables, `backend/app/core/config.py`)

| Variable | Default | Notes |
| --- | --- | --- |
| `LG_PROFILE` | `dev` | `dev | test | demo | prod`; exemptions only allowed in `test`/`demo` |
| `LG_HEAD_FETCH_BYTES` | 5242880 | Phase 1 byte cap (5 MB) |
| `LG_CONNECT_TIMEOUT_S` | 5 | |
| `LG_TOTAL_DEADLINE_S` | 20 | Whole scan including redirects |
| `LG_MIN_THROUGHPUT_BPS` | 1024 | **[confirmed C1]** enforced after a 5 s grace period |
| `LG_MAX_REDIRECTS` | 5 | |
| `LG_LONG_CHAIN_HOPS` | 3 | **[confirmed C2]** more redirects than this → `REDIR_LONG_CHAIN` |
| `LG_ALLOWED_PORTS` | `80,443` | |
| `LG_MAX_URL_LENGTH` | 2048 | |
| `LG_MAX_CONCURRENT_SCANS` | 4 | `asyncio.Semaphore` size |
| `LG_MAX_WAITING_SCANS` | 20 | Beyond this, `POST` returns 503 `SERVER_BUSY` |
| `LG_BIND_HOST` | `127.0.0.1` | Must stay loopback (D18) |
| `LG_CORS_ORIGINS` | `*` | `allow_credentials=False` always |
| `LG_DATABASE_URL` | `sqlite:///./linkguard.db` | `PRAGMA journal_mode=WAL` on connect; nothing else |
| `LG_USER_AGENT` | `LinkGuard/1.0 (link safety checker)` | Fixed, honest |
| `LG_STATIC_HOSTS` | empty | `test`/`demo` only: `name=ip` pairs used by the resolver before DNS |
| `LG_SSRF_EXEMPT` | empty | `test`/`demo` only: `host:port` pairs allowed to resolve non-public |
| `LG_EXTRA_CA_BUNDLE` | empty | `test`/`demo` only: path to the local test CA |

Startup MUST fail if `LG_STATIC_HOSTS`, `LG_SSRF_EXEMPT` or `LG_EXTRA_CA_BUNDLE` are set in
`dev` or `prod`, and MUST log every active exemption at WARNING level.

## 5. Fetcher and SSRF rules (M2)

Pipeline per hop: parse (real URL parser) → validate scheme (`http`/`https`), host present,
no userinfo, port in allow-list, length → normalize host (lowercase, IDNA → punycode, strip
trailing dot; keep display + punycode forms) → parse IP literals strictly (decimal, octal, hex,
short forms, full-width digits normalized) → resolve A + AAAA via an injectable `Resolver`
(`getaddrinfo` in a thread; static hosts first in test/demo) → classify every address with
`ipaddress` (`is_global`; IPv4-mapped IPv6 by IPv4 part) → reject if any is non-public unless
`(host, port)` is exempt in test/demo → connect to the chosen validated IP with original Host
header and SNI/cert hostname = original host → send HEAD; on 405/403/501 or suspicious
headers fall back to `GET` with `Range: bytes=0-(N-1)`; always `Accept-Encoding: identity`;
no cookies, no auth, `trust_env=False` → handle 3xx manually: resolve relative Location, track
visited URLs, re-run the entire pipeline for the next hop → stream body counting bytes
actually read, stop at the cap, enforce total deadline and minimum throughput.

Pinned TLS: first task in week 2 is a spike (see tasks T1.3). Preferred approach: httpx with
the request extension `sni_hostname` while connecting to the IP URL, then verify the
certificate is checked against the original hostname using the local TLS demo endpoint
(valid cert → success, wrong-host cert → `FETCH_TLS_ERROR`). If this cannot be made to verify
hostnames correctly, use a custom transport, and only as a last resort the plan's fallback
(resolve, validate, connect, re-check the connected peer address) with the residual risk
written in `docs/limitations.md`.

`FetchResult` (plain data): `body_head: bytes`, `bytes_read`, `total_size | None`,
`range_supported: bool`, `ended: "complete" | "cap" | "timeout" | "interrupted" | "error"`,
`status_code`, whitelisted headers (`content-type`, `content-length`, `content-disposition`,
`content-range`, `content-encoding`, `etag`, `last-modified`, `location`, `retry-after`),
`hops: [ {url, status, address_class} ]`, `timings`, `failure_code | None`.

### SSRF test table (all must be rejected; a socket guard fails the test on any outbound connect)

| Input | Expected status / code |
| --- | --- |
| `http://127.0.0.1/` | rejected / URL_PRIVATE_ADDRESS |
| `http://localhost:8000/` | rejected / URL_PORT_BLOCKED or URL_PRIVATE_ADDRESS (port check runs first → URL_PORT_BLOCKED) |
| `http://localhost./` | rejected / URL_PRIVATE_ADDRESS |
| `http://[::1]/` | rejected / URL_PRIVATE_ADDRESS |
| `http://0.0.0.0/` | rejected / URL_PRIVATE_ADDRESS |
| `http://2130706433/` | rejected / URL_PRIVATE_ADDRESS |
| `http://0x7f.0.0.1/` | rejected / URL_PRIVATE_ADDRESS |
| `http://0177.0.0.1/` | rejected / URL_PRIVATE_ADDRESS |
| `http://127.1/` | rejected / URL_PRIVATE_ADDRESS |
| `http://１２７.0.0.1/` (full-width digits) | rejected / URL_PRIVATE_ADDRESS |
| `http://169.254.169.254/latest/meta-data/` | rejected / URL_PRIVATE_ADDRESS |
| `http://[::ffff:169.254.169.254]/` | rejected / URL_PRIVATE_ADDRESS |
| `http://metadata.google.internal/` (test resolver → 169.254.169.254) | rejected / URL_PRIVATE_ADDRESS |
| `http://10.0.0.5/`, `http://172.16.0.1/`, `http://192.168.1.1/` | rejected / URL_PRIVATE_ADDRESS |
| `http://100.64.0.1/` | rejected / URL_PRIVATE_ADDRESS |
| `http://[fe80::1]/` | rejected / URL_PRIVATE_ADDRESS |
| `http://localtest.me/` (test resolver → 127.0.0.1) | rejected / URL_PRIVATE_ADDRESS |
| `http://127.0.0.1.nip.io/` (test resolver → 127.0.0.1) | rejected / URL_PRIVATE_ADDRESS |
| `http://google.com@127.0.0.1/` | rejected / URL_USERINFO |
| `https://example.com:22/`, `:6379`, `:5432` | rejected / URL_PORT_BLOCKED |
| `file:///etc/passwd`, `gopher://x/`, `data:text/plain,hi`, `javascript:alert(1)` | rejected / URL_SCHEME_UNSUPPORTED |
| public demo URL that 302s to `http://127.0.0.1/` | rejected / SSRF_BLOCKED_AT_HOP (chain shown up to that hop) |
| Rebinding: resolver answers public then private | rejected or fetched from the FIRST validated IP only; resolver called exactly once per hop (assert) |
| Host with one public and one private A record | rejected / URL_PRIVATE_ADDRESS |
| Exempt host `a.demo.test:8081` but on port 8082 | rejected (exemption is exact host:port) |
| `127.0.0.1:8081` (demo server IP, not the exempt name) | rejected / URL_PRIVATE_ADDRESS |
| `HTTP_PROXY` set in environment | ignored (assert no proxy used) |

Add every newly discovered bypass as a row.

## 6. Router (M3)

- Clean: trim whitespace, strip surrounding quotes, `<…>`, trailing `.`/`,`/`)` not part of the URL; reject if more than one URL (`URL_MULTIPLE`, HTTP 400); add `https://` if no scheme; lowercase scheme and host.
- Classify (pure function `classify(url) -> LinkKind`): `http(s)` → fetch; `magnet:`, `ftp:`, path ending `.torrent` → unsupported (`LINK_TYPE_UNSUPPORTED`, message names the type, "planned for a later phase"); `file:`, `gopher:`, `data:`, `javascript:` and others → rejected (`URL_SCHEME_UNSUPPORTED`).
- `link_type = shortened` when the chain has ≥ 1 redirect to a different hostname (exact, case-insensitive comparison after normalization); otherwise `http`. The same rule triggers `REDIR_CROSS_DOMAIN`. No shortener lists.
- Web page: `Content-Type` `text/html` or `application/xhtml+xml` without `Content-Disposition: attachment` → stop reading, `LINK_IS_WEB_PAGE`, scope `metadata-only`. Also when the body is sniffed as HTML (`<!doctype html`, `<html` in the first 1 KB after whitespace/BOM) regardless of headers → `LINK_IS_WEB_PAGE`, scope as read.
- Cloud-share hint (P1): if final host is a known share host (Drive, Dropbox, OneDrive, Mega) and it is a web page, add info reason `LINK_CLOUD_SHARE_PAGE` with a hint about direct-download links. Never scrape the page.
- Redirect ending at `magnet:`, `ftp:`, `intent:` → unsupported. Ending at any other non-HTTP(S) scheme → rejected `REDIR_BAD_TARGET`.

## 7. Supported formats and detection (M4)

**[CONFIRM C3: 15 formats confirmed; 16th open, D15] format list.** The plan says 16 formats but never lists them. Identified 15:

| Family | Format | Signature |
| --- | --- | --- |
| executable | PE (.exe/.dll/.scr/.sys…) | `MZ` at 0, `PE\0\0` at `e_lfanew` (u32 at 0x3C) |
| executable | ELF | `7F 45 4C 46` |
| executable | Mach-O | `FE ED FA CE/CF`, `CE/CF FA ED FE`, `CA FE BA BE` (also Java class → "Java class or Mach-O") |
| archive | ZIP (.zip; base for .docx/.xlsx/.jar/.apk) | `50 4B 03 04`, `50 4B 05 06` (empty), `50 4B 07 08` (spanned) |
| archive | 7z | `37 7A BC AF 27 1C` |
| archive | RAR4 / RAR5 | `52 61 72 21 1A 07 00` / `52 61 72 21 1A 07 01 00` |
| document | PDF | `%PDF-` within the first 1024 bytes |
| document | DOCX / XLSX | ZIP + `[Content_Types].xml` + `word/` or `xl/` entries |
| document | OLE container (.msi, legacy .doc/.xls) | `D0 CF 11 E0 A1 B1 1A E1` |
| script (text) | .js, .ps1, .bat | No magic: detect text (BOM UTF-8/UTF-16, printable ratio); rely on extension |
| media | MP4 (+ .mov/.m4a class) | `ftyp` at offset 4 |
| media | MP3 | `ID3`, or frame sync `FF Ex/Fx` (certain only with a second valid frame header) |
| image | PNG | `89 50 4E 47 0D 0A 1A 0A` |
| image | JPEG | `FF D8 FF` |

(ELF and Mach-O are listed as executable family members in the plan; the 16th named format is
still to be confirmed by the team.)

`detect_type(bytes) -> {type, family, confidence: certain|probable|unconfirmed}`. The project's
table is authoritative; `python-magic` (optional) only logs disagreements.

DOCX/XLSX subtype: if scope is `full` (≤ 5 MB), list entries with `zipfile` over an in-memory
buffer (listing only, no extraction, entry cap 10,000, catch all exceptions). Otherwise scan the
head for local-header names; if not found → "ZIP-based, subtype unconfirmed" and no mismatch.

Claimed name order: `Content-Disposition` (RFC 6266/5987, `filename*` preferred) → final URL
path → original URL path. Normalize: percent-decode, take last path segment, strip trailing
dots/spaces, lowercase for comparison, keep the original for display (escaped). Never use as a path.

Equivalence classes (no mismatch inside a class): `{mp4, m4a, m4v, mov}`, `{jpg, jpeg, jpe}`,
`{zip, docx, xlsx, jar, apk}` for Content-Type `application/zip`, `{msi, doc, xls}` for OLE,
`application/octet-stream` / missing Content-Type = no signal.

Checks (each a separate function, each emits registry codes):
- executable content with a non-executable claimed extension → `TYPE_MISMATCH_EXEC`
- non-HTML text content with a binary claimed extension → `TYPE_MISMATCH_TEXT`
- other cross-family or wrong-member mismatch (PNG named .jpg, plain ZIP named .docx, .zip that is really .jar/.apk) → `TYPE_MISMATCH_OTHER`
- double extension where the last is executable/risky and the previous looks like a document/media type (`invoice.pdf.exe`) → `EXT_DOUBLE`
- risky extension outside the format list (`.scr .lnk .hta .vbs .cmd .jar .com .pif`) → `EXT_RISKY`
- control / bidi characters (U+202E, U+200B…) in the name → `EXT_SPOOFED_NAME`
- Content-Type contradicts detected type → `TYPE_CONTENT_TYPE_MISMATCH`
- second signature at a plausible offset → `TYPE_POLYGLOT` (P1)
- MZ without valid PE header in buffer → `TYPE_EXEC_PROBABLE` (info) and still family executable
- too short to detect → `TYPE_UNKNOWN` (info)

## 8. Reason-code registry (X2)

File: `backend/app/registry/reason_codes.yaml`. Loaded and validated at startup and in tests:
unique codes, allowed prefix, known group, weight ≥ 0, every template renders with the
declared evidence keys.

Entry shape:

```yaml
TYPE_MISMATCH_EXEC:
  group: type
  weight: 70
  severity: high
  outcome: risk          # risk | info | unable | rejected | unsupported
  hard_min_verdict: UNSAFE
  message: "The file is named .{claimed_ext} but its content is {detected_label}."
  headline: "Blocked: file named .{claimed_ext} is actually {detected_label}"
```

Allowed prefixes: `URL_ SSRF_ REDIR_ FETCH_ LINK_ TYPE_ EXT_ SCAN_ ANALYSIS_` (Phase 2+ will add
`REP_ BROWSER_ PE_ ARCH_ DOC_ PDF_ SCRIPT_ TOR_ MSI_ YARA_`). `EXT_` means filename
extension only; Chrome-extension codes will use `BROWSER_`.

Phase 1 codes and starter weights (hypotheses; tuned in Phase 4 only):

| Code | Group | Weight | Severity | Outcome | Notes |
| --- | --- | --- | --- | --- | --- |
| TYPE_MISMATCH_EXEC | type | 70 | high | risk | hard rule: at least UNSAFE |
| EXT_DOUBLE | type | 40 | medium | risk | |
| EXT_SPOOFED_NAME | type | 40 | medium | risk | **[confirmed C4]** weight not in plan |
| TYPE_POLYGLOT | type | 30 | medium | risk | **[confirmed C5]** weight not in plan; P1 |
| TYPE_MISMATCH_TEXT | type | 20 | low | risk | |
| TYPE_MISMATCH_OTHER | type | 15 | low | risk | |
| EXT_RISKY | type | 15 | low | risk | |
| TYPE_CONTENT_TYPE_MISMATCH | header | 10 | low | risk | renamed from plan's CONTENT_TYPE_MISMATCH |
| REDIR_DOWNGRADE | redirect | 10 | low | risk | |
| REDIR_LONG_CHAIN | redirect | 10 | low | risk | |
| REDIR_CROSS_DOMAIN | redirect | 0 | info | info | plan conflict resolved: informational |
| URL_HOMOGRAPH | url | 0 | info | info | P1 |
| LINK_CLOUD_SHARE_PAGE | link | 0 | info | info | P1 |
| TYPE_EXEC_PROBABLE | detect | 0 | info | info | |
| TYPE_UNKNOWN | detect | 0 | info | info | |
| SCAN_PARTIAL | scope | 0 | info | info | |
| FETCH_UNEXPECTED_ENCODING | fetch | 0 | info | info | forces confidence low, scope partial |
| LINK_IS_WEB_PAGE | link | 0 | info | unable | |
| FETCH_TIMEOUT | fetch | 0 | info | unable | |
| FETCH_INTERRUPTED | fetch | 0 | info | unable | only when too few bytes to detect a type |
| FETCH_EMPTY | fetch | 0 | info | unable | |
| FETCH_AUTH_REQUIRED | fetch | 0 | info | unable | 401/403 |
| FETCH_RATE_LIMITED | fetch | 0 | info | unable | 429 (one retry max, Retry-After ≤ 5 s) |
| FETCH_HTTP_ERROR | fetch | 0 | info | unable | 404, 410, 5xx, other non-2xx |
| FETCH_TLS_ERROR | fetch | 0 | info | unable | |
| FETCH_DNS_ERROR | fetch | 0 | info | unable | new (not in plan): NXDOMAIN / no answer |
| REDIR_LOOP | redirect | 0 | info | unable | |
| REDIR_TOO_MANY | redirect | 0 | info | unable | |
| ANALYSIS_ERROR | analysis | 0 | info | unable | internal exception, never leaks details |
| URL_PRIVATE_ADDRESS | url | – | – | rejected | |
| URL_USERINFO | url | – | – | rejected | |
| URL_PORT_BLOCKED | url | – | – | rejected | |
| URL_SCHEME_UNSUPPORTED | url | – | – | rejected | |
| SSRF_BLOCKED_AT_HOP | redirect | – | – | rejected | |
| REDIR_BAD_TARGET | redirect | – | – | rejected | |
| LINK_TYPE_UNSUPPORTED | link | – | – | unsupported | |

## 9. Scoring (M5)

```
score = min(100, sum over groups of max(weight of reasons in that group))
```

All reasons stay in the output even when not counted. Thresholds: 0–29 SAFE, 30–59 SUSPICIOUS,
60–100 UNSAFE (upper bucket inclusive: 30 is SUSPICIOUS, 60 is UNSAFE). Then apply Section 3.
Reason order in output: weight desc, severity desc, code asc. A code missing from the registry
at runtime: weight 0, ERROR log, no crash (tests fail on it).

Golden tests: `backend/tests/golden/<case>.input.json` → `<case>.expected.json`.

## 10. Web app (M6)

Visual design, tokens, layouts and copy rules: `docs/ui-style-guide.md` (authoritative for look and wording).

- Home: link input, submit, example links (demo profile only), short "what we check" text.
- Submit → `POST`, then poll `GET /api/scans/{id}` every `poll_after_ms` (backoff to 2 s), show elapsed time; disable submit while in flight.
- Report: verdict band (text + icon, never colour alone), headline, the "claimed vs actual" panel with the 16-byte hex strip and highlighted signature, score, confidence, scope label, reasons (severity icon + message; unknown codes → generic card), file info (claimed vs detected), redirect chain (URL as plain text with copy button, status, address class), timings, engine and rules version.
- Distinct screens: REJECTED (why the target cannot be scanned, no internal details), UNSUPPORTED (named link type), UNABLE_TO_VERIFY (neutral colour, states why), backend unreachable / 503 busy / 500.
- Recent scans (P1, optional): the last 20 `{scan_id, url, display_verdict, time}` kept in the browser's localStorage only, with a "clear" button. No backend history.
- Security: no `dangerouslySetInnerHTML`; scanned URLs never clickable; long values truncated in the middle with expand; control/bidi characters shown escaped (e.g. `\u202E`); IDN shows both forms.
- Accessibility: keyboard navigation, focus styles, labelled landmarks; works at 360 px; dark mode follows system.

## 11. Test kit and demo server (M7)

`demo/make_samples.py` (fixed seeds) generates into `samples/` (gitignored): genuine small
files for every format in Section 7; a tiny "hello" PE (generated or built by script — must not
be committed); disguised variants (`movie.mp4` = PE, `invoice.pdf.exe` = PE, `photo.jpg` = PNG,
`report.docx` = plain ZIP, `file.pdf` = HTML error page); a large MP4-shaped file streamed on
the fly (never written to disk). `.gitattributes` marks fixtures binary.

Demo server (`demo/`, HTTP on 8081, HTTPS on 8443 with a cert from a generated local test CA)
serves, by path:

| Path | Behaviour |
| --- | --- |
| `/f/{name}` | Sample file, correct Content-Type, Range supported |
| `/disguised/{name}` | Disguised samples with misleading Content-Type/Content-Disposition |
| `/big?range=yes|no` | 200 MB generated stream; `no` ignores Range and returns 200 |
| `/slow` | Headers, then 1 byte every 2 s |
| `/reset` | Sends 4 KB then closes the connection |
| `/chunked` | No Content-Length |
| `/gzip/{name}` | Gzip-encoded despite `identity` |
| `/cd/{variant}` | Content-Disposition variants (`filename*`, `../`, quotes, RTL override, NUL) |
| `/redirect/chain?n=2&to=…` | Hops across `a.demo.test` → `b.demo.test` → `c.demo.test` |
| `/redirect/loop` | A → B → A |
| `/redirect/internal` | 302 to `http://127.0.0.1/` |
| `/redirect/https-to-http` | Downgrade |
| `/status/{code}` | 401, 403, 404, 429 (with Retry-After), 500 |
| `/page` | HTML page |
| `/empty` | 0-byte body |
| `/index` | Directory-listing-style HTML |

Test/demo config: `LG_STATIC_HOSTS=a.demo.test=127.0.0.1,b.demo.test=127.0.0.1,c.demo.test=127.0.0.1`,
`LG_SSRF_EXEMPT=a.demo.test:8081,b.demo.test:8081,c.demo.test:8081,a.demo.test:8443,…`,
`LG_ALLOWED_PORTS=80,443,8081,8443,8444`, `LG_EXTRA_CA_BUNDLE=demo/certs/test-ca.pem`.
Port 8444 is the wrong-certificate HTTPS listener for row 22, exempted as `a.demo.test:8444` (D34).
A test asserts the `prod` profile rejects all of these.

## 12. Acceptance matrix (each row = one automated e2e test; exactly one expected outcome)

| # | Sample / input | status | verdict | display_verdict | confidence | scope | Required codes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Genuine small PDF | completed | SAFE | SAFE | high | full | none |
| 2 | Large MP4 > 5 MB, Range works | completed | SAFE | NO_ISSUES_IN_CHECKED_PART | medium | partial | SCAN_PARTIAL |
| 3 | `movie.mp4` that is a PE | completed | UNSAFE | UNSAFE | high | full | TYPE_MISMATCH_EXEC |
| 4 | Genuine PE named `invoice.pdf.exe` | completed | SUSPICIOUS | SUSPICIOUS | high | full | EXT_DOUBLE |
| 5 | PNG named `photo.jpg` | completed | SAFE | SAFE | high | full | TYPE_MISMATCH_OTHER |
| 6 | Plain ZIP named `report.docx` | completed | SAFE | SAFE | high | full | TYPE_MISMATCH_OTHER |
| 7 | HTML error page served as `file.pdf` with `application/pdf` | completed | UNABLE_TO_VERIFY | UNABLE_TO_VERIFY | low | full | LINK_IS_WEB_PAGE |
| 8 | 2-hop chain (a → b) to a clean PDF | completed | SAFE | SAFE | high | full | REDIR_CROSS_DOMAIN; link_type shortened |
| 9 | 2-hop chain to the disguised PE | completed | UNSAFE | UNSAFE | high | full | TYPE_MISMATCH_EXEC; link_type shortened |
| 10 | Redirect loop | completed | UNABLE_TO_VERIFY | UNABLE_TO_VERIFY | low | none | REDIR_LOOP |
| 11 | Chain whose hop 2 is `127.0.0.1` | rejected | null | REJECTED | null | none | SSRF_BLOCKED_AT_HOP; hops listed |
| 12 | `http://169.254.169.254/latest/meta-data/` | rejected | null | REJECTED | null | none | URL_PRIVATE_ADDRESS |
| 13 | Large file, server ignores Range | completed | SAFE | NO_ISSUES_IN_CHECKED_PART | low | partial | SCAN_PARTIAL; range_supported false |
| 14 | Slow-drip | completed | UNABLE_TO_VERIFY | UNABLE_TO_VERIFY | low | partial | FETCH_TIMEOUT |
| 15 | 404 | completed | UNABLE_TO_VERIFY | UNABLE_TO_VERIFY | low | none | FETCH_HTTP_ERROR |
| 16 | 401 | completed | UNABLE_TO_VERIFY | UNABLE_TO_VERIFY | low | none | FETCH_AUTH_REQUIRED |
| 17 | `text/html` page | completed | UNABLE_TO_VERIFY | UNABLE_TO_VERIFY | low | metadata-only | LINK_IS_WEB_PAGE |
| 18a/b/c | `magnet:?xt=…`, `https://…/x.torrent`, `ftp://…` | unsupported | null | UNSUPPORTED | null | none | LINK_TYPE_UNSUPPORTED |
| 19 | Zero-byte body | completed | UNABLE_TO_VERIFY | UNABLE_TO_VERIFY | low | none | FETCH_EMPTY |
| 20 | Gzip-encoded small PDF | completed | SAFE | NO_ISSUES_IN_CHECKED_PART | low | partial | FETCH_UNEXPECTED_ENCODING |
| 21 | HTTPS (8443) genuine PNG, valid test cert | completed | SAFE | SAFE | high | full | none (proves pinned TLS) |
| 22 | HTTPS endpoint presenting a cert for another host | completed | UNABLE_TO_VERIFY | UNABLE_TO_VERIFY | low | none | FETCH_TLS_ERROR |

Rows 7, 20, 21 and 22 differ from or extend the original plan; see `docs/decisions.md`.
Assert status, verdict, display_verdict, confidence, scope.mode and required codes — never exact scores.

## 13. Non-functional targets **[confirmed C6]**

- Scan latency against the local demo server: p95 < 3 s for files ≤ 5 MB (excluding deliberate slow endpoints).
- Every scan terminates within `LG_TOTAL_DEADLINE_S` + 2 s.
- Backend memory per scan bounded by the byte cap (+ overhead); 4 concurrent scans on a laptop.
- Logs: plain `logging` to the terminal; every URL, filename or header passes through `safe()` (strips control characters, redacts query values); never log body bytes.
