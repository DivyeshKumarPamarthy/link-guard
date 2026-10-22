# Module: SSRF-safe fetcher (M2, tasks T1.2–T1.4, T2.1)

Owner: Divyesh (track A, D16) · Reviewer: TBD · Phase: B · Last updated: 2026-10-20

This note grows with each fetcher task. **Done so far: T1.2, the target check** (URL
validation, host normalization, IP literals, resolvers, address classification, demo
exemption), **T1.3, pinned connections**, **T1.4, redirects** and **T2.1, the streaming
fetch** (see the sections below). The fetcher is complete; T2.4 wires it into real scans.

## What it does (2–3 sentences, plain language)

Before LinkGuard contacts any link, `check_target` decides whether it is safe to contact.
It refuses links that point inside the computer or a private network (Server-Side Request
Forgery, SSRF), however the address is disguised. If the link is allowed, it returns the
exact addresses the fetcher must connect to, so DNS cannot be asked again and give a
different answer.

## Inputs and outputs
- Input: a URL string, `Settings` (allowed ports, max URL length, profile, demo exemptions)
  and a `Resolver` (system DNS, static demo hosts, or a fake in tests).
- Output: a `Target` (scheme, port, display and punycode host, validated addresses, pinned
  `ip`, `address_class`, `exempt`), or an exception:
  - `TargetRejected(code)`: refused; `code` is a `rejected` reason code: `URL_INVALID`,
    `URL_SCHEME_UNSUPPORTED`, `URL_USERINFO`, `URL_PORT_BLOCKED`, `URL_PRIVATE_ADDRESS`.
  - `ResolveError`: the name has no addresses (`FETCH_DNS_ERROR`, so Unable to verify).

## How it works (5–10 lines; the steps you would draw on a whiteboard)

1. **Length**: longer than `LG_MAX_URL_LENGTH` is `URL_INVALID` (covers redirect hops too).
2. **Parse** with `urllib.parse.urlsplit`; a parse error or no host is `URL_INVALID`.
3. **Scheme** `http`/`https` only; **no userinfo** (`@`); **port** in `LG_ALLOWED_PORTS`.
4. **Normalize the host** (`normalize_host`): refuse any `%`; IDNA (UTS 46) mapping turns
   full-width digits and ideographic dots into ASCII; strip one trailing dot; keep the
   display (Unicode) and punycode forms.
5. **IP literals** (`ip_literals.py`): a host ending in a number must parse as IPv4 under
   the WHATWG rules (decimal, octal, hex, short forms), or it is `URL_INVALID`.
6. **Resolve once** (`resolve_once`): IP literals need no lookup; names are resolved exactly
   once per hop.
7. **Classify every address** (`is_public`, D40). One non-public address rejects the link,
   unless the (name, port) pair is a demo exemption in the test or demo profile.

Steps 1–5 need no DNS, so most bad links are refused without any network activity.

## Why it is designed this way (the decision and the simpler/harder alternative you rejected)

- **Classify resolved addresses, not names.** A blocklist of names ("localhost",
  "metadata.google.internal") misses `localtest.me` and `127.0.0.1.nip.io`, which are public
  names that resolve to 127.0.0.1.
- **Parse IP literals ourselves (WHATWG rules).** Browsers and C libraries read
  `2130706433` or `0x7f.1` as 127.0.0.1. If we treated those as names, the operating system
  would still turn them into loopback. A host that looks numeric but is invalid
  (`256.1.1.1`) is refused, never sent to DNS, because different parsers disagree on it (D38).
- **Resolve once and pin.** Resolving again at connect time would let a DNS server answer
  "public" for the check and "127.0.0.1" for the connection (DNS rebinding).
- **`is_global` plus D40.** Python's `is_global` calls NAT64 (`64:ff9b::7f00:1`),
  IPv4-compatible (`::7f00:1`), site-local and multicast addresses "public". D40 judges
  NAT64 and IPv4-mapped addresses by their IPv4 part, and never contacts `::/96`,
  site-local or multicast. Refusing all NAT64 would have been simpler, but it would break
  scanning on IPv6-only networks, where DNS64 answers `64:ff9b::<IPv4>` for ordinary sites.
- **Exemption by exact (name, port), test/demo only (D2).** The e2e tests need the demo
  server on loopback. A global "allow private" switch would make it too easy to weaken
  production by accident.

## Pinned connections (T1.3, `pinned.py`, D41–D43)

**What:** the request goes to the address `check_target` validated, never to the name, so
nothing resolves the name a second time. The original name still travels in two places:
the `Host` header (so the server serves the right site) and the TLS SNI field via httpx's
`sni_hostname` extension, which is also the name the certificate is checked against. A
certificate for any other name is refused. CA certificates come from `certifi` (D43), the
same on every machine; the local test CA is added only in the test and demo profiles.

**The connection-reuse finding (for the report).** During the spike, a request for
`evil.example` succeeded against a server whose certificate only covers `a.demo.test`. The
cause: httpx keeps finished connections in a pool and reuses them, and it identifies a
pooled connection only by scheme, IP address and port, not by the SNI name. The first
request had opened and verified a connection to 127.0.0.1:8443 as `a.demo.test`; the second
request, also to 127.0.0.1:8443, simply reused it, so its own certificate check never
happened. In real use this means: two sites behind the same IP (common with CDNs), one hop
verified for site A, and a later hop for site B riding on A's verified connection.

**Why D41 fixes it:** every hop gets its own new client, closed when the hop ends, so every
hop starts with an empty pool and makes its own TLS handshake and certificate check. Within
one hop all requests (HEAD, the Range GET fallback, the single retry) go to the same Target,
so reusing the connection there is safe. The cost is at most one extra handshake per hop
(5 redirects at most). The alternative, one shared client with keep-alive turned off, was
rejected: it still shares one pool and one cookie jar (also keyed by IP) across sites, and
"one hop, one client, one certificate check" is easier to explain and to check in review.
A canary test asserts the unsafe httpx behaviour on a shared client, so the team notices if
a future httpx version changes it.

## Redirects (T1.4, `redirects.py`, D45–D51)

**What:** httpx never follows redirects (`follow_redirects=False`); `follow_redirects()` does
it by hand so that every redirect target is checked exactly like a pasted link, with one DNS
lookup per hop, before anything is sent to it. It records the chain and, if it stops early,
says why and where. The function that contacts one hop is passed in, so the logic is tested
with fakes and T2.1 plugs in the real request.

**For each redirect, in this order (D46):**
1. Only 301/302/303/307/308 with a `Location` are redirects (D45); two *different*
   `Location` headers are refused (`REDIR_BAD_TARGET`), because clients disagree on which
   one wins (D51).
2. Resolve a relative `Location` against the current URL; drop the fragment.
3. More than `LG_MAX_REDIRECTS` → `REDIR_TOO_MANY`; that target is never looked up.
4. `magnet:`, `ftp:`, `intent:`, or a `.torrent` path → "not supported yet" (D6, D50);
   any other non-web scheme → `REDIR_BAD_TARGET` with the reason in plain words (D51).
5. Already visited → `REDIR_LOOP`.
6. The full `check_target`. A private address becomes `SSRF_BLOCKED_AT_HOP {hop}`; an
   invalid or too-long URL `REDIR_BAD_TARGET`; a blocked port or user name keeps its own
   code; no DNS answer `FETCH_DNS_ERROR` (D47).

**Facts about the chain (D49)**, reported even when the chain stops later: the first
https → http switch (`REDIR_DOWNGRADE {hop}`), more than `LG_LONG_CHAIN_HOPS` redirects
(`REDIR_LONG_CHAIN`), and a change of host (`REDIR_CROSS_DOMAIN`, `link_type = shortened`).
Hosts are compared in their ASCII (punycode) form; the Unicode form is only shown.

**Hop records (D48):** one per URL that went through the checks; a refused one is listed as
`blocked` with no status, so the report shows the chain up to where it stopped.

## The streaming fetch (T2.1, `fetch.py`, `response_rules.py`, D52–D61)

**What:** `fetch(url, settings, resolver) -> FetchResult` follows the link (every hop checked,
pinned) and reads at most `LG_HEAD_FETCH_BYTES` of the final file. Every way it can end is a
defined result with a reason code; nothing becomes "Safe" because something failed.

**Per hop (D52)**, with one client: HEAD (`Connection: close`); a redirect is followed with
no GET. Otherwise one GET with `Range: bytes=0-(cap-1)` on a fresh connection, and that
response is the one trusted. The HEAD's connection is closed because a server that is still
busy with it would make the GET wait behind it (found in testing). No cookies are kept.

**On the final response**, in this order:
1. Error statuses (D57): 401/403 → `FETCH_AUTH_REQUIRED`; 429 → one retry after a short
   `Retry-After` (≤ `LG_MAX_RETRY_AFTER_S`), then `FETCH_RATE_LIMITED`; anything else that
   is not 2xx → `FETCH_HTTP_ERROR {status}`.
2. A web page (D53): `text/html` / `application/xhtml+xml` without `attachment` → stop
   before reading any body byte, add `LINK_IS_WEB_PAGE`, scope metadata-only. **T3.1 must
   reuse `is_web_page_headers()` and add `LINK_IS_WEB_PAGE` only for the HTML-sniff case,
   never a second time.**
3. Range (D54): a 206 with `Content-Range: bytes 0-E/T` confirms Range and gives the total;
   a 200 means the server ignored Range (we still read only the first cap bytes); a broken
   206 is `FETCH_HTTP_ERROR {status: 206}`.
4. Encoding (D56, D61): gzip/deflate are decoded by us, never past the cap
   (`FETCH_UNEXPECTED_ENCODING`, scope partial); anything else is
   `FETCH_UNSUPPORTED_ENCODING` and never guessed at.
5. The body (D55, D58): raw bytes are counted as they arrive (`Content-Length` is never
   trusted), the response is closed at the cap without draining it, the whole fetch runs under
   `LG_TOTAL_DEADLINE_S`, and after `LG_MIN_THROUGHPUT_GRACE_S` a server slower than
   `LG_MIN_THROUGHPUT_BPS` is cut off (`FETCH_TIMEOUT`). Bytes read before a timeout or a
   reset (`FETCH_INTERRUPTED`) are kept.

**Full or partial (D54):** full only when the whole body is known to have arrived: bytes read
equal the Content-Length or Content-Range total, or a chunked body ended with its
terminating chunk. A body read until the connection closed with no length is partial, as are
the cap, an early end and decoded bodies. `FetchResult.whole_file` holds this rule.

## How it is tested (test files, acceptance rows it covers)

- `backend/tests/ssrf/test_ssrf_table.py`: every spec §5 row that needs no redirect or fetch,
  plus the D38 and D40 rows. Each row also states whether DNS may be asked; most must be
  refused before any lookup.
- `backend/tests/ssrf/test_targets.py`: accepted targets, normalization, the order of
  checks, `URL_INVALID` cases (D38), the exemption, the resolvers, and the IP-literal parser.
- `backend/tests/ssrf/fakes.py`: `FakeResolver` (fixed answers, records every lookup).
  `conftest.py` adds a socket guard that fails any test that tries real DNS or a connection.
- Run: `make test-ssrf`. All spec §5 rows are now covered.
- `backend/tests/ssrf/test_redirect_hops.py` (T1.4, no sockets): a public link that
  redirects to loopback, metadata, `[::1]`, `0x7f.1`, `//127.0.0.1/`, a name resolving to
  loopback, or a mixed-record name stops with `SSRF_BLOCKED_AT_HOP`, the chain kept and the
  target never contacted; one lookup per hop (rebinding); the demo exemption does not cover
  a redirect to the demo server's IP.
- `backend/tests/unit/test_redirects.py` (T1.4): redirect statuses, relative locations,
  too-many, loops, bad and unsupported targets, refusals at a hop, conflicting or over-long
  `Location`, downgrade, long chain, cross-domain; plus `integration` tests against the
  demo server's chain (row 8), loop (row 10), redirect to localhost (row 11), https → http
  downgrade and too-many endpoints. The demo fixture is shared in `tests/demo_server.py`.
- `backend/tests/unit/test_pinned_tls.py` (T1.3, marked `integration`, D44): starts the real
  demo server as a subprocess on free loopback ports with a fresh test CA, and may open
  sockets to 127.0.0.1 only. Valid certificate → 200; wrong-host certificate → certificate
  error (the test checks the cause, so "connection refused" cannot pass); resolver called
  once and the name never reaches the system's DNS; a second host on the same IP gets its
  own certificate check; the shared-client canary; plain HTTP; proxy variables ignored;
  request building (first validated IP, Host header, IPv6 brackets, no SNI for IP literals).
- `backend/tests/unit/test_fetch.py` (T2.1, `integration`): one test per demo endpoint:
  small file whole over HTTP and HTTPS (rows 1, 21), wrong-host certificate (22), 200 MB with
  and without Range stops at exactly 5 MB in seconds with Python memory under 32 MB (2, 13),
  slow drip and total deadline (14), reset, chunked, gzip (20), empty (19), web page (17),
  401/403/404/410/500 (15, 16), 429 retry, connection refused, and redirects through the real
  fetch (8, 10, 11).
- `backend/tests/unit/test_fetch_helpers.py` (T2.1, no network): Content-Range and
  Retry-After parsers, the web-page rule, encodings, a decompression bomb (50 MB of zeros
  stops at the cap), corrupt and undecodable bodies, status mapping, TLS detection in the
  exception chain, the no-cookies client, and the full-scope rule.
- Checked by hand once (not a test, tests never use the internet): example.com, python.org
  and github.com load; badssl.com's wrong-host and expired certificates are refused.

## Known limitations

- `check_target` is synchronous and `SystemResolver` blocks; the async fetcher must call it
  in a worker thread (T2.1).
- Only the first validated address is used; if it is down, the hop fails rather than
  trying the next address (simplest; revisit in T2.1 if the demo needs it).
- ASCII host names may contain only letters, digits, `-`, `_` and `.`; anything else is
  `URL_INVALID`. Unusual but valid names (none known) would be refused.
- At a redirect hop, T1.4 reports `URL_INVALID` targets as `REDIR_BAD_TARGET`; for pasted
  input, T3.1 returns HTTP 400 `URL_INVALID` with no scan (D38).

## Likely viva questions (and your short answers)

- *Why not just block "localhost" and 127.0.0.1?* Too many spellings (`127.1`,
  `2130706433`, `[::ffff:127.0.0.1]`, full-width digits) and public names that resolve to
  loopback. We classify the final addresses instead.
- *What is DNS rebinding and how do you stop it?* A name answers "public" when checked and
  "private" when connected. We resolve once and connect only to the checked address.
- *Why reject if ANY address is private?* The connection could use the private one.
- *Why is NXDOMAIN not "unsafe"?* No answer is missing evidence, so it means "cannot
  check" (Unable to verify), never Safe and never Unsafe.
- *Why is `64:ff9b::5db8:d822` allowed but `::5db8:d822` refused?* The first is NAT64, which
  real IPv6-only networks use to reach a public IPv4 site. The second is a deprecated form
  with no legitimate use (D40).
- *Why a new HTTP client for every hop?* httpx reuses pooled connections by IP and port,
  not by name, so a shared client could carry a request for site B over a connection
  verified for site A on the same IP. A fresh client per hop forces a certificate check
  for every hop (D41).
- *Why certifi instead of the system's certificates?* The same CA list on every machine,
  including uv's standalone Python, which may not find the system store (D43).
- *Why follow redirects yourself instead of letting httpx do it?* httpx would follow a
  redirect to 127.0.0.1 without our checks. Every hop must pass the same checks as the
  pasted link, with one lookup, before anything is sent.
- *What if a redirect has two Location headers?* Refused: different clients pick different
  ones, so we could approve one target while a browser follows the other (D51).
- *How do you stop a 2 GB download or a decompression bomb?* The cap counts bytes actually
  read, never the Content-Length header, and the decoder never produces more than the cap.
- *Why is a slow server "Unable to verify" and not "Safe"?* A timeout is missing evidence;
  missing evidence never means safe (`FETCH_TIMEOUT`, bytes kept, scope partial at best).
- *Why HEAD and then GET?* HEAD finds redirects cheaply; the GET with Range is the response
  we trust, because some servers answer HEAD wrongly or not at all.
- *How do the tests prove no network was used?* The fake resolver records every lookup, and
  the socket guard fails the test on any real DNS call or connect.
