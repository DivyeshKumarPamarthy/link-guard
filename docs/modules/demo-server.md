# Module: Demo server (M7, task T1.1)

Owner: Divyesh (track C, D16) · Reviewer: TBD · Phase: B · Last updated: 2026-10-19

## What it does (2–3 sentences, plain language)

A small local web server that pretends to be every kind of download server LinkGuard must
handle: a normal file, a 200 MB file, a server that drips bytes or drops the connection,
redirect chains and loops, error pages, a web page. The fetcher, the end-to-end tests and the
demo all use it, so nothing needs the internet or real malware.

## Inputs and outputs
- Input: `DEMO_*` environment variables (ports, sizes, timings); sample files in `samples/`.
- Output: three loopback listeners: HTTP `:8081`, HTTPS `:8443` (valid for a/b/c.demo.test), HTTPS `:8444` (certificate for another host).

## Endpoints

| Path | Imitates | Used by |
| --- | --- | --- |
| `/f/{name}` | A normal file with its real Content-Type; Range and HEAD supported | rows 1, 3–6, 8–9, 21 |
| `/big?range=yes\|no` | 200 MB MP4-shaped stream generated on the fly; `no` ignores Range | rows 2, 13 |
| `/slow` | Headers, then 1 byte every 2 s | row 14 |
| `/reset` | Promises 1 MB, sends 4 KB, drops the connection | T2.1 interrupted stream |
| `/chunked` | No Content-Length (chunked transfer encoding) | T2.1 |
| `/gzip/{name}` | Gzip-compressed despite `Accept-Encoding: identity` | row 20 |
| `/redirect/chain?n=&to=` | `n` redirects across a.demo.test → b → c, then `to` | rows 8–9 |
| `/redirect/loop` | A → B → A (relative Locations) | row 10 |
| `/redirect/internal` | 302 to `http://127.0.0.1/` | row 11 |
| `/redirect/https-to-http` | HTTPS → HTTP downgrade | `REDIR_DOWNGRADE` |
| `/status/{code}` | 401, 403, 404, 410, 429 (Retry-After), 500 | rows 15–16 |
| `/page` | An HTML web page | row 17 |
| `/empty` | 200 with a 0-byte body | row 19 |

## How it works (5–10 lines; the steps you would draw on a whiteboard)

1. `python -m demo_server` loads `DemoSettings` and, if `demo/certs/` is empty, generates a fresh test CA plus two server certificates.
2. One Starlette app is served by three uvicorn servers in one asyncio loop (HTTP, HTTPS, wrong-cert HTTPS), all on 127.0.0.1.
3. `/f` uses Starlette's `FileResponse`, which handles Range and HEAD; names are plain file names, never paths.
4. `/big` computes bytes from their offset (MP4 header, then a repeating 0–255 pattern), so any range is generated without a file and memory stays at one 64 KB chunk.
5. `/reset` raises an exception mid-body; uvicorn then closes the socket, which a client sees as an incomplete download.
6. `/redirect/chain` reads the Host it was called on and redirects to the next demo hostname on the same port.
7. The backend reaches `a.demo.test` etc. through `LG_STATIC_HOSTS` and exact `LG_SSRF_EXEMPT` pairs, only in the `test`/`demo` profile (D2).

## Why it is designed this way (the decision and the simpler/harder alternative you rejected)

- Separate uv project (D35): demo-only packages (cryptography) never enter the backend.
- A second HTTPS port for the wrong certificate (D34): uvicorn cannot choose a certificate per hostname on one port.
- The CA private key is never saved, so nobody can issue further certificates with it, even if the folder leaks.
- Rejected: real-internet test URLs (flaky, can change, and tests must stay offline) and committed sample binaries (antivirus, repo size).

## How it is tested (test files, acceptance rows it covers)

- `demo/tests/test_endpoints.py` (47, in-process): every endpoint, Range variants (start, middle, suffix, past the end, ignored), HEAD, missing sample message, path-escape attempts, chain a → b → c, bad chain parameters (open redirect refused), statuses, empty body.
- `demo/tests/test_listeners.py` (12, real sockets on free ports): bound to 127.0.0.1 only, `/reset` drops after exactly 4096 bytes, chunked encoding, real-time slow drip, 200 MB stream read lazily, TLS valid for a/b/c.demo.test, hostname mismatch refused, wrong-cert listener refused (row 22), test CA not trusted by default, CA key never written.
- Tests may only connect to 127.0.0.1 (pytest-socket `--allow-hosts`).
- Manual: `make demo-server`, then curl on all three ports.

## Known limitations

- `/disguised/{name}`, `/cd/{variant}` and `/index` (spec §11) come with T1.5/T2.6, together with the samples they serve.
- `/reset` prints a traceback in the demo server's terminal; that is the deliberate drop.
- `/chunked` serves a PDF-shaped body (`%PDF-` header), not a complete PDF document.

## Likely viva questions (and your short answers)

- *How do you test without the internet?* Every scenario is a local endpoint; the backend maps the demo hostnames to 127.0.0.1 in the test profile only.
- *How do you serve 200 MB without a 200 MB file?* Each byte is computed from its offset, so the server generates any range on demand.
- *How do you test a bad certificate?* A second listener presents a certificate for a different hostname; a correct client must refuse it.
- *Isn't the demo server an SSRF hole?* It is only reachable on 127.0.0.1, and the backend reaches it only through exact host:port exemptions in the test/demo profile.
