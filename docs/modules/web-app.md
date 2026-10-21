# Module: Web app screens, submit and polling (M6, task T1.6)

Owner: Divyesh (track C, D16) · Reviewer: TBD · Phase: B · Last updated: 2026-10-19

## What it does (2–3 sentences, plain language)

The browser app a user actually sees: paste a link, press "Check link", watch "Checking… 4 s",
then read the result. It talks to the backend with plain `fetch` (today the backend answers from
the `MockExecutor`), polls until the scan is done, and shows one of the style guide's screens:
report, unable to verify, rejected, unsupported, or an error/busy screen.

## Inputs and outputs
- Input: the text typed by the user; `202` / `ScanResult` / `ErrorBody` JSON from `POST /api/scans` and `GET /api/scans/{id}`.
- Output: rendered screens only. Nothing is stored in the browser.

## How it works (5–10 lines; the steps you would draw on a whiteboard)

1. `App.tsx` holds one `Screen` value: `home`, `checking`, `report` or `error`.
2. Submit → `submitScan()` (`api/client.ts`) POSTs the raw text; the backend cleans and validates it.
3. `pollUntilDone()` (`api/poll.ts`) waits `poll_after_ms`, GETs the scan, and repeats with the wait ×1.5 up to 2 s until `state` is `done`.
4. Every failure becomes an `ApiError` with a `kind`: `input` (our own 400 message, shown under the input), `unreachable` (fetch threw), `busy` (503), `server` (500, 404, unreadable JSON, unknown schema major).
5. `ReportScreen` picks the layout from `display_verdict` only (D4): band + headline, then claimed vs actual, why, where the link went, and collapsed details for scanned results; hints for unable (`screens/hints.ts`, keyed by reason code, D33); the "protects your network" note for rejected.
6. URLs are mono text via `UrlText`: middle-truncated with "Show all", "Copy URL", never a link.
7. All remote text goes through React text nodes and `showInvisible()`, so HTML stays text and bidi characters show as `\u202E` (the escape text, never the character itself).

## Why it is designed this way (the decision and the simpler/harder alternative you rejected)

- A tiny state machine in `App` instead of a router library: four screens, no URLs to share (no history API, D17).
- Polling is a plain async loop with `getScan` and `wait` passed in, so it is tested without timers or a server. Rejected: `setInterval` (harder to stop, overlapping requests).
- No automatic retry on errors or 503 (D33): the user presses "Try again", which resubmits the same text.
- The API address is `VITE_API_BASE`, default `http://127.0.0.1:8000`; the backend already allows CORS `*` without credentials. Rejected: a Vite dev proxy (one more moving part to explain).
- Every reason row shows its code next to the message, so an unknown code is automatically a "generic card" (code + message) with no list to keep in sync with the registry.
- Tunable numbers (poll ceiling, backoff factor, URL display length) are in `src/config.ts`.

## How it is tested (test files, acceptance rows it covers)

- `src/api/poll.test.ts`: polls until done; backoff sequence 500, 750, 1125, 1688, 2000…; ceiling cap; an error stops polling.
- `src/api/client.test.ts`: POST body and URL; unknown fields ignored; 400 input codes; unreachable; 503 busy; 500 / other 400 / non-JSON / 404 / schema 2.0 → server error.
- `src/App.test.tsx` (fake `fetch`, no backend): submit → checking → report; every report section; URLs never clickable; check another link; unable (hints, check again, never "Safe"); rejected (no details); unsupported (names the type); unknown reason code; inline 400 errors keep focus; unreachable + try again; busy without auto-retry; 500 on submit and while polling; hostile filename `<img src=x onerror=alert(1)>` rendered as text; hostile URL, headline and reason text; RTL override escaped.
- `src/screens/hints.test.ts`, `src/lib/text.test.ts` (middle truncation).

## Known limitations

- Wired to the mock backend only; the real endpoint and the complete report page come in T2.6, the full screen set (360 px checklist, keyboard pass) in T3.2.
- Example links on Home (demo profile only, spec §10) are not shown yet: the web app has no way to know the backend profile.
- The busy screen does not count down `Retry-After`; it only says to try again in a few seconds.
- No client-side time limit while polling: it relies on the backend's overall scan timeout (T2.4).
- The `/` header link reloads the page, which is fine because nothing is kept between scans.

## Likely viva questions (and your short answers)

- *How do you stop XSS from a filename like `<img onerror>`?* React puts it in a text node, never HTML; we never use `dangerouslySetInnerHTML`; a test checks no `<img>` appears.
- *Why poll instead of WebSockets?* The contract is async with polling (D3); it is simple and works the same for the future extension.
- *What happens if the server is down?* `fetch` throws, we show "Can't reach the LinkGuard server. Start it with `make dev`…" and a "Try again" button.
- *Why is the web app not deciding "Safe"?* The backend computes `display_verdict` (D4); the web only maps it to words, icon and colour.
- *Why does polling back off?* To ask often at first (fast scans feel instant) but not hammer the server during slow scans.
