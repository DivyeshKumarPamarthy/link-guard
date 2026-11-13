# LinkGuard UI style guide

Authoritative for the web app (and, in Phase C, the extension popup). Tailwind tokens must come
from this file; do not invent colours or sizes in components.

## Concept: an inspection slip

LinkGuard's result should read like a customs inspection slip: a clear verdict first, then the
evidence. Spend the visual boldness in **one place, the "claimed vs actual" panel**, which shows
what the file says it is next to what its first bytes prove it is, with the identifying bytes
highlighted in a hex strip. Everything else is quiet, left-aligned and plain.

## Colour tokens

All text/background pairs below were checked at ≥ 4.5:1 (WCAG AA). Re-check any new pair.

| Token | Light | Dark | Use |
| --- | --- | --- | --- |
| `paper` | #F5F7F9 | #0F1720 | Page background |
| `surface` | #FFFFFF | #16212C | Panels, input |
| `ink` | #13202E | #E6EBF0 | Main text |
| `muted` | #5A6878 | #9AA8B6 | Secondary text, labels |
| `line` | #D5DCE3 | #2A3744 | Borders, dividers |
| `brand` | #2F5D8A | #8DB4DD | Primary button, links, focus ring |

Verdict colours (text colour on its tinted background):

| `display_verdict` | Label shown | Light text / bg | Dark text / bg |
| --- | --- | --- | --- |
| SAFE | Safe | #1E7A4C / #E6F3EC | #6CC59A / #173126 |
| NO_ISSUES_IN_CHECKED_PART | No issues in the checked part | #2E6F7E / #E5F0F2 | #74BCCB / #14303A |
| SUSPICIOUS | Suspicious | #8A5200 / #FBF0DC | #E8B04B / #352812 |
| UNSAFE | Unsafe | #B3261E / #FBE7E5 | #F2867D / #3A1A18 |
| UNABLE_TO_VERIFY | Unable to verify | #4F5D6C / #EEF1F4 | #A4B0BC / #222D38 |
| REJECTED | Not scanned: blocked address | #13202E / #EEF1F4, 2 px `ink` border | #E6EBF0 / #222D38, 2 px `ink` border |
| UNSUPPORTED | Not supported yet | #4F5D6C / transparent, dashed `muted` border, `muted` headline | #A4B0BC / transparent |

Rules: the verdict word always carries the meaning, never colour alone. No icons (D79). "No issues in the checked part" is a
different colour from "Safe" on purpose. "Unable to verify" is neutral grey: it is not a warning
and not a pass. "Not scanned: blocked address" is not a verdict on the file (nothing was
fetched), so it gets no risk colour: neutral ink with a 2 px ink border (D79, D80).

The "No issues in the checked part" headline always says what was read, using the scope label
exactly as the backend sends it (capital letter included, never lower-cased in the UI), e.g.
"No issues found in the checked part (First 5 MB of 200 MB)". Other labels: "Whole file
checked (47 KB)", "First 4 KB (total size unknown)", "3 KB read, but sent compressed",
"Only the server's headers were read", "Nothing was read" (decision D64).

No icons, emoji or decorative graphics anywhere (D79). Severity in "Why" is the word alone (High,
Medium, Low, Info).

## Type

- **IBM Plex Sans** (400, 500, 600) for all interface text; **IBM Plex Mono** (400, 500) only for
  data the user may copy or compare: URLs, hostnames, filenames, hex bytes, hashes. Load both from
  `@fontsource` so the demo works offline.
- Scale (px / line-height, D80): 13/20 small, 14/20 label (section headings in `muted`), 16/24 body,
  18/26 lead (verdict headline), 21/28 evidence (claimed name, detected type), 22/28 section
  (error titles), 30/36 title (home title, "Checking… 4 s"), verdict word `clamp(30px, 8vw, 42px)`
  / 1.12. Weights: 600 for the verdict word, titles, labels and buttons, 500 for the claimed name,
  400 for body.
- Section headings ("Claimed vs actual", "Why", "What we check", …) are small 14 px `muted` labels,
  not big titles: the verdict band is the only large element on a report.
- Sentence case everywhere. No all-caps labels, no letter-spaced eyebrows.
- Line length ≤ 72 characters for prose.

## Shape and spacing

- Spacing on a 4 px grid (Tailwind default). Page padding 20 px each side; 56 px above the home
  title, 28 px above the report wordmark; 32–40 px between sections.
- Radius (D80): 3 px badges and byte cells, 4 px inputs and buttons, 6 px panels. No drop shadows;
  panels use a 1 px `line` border. Lists are rows divided by 1 px `line` rules, not cards.
- Buttons are at least 44 px tall (48 px for main actions): primary = `brand` fill; secondary and
  small = transparent with a `muted` border and `ink` text (`web/src/components/buttons.ts`).
- Content column: max width 720 px, left-aligned.

## Screens (7)

1. Home: title, one-line explanation, link input, "Check link" button, "What we check" (3 short lines).
   In demo mode only (`npm run dev:demo`), a "Demo links" panel under the input lists the demo links
   (`web/src/demoLinks.ts`); one click checks a link for real (D79).
2. Checking: the submitted URL (mono, middle-truncated), progress text "Checking… 4 s", nothing else.
3. Report (Safe / No issues / Suspicious / Unsafe): layout below.
4. Unable to verify: verdict band + why (e.g. "The server answered 404: the file is not there") + what to try.
5. Rejected: "LinkGuard won't contact this address because it points inside a private network." No internal details.
6. Unsupported: names the link type ("Magnet links aren't supported yet").
7. Error / busy: server unreachable, busy (503), unexpected error — each with what to do next.

Source design: the Claude Design canvas https://claude.ai/artifact/V2SkKQgpjc91LGw16sYTQN (main page, result page in all
seven verdicts, checking, errors; light, dark and 360 px). The app follows it (D80).

### Home

```
LinkGuard
Check a download link before you open the file.

Link to check
[ https://…                                   ] [ Check link ]

┌ Demo links (demo mode only) ─────────────────────────────┐
│ A genuine PDF                                            │  ← one button per row
│ http://a.demo.test:8081/f/sample.pdf                     │
├──────────────────────────────────────────────────────────┤
│ …                                                        │
└──────────────────────────────────────────────────────────┘

What we check                                                ← rows with dividers
  The file's real type, read from its first bytes
  Where shortened links really lead
  Whether the address is safe to contact

Recent scans                                          Clear
  [Unsafe]                                   [ Check again ]
  http://a.demo.test:8081/redire…/disguised/movie.mp4
```

### Report

```
┌──────────────────────────────────────────────────────────┐
│ Unsafe                                                    │  ← verdict band (tinted bg)
│ Blocked: file named .mp4 is actually a Windows executable │  ← headline
│ [■□□□□□□□□□□□□□□□□□]  Read: first 5 MB · Not read: 195 MB │  ← only on "No issues in the
└──────────────────────────────────────────────────────────┘     checked part" with a known size

Link checked: http://a.demo.test:8081/redire…/movie.mp4
[ Copy URL ] [ Show all ]

Claimed vs actual                                             ← the one bold element
┌───────────────────────────┬───────────────────────────────┐
│ Claimed                   │ Actual            (tinted on   │
│ movie.mp4                 │ Windows executable  Unsafe,    │
│ video/mp4                 │ Certain             Suspicious,│
│ Name from the server's…   │                     Unable)    │
├───────────────────────────┴───────────────────────────────┤
│ First bytes                                                │
│ [4d][5a] 90 00 03 00 00 00   04 00 00 00 ff ff 00 00       │
│ Highlighted: MZ (Windows executable)                       │
└────────────────────────────────────────────────────────────┘

Why                                                           ← "No findings." when empty
  High   The file is named .mp4 but its content is a Windows executable.
         TYPE_MISMATCH_EXEC

What you can try                                              ← Unable to verify only

Where the link went                                           ← numbered: it is a sequence
  1  http://a.demo.test:8081/redirect/chain?n=2&to=…           (full URL, wrapped)
     Status: 302   Address: private

Details                                                Show  ← a button; rows appear when open

[ Check another link ]
```

Hex strip: Plex Mono, 16 bytes in two rows of eight 30 px cells; signature bytes get the
verdict's tinted background, bold and an underline, with a one-line caption naming the signature. If `file.signature` is null, show the
bytes with no highlight and the caption "No known signature in the first bytes".

## Copy rules

- Verdict labels exactly as in the verdict table; never "Clean", "Virus-free" or "100% safe".
- Headlines state the finding in plain words; reasons come from the registry messages.
- Errors say what happened and what to do: "Can't reach the LinkGuard server. Start it with `make dev`, then try again." Busy: "LinkGuard is checking other links. Try again in a few seconds."
- Buttons name the action: "Check link", "Check again", "Copy URL". No "→" suffixes.
- Never render a scanned URL as a clickable link; show it as mono text with a "Copy URL" button.

## Motion and accessibility

- One motion only: the verdict band fades in when the result arrives (150 ms). Respect `prefers-reduced-motion`.
  No hover animations or transitions; hover may only change a colour or underline instantly.
- Visible focus ring (2 px `brand`), full keyboard use, labelled landmarks, `aria-live="polite"` on the progress/verdict region.
- Works at 360 px wide. Dark mode follows the system setting until the user presses the theme
  button: a small "Dark mode" / "Light mode" text button (it names the mode it switches to) at the
  top right of every screen. The choice is kept in this browser's localStorage (D81).
