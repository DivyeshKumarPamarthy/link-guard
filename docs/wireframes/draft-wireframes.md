# Wireframes: draft for team review (T0.10)

Status: **DRAFT, not approved.** Drafted by Claude Code on 2026-10-19 from
`docs/ui-style-guide.md`, `docs/phase1-spec.md` §10 and the contract fields in §2.
The team corrects these (edit this file, or put sketches/Figma exports next to it), then
records approval at the bottom. T0.10 is ticked only after that.

How to read them: low fidelity, desktop width (content column max 720 px, left-aligned).
`[ ... ]` = input or button, `( )` = icon, `‹ ›` = mono text (URLs, filenames, hex).
Every screen keeps the same header so the user always sees where they are.
**Decide:** lines are open questions for the team.

---

## Shared frame (all screens)

```
LinkGuard                                              ← header: title, links to Home
────────────────────────────────────────────────────
<main aria-live="polite">  screen content  </main>
────────────────────────────────────────────────────
Runs on this computer only · engine 1.0.0 · rules 1.0.0   ← footer, small muted text
```

- Page padding 16 px (mobile), 32 px (desktop). No shadows; panels have a 1 px `line` border.
- Results never show the scanned URL as a link: mono text plus a [ Copy URL ] button.
- **Decide:** footer versions on every screen, or only inside report "Details"?

---

## 1. Home

```
LinkGuard                                                   ← 40/46 title
Check a download link before you open the file.

Link to check                                               ← visible label
[ ‹https://…›                                 ] [ Check link ]
  error text appears here, e.g. "Paste a link to check."

What we check
  The file's real type, read from its first bytes
  Where shortened links really lead
  Whether the address is safe to contact

Example links (demo profile only)                           ← spec §10
  ‹http://a.demo.test:8081/f/sample.pdf›          [ Use ]
  ‹http://a.demo.test:8081/disguised/movie.mp4›   [ Use ]
```

- 400 errors show inline under the input (URL_EMPTY "Paste a link to check.", URL_TOO_LONG,
  URL_MULTIPLE "Paste one link at a time."); focus stays in the input.
- [ Check link ] is disabled while a scan is in flight.
- 360 px: input and button stack vertically, button full width.
- **Decide:** the recent-scans list (P1, localStorage) goes below "What we check"?

## 2. Checking

```
Checking…  4 s                                              ← progress text, live region
‹https://short.example/…/movie.mp4›                         ← mono, middle-truncated
```

- Nothing else on the screen (style guide). Elapsed seconds update every second.
- Polls `GET /api/scans/{id}` every `poll_after_ms`, backing off to 2 s.
- **Decide:** show a [ Cancel ] link? (Only stops polling; the backend has no cancel.)

## 3. Report (Safe / No issues in the checked part / Suspicious / Unsafe)

```
┌──────────────────────────────────────────────────────┐
│ (octagon ×) Unsafe                                   │  ← verdict band, verdict tint
│ Blocked: file named .mp4 is actually a Windows       │  ← headline (registry text)
│ executable                                           │
└──────────────────────────────────────────────────────┘

Claimed vs actual                                          ← the one bold element
  Claimed      ‹movie.mp4› · ‹video/mp4›
  Actual       Windows executable
  First bytes  [4d 5a] 90 00 03 00 00 00 04 00 00 00 ff ff 00 00
               Highlighted: MZ (Windows executable)

Why
  (●) High   The file is named .mp4 but its content is a Windows executable.
  (○) Info   The link ended on a different site: files.example.

Where the link went                                        ← numbered list
  1  ‹short.example/abc›          302   public   [ Copy URL ]
  2  ‹files.example/movie.mp4›    200   public   [ Copy URL ]

▸ Details                                                  ← collapsed by default
    What was read   Whole file checked (47 KB)
    Confidence      High
    Score           70 / 100
    Timings         812 ms total, 640 ms fetch
    Engine / rules  1.0.0 / 1.0.0

[ Check another link ]
```

- Same layout for all four verdicts; only the band (colour, icon, word) and headline change.
- "No issues in the checked part" always states the scope in its headline
  ("No issues found in the checked part (first 5 MB of 200 MB)").
- Unknown reason codes render as a generic card: code + message.
- Long URLs are middle-truncated with an expand control; control/bidi characters are shown
  escaped (U+202E is displayed as the six visible characters backslash, u, 2, 0, 2, E).
- IDN hosts show both forms: `bücher.example (xn--bcher-kva.example)`.
- 360 px: the hex strip wraps to two lines of 8 bytes; redirect rows stack (URL on its own line).
- **Decide:** show the score at all, or only in Details? (Guide puts it in Details.)

## 4. Unable to verify

```
┌──────────────────────────────────────────────────────┐
│ (circle ?) Unable to verify                          │  ← neutral grey, not a warning
│ The server answered 404: the file is not there.      │
└──────────────────────────────────────────────────────┘

What you can try
  Check the link is complete and still works in your browser.
  If the site needs a login, LinkGuard can't check it.

Where the link went            (if any hops were made)
▸ Details                      (what was read: "Nothing was read")

[ Check again ]   [ Check another link ]
```

- The "what you can try" text depends on the reason code (404/410, 401/403, timeout, TLS,
  web page, redirect loop). **Decide:** wording per code, in the registry or in the web app?
- Never says or implies "safe".

## 5. Rejected (blocked address)

```
┌──────────────────────────────────────────────────────┐
│ (crossed circle) Not scanned: blocked address        │
│ LinkGuard won't contact this address because it      │
│ points inside a private network.                     │
└──────────────────────────────────────────────────────┘

This protects your computer and local network. Links to your own
computer, your router or company systems are never fetched.

[ Check another link ]
```

- No internal details: no resolved IP, no "which rule fired" beyond the message.
- For SSRF_BLOCKED_AT_HOP, show "Where the link went" up to the blocked hop.

## 6. Unsupported

```
┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐
  (dashed circle) Not supported yet                        ← dashed outline, no tint
  Magnet links aren't supported yet; they are planned
  for a later phase.
└ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘

[ Check another link ]
```

- Names the link type: magnet links, torrent files, FTP links.

## 7. Error / busy

Three variants; same layout, plain panel (no verdict colours: these are not verdicts).

```
Can't reach the LinkGuard server.
Start it with `make dev`, then try again.             [ Try again ]

LinkGuard is checking other links.
Try again in a few seconds.                           [ Try again ]   ← 503, honours Retry-After

Something went wrong on the LinkGuard server.
Try again; if it keeps happening, check the server terminal.   [ Try again ]   ← 500
```

- **Decide:** for 503, retry automatically after `Retry-After`, or wait for the user?

---

## Review and approval

| Screen | Changes requested | Approved by | Date |
| --- | --- | --- | --- |
| 1 Home | | | |
| 2 Checking | | | |
| 3 Report | | | |
| 4 Unable to verify | | | |
| 5 Rejected | | | |
| 6 Unsupported | | | |
| 7 Error / busy | | | |
