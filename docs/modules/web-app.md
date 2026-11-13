# Module: Web app screens, submit and polling (M6, task T1.6)

Owner: Divyesh (track C, D16) · Reviewer: TBD · Phase: B · Last updated: 2026-10-24

## What it does (2–3 sentences, plain language)

The browser app a user actually sees: paste a link, press "Check link", watch "Checking… 4 s",
then read the result. It talks to the backend with plain `fetch` (today the backend answers from
the `MockExecutor`), polls until the scan is done, and shows one of the style guide's screens:
report, unable to verify, rejected, unsupported, or an error/busy screen.

## Inputs and outputs
- Input: the text typed by the user; `202` / `ScanResult` / `ErrorBody` JSON from `POST /api/scans` and `GET /api/scans/{id}`.
- Output: rendered screens. The browser keeps only the recent-scans list and the light / dark choice in localStorage.

## How it works (5–10 lines; the steps you would draw on a whiteboard)

1. `App.tsx` holds one `Screen` value: `home`, `checking`, `report` or `error`.
2. Submit → `submitScan()` (`api/client.ts`) POSTs the raw text; the backend cleans and validates it.
3. `pollUntilDone()` (`api/poll.ts`) waits `poll_after_ms`, GETs the scan, and repeats with the wait ×1.5 up to 2 s until `state` is `done`.
4. Every failure becomes an `ApiError` with a `kind`: `input` (our own 400 message, shown under the input), `unreachable` (fetch threw), `busy` (503), `server` (500, 404, unreadable JSON, unknown schema major).
5. `ReportScreen` picks the layout from `display_verdict` only (D4): band + headline, then claimed vs actual, why, where the link went, and collapsed details for scanned results; hints for unable (`screens/hints.ts`, keyed by reason code, D33); the "protects your network" note for rejected.
   The report (T2.6, spec §10): claimed vs actual shows the claimed name with where it came from (`name_source`), the content type, the detected label with its confidence, and the 16-byte hex strip with the signature bytes highlighted; Details shows final site and address, link type, what was read, signals not checked, confidence, score, timings and engine/rules versions.
6. URLs are mono text via `UrlText`: middle-truncated with "Show all", "Copy URL", never a link.
7. All remote text goes through React text nodes and `showInvisible()`, so HTML stays text and bidi characters show as `\u202E` (the escape text, never the character itself).
8. Demo links (D79): `src/demoLinks.ts` lists nine demo links, one per demo scenario. `App` passes them to `HomeScreen` only when `SHOW_DEMO_LINKS` is true, which is `import.meta.env.MODE === 'demo'` (`npm run dev:demo`). Each row is a button that calls the normal `onSubmit`, so a demo link is scanned exactly like a pasted one.
9. Theme button (D81): the shared header in `App.tsx` holds a "Dark mode" / "Light mode" button on every screen. `lib/theme.ts` picks the start theme (saved choice, else the system setting), sets `data-theme` on `<html>` and saves the choice in localStorage; `main.tsx` applies it before the first render so there is no flash.

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
- `src/screens/HomeScreen.test.tsx`: demo links are off outside demo mode, hidden when none are passed, listed as buttons (never links) with their URLs, one click submits the URL, and every link points only at the demo server, the metadata address or a magnet link.
- `src/screens/ReportScreen.test.tsx` (D80): the read / not-read bar (shown for a partial scan with a known size, hidden when the size is unknown or the verdict differs), "No findings.", the Details toggle with `aria-expanded`, and the tinted Actual cell only when the detected type is the problem.
- `src/lib/theme.test.tsx` (D81): system setting used without a saved choice; a saved choice wins and junk is ignored; the button names the other mode, switches `data-theme` and saves it; it sits in the shared header.
- `src/App.test.tsx` (fake `fetch`, no backend): submit → checking → report; every report section; URLs never clickable; check another link; unable (hints, check again, never "Safe"); rejected (no details); unsupported (names the type); unknown reason code; inline 400 errors keep focus; unreachable + try again; busy without auto-retry; 500 on submit and while polling; hostile filename `<img src=x onerror=alert(1)>` rendered as text; hostile URL, headline and reason text; RTL override escaped.
- `src/App.test.tsx` (T2.6): "renders every field of a real result": acceptance row 9 (2-hop chain to the disguised hello PE) checked field by field, including the exact hex bytes and which two are highlighted; unchecked signals listed in Details.
- `src/screens/hints.test.ts`, `src/lib/text.test.ts` (middle truncation).

## Known limitations

- The app calls the backend's real `POST /api/scans` and `GET /api/scans/{id}`, but the backend still answers from the `MockExecutor` until T2.4. The full screen set (360 px checklist, keyboard pass) comes in T3.2.
- The report's "every field" test uses a hand-written row-9 result (`DEMO_DISGUISED_CHAIN`); T3.2 replaces it with one captured from the real executor.
- Not shown on purpose: `schema_version`, `scan_id`, `state`, `status` and `verdict` (the screen uses `display_verdict`, D4), `normalized_url`, the timestamps, the scope byte counts (the scope label says it in words), and each reason's weight, group and evidence (the message already says it).
- Example links on Home (demo profile only, spec §10) are not shown yet: the web app has no way to know the backend profile.
- The busy screen does not count down `Retry-After`; it only says to try again in a few seconds.
- No client-side time limit while polling: it relies on the backend's overall scan timeout (T2.4).
- The `/` header link reloads the page, which is fine because nothing is kept between scans.

## Likely viva questions (and your short answers)

- *How do you stop XSS from a filename like `<img onerror>`?* React puts it in a text node, never HTML; we never use `dangerouslySetInnerHTML`; a test checks no `<img>` appears.
- *Why poll instead of WebSockets?* The contract is async with polling (D3); it is simple and works the same for the future extension.
- *What happens if the server is down?* `fetch` throws, we show "Can't reach the LinkGuard server. Start it with `make dev`…" and a "Try again" button.
- *Why is the web app not deciding "Safe"?* The backend computes `display_verdict` (D4); the web only maps it to words and colour.
- *Why does polling back off?* To ask often at first (fast scans feel instant) but not hammer the server during slow scans.
