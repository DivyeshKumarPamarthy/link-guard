# Module: SSRF-safe fetcher (M2, tasks T1.2–T1.4, T2.1)

Owner: Divyesh (track A, D16) · Reviewer: TBD · Phase: B · Last updated: 2026-10-20

This note grows with each fetcher task. **Done so far: T1.2, the target check** (URL
validation, host normalization, IP literals, resolvers, address classification, demo
exemption). Still to come: pinned TLS (T1.3), redirects (T1.4), the streaming fetch (T2.1).

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

## How it is tested (test files, acceptance rows it covers)

- `backend/tests/ssrf/test_ssrf_table.py`: every spec §5 row that needs no redirect or fetch,
  plus the D38 and D40 rows. Each row also states whether DNS may be asked; most must be
  refused before any lookup.
- `backend/tests/ssrf/test_targets.py`: accepted targets, normalization, the order of
  checks, `URL_INVALID` cases (D38), the exemption, the resolvers, and the IP-literal parser.
- `backend/tests/ssrf/fakes.py`: `FakeResolver` (fixed answers, records every lookup).
  `conftest.py` adds a socket guard that fails any test that tries real DNS or a connection.
- Run: `make test-ssrf`. Rows left for later tasks: redirect to a private address (T1.4);
  fetched from the first validated IP only, and `HTTP_PROXY` ignored (T1.3/T2.1).

## Known limitations

- `check_target` is synchronous and `SystemResolver` blocks; the async fetcher must call it
  in a worker thread (T2.1).
- Pinning is only promised here: `Target.addresses` carries the validated addresses, and
  connecting to them is T1.3.
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
- *How do the tests prove no network was used?* The fake resolver records every lookup, and
  the socket guard fails the test on any real DNS call or connect.
