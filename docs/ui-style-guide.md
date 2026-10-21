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

| `display_verdict` | Label shown | Icon idea | Light text / bg | Dark text / bg |
| --- | --- | --- | --- | --- |
| SAFE | Safe | check in shield | #1E7A4C / #E6F3EC | #6CC59A / #173126 |
| NO_ISSUES_IN_CHECKED_PART | No issues in the checked part | half-filled shield | #2E6F7E / #E5F0F2 | #74BCCB / #14303A |
| SUSPICIOUS | Suspicious | triangle with ! | #8A5200 / #FBF0DC | #E8B04B / #352812 |
| UNSAFE | Unsafe | octagon with × | #B3261E / #FBE7E5 | #F2867D / #3A1A18 |
| UNABLE_TO_VERIFY | Unable to verify | circle with ? | #4F5D6C / #EEF1F4 | #A4B0BC / #222D38 |
| REJECTED | Not scanned: blocked address | crossed-out circle | #6A4C93 / #EFEAF6 | #C2A6E8 / #2A2238 |
| UNSUPPORTED | Not supported yet | dashed outline only | #4F5D6C / transparent, dashed `line` border | #A4B0BC / transparent |

Rules: verdict is always word + icon, never colour alone. "No issues in the checked part" is a
different colour from "Safe" on purpose. "Unable to verify" is neutral grey: it is not a warning
and not a pass.

The "No issues in the checked part" headline always says what was read, using the scope label
exactly as the backend sends it (capital letter included, never lower-cased in the UI), e.g.
"No issues found in the checked part (First 5 MB of 200 MB)". Other labels: "Whole file
checked (47 KB)", "First 4 KB (total size unknown)", "3 KB read, but sent compressed",
"Only the server's headers were read", "Nothing was read" (decision D64).

Icons: `lucide-react` (free, tree-shaken, no component library). Same icon per verdict everywhere.

## Type

- **IBM Plex Sans** (400, 500, 600) for all interface text; **IBM Plex Mono** (400, 500) only for
  data the user may copy or compare: URLs, hostnames, filenames, hex bytes, hashes. Load both from
  `@fontsource` so the demo works offline.
- Scale (px / line-height): 13/18 small, 16/24 body, 20/28 section, 28/34 verdict word, 40/46 home
  title. Weights: 600 for the verdict word and section titles, 500 for labels, 400 for body.
- Sentence case everywhere. No all-caps labels, no letter-spaced eyebrows.
- Line length ≤ 72 characters for prose.

## Shape and spacing

- Spacing on a 4 px grid (Tailwind default). Page padding 16 px mobile, 32 px desktop.
- Radius: 6 px inputs and buttons, 10 px panels, 999 px badges. No drop shadows; panels use a 1 px `line` border.
- Content column: max width 720 px, left-aligned.

## Screens (7)

1. Home: title, one-line explanation, link input, "Check link" button, "What we check" (3 short lines).
2. Checking: the submitted URL (mono, middle-truncated), progress text "Checking… 4 s", nothing else.
3. Report (Safe / No issues / Suspicious / Unsafe): layout below.
4. Unable to verify: verdict band + why (e.g. "The server answered 404: the file is not there") + what to try.
5. Rejected: "LinkGuard won't contact this address because it points inside a private network." No internal details.
6. Unsupported: names the link type ("Magnet links aren't supported yet").
7. Error / busy: server unreachable, busy (503), unexpected error — each with what to do next.

### Home

```
LinkGuard
Check a download link before you open the file.

[ https://…                                   ] [ Check link ]

What we check
  The file's real type, read from its first bytes
  Where shortened links really lead
  Whether the address is safe to contact
```

### Report

```
┌──────────────────────────────────────────────────────────┐
│ ⛔ Unsafe                                                  │  ← verdict band (tinted bg)
│ The file is named movie.mp4 but it is a Windows program.  │  ← headline
└──────────────────────────────────────────────────────────┘

Claimed vs actual                                             ← the one bold element
  Claimed   movie.mp4 · video/mp4
  Actual    Windows executable
  First bytes  [4d 5a] 90 00 03 00 00 00 04 00 00 00 ff ff 00 00
               ^^^^^ MZ: the signature of a Windows program

Why
  ● High   Named .mp4 but its content is a Windows executable
  ○ Info   The link ended on a different site: files.example

Where the link went                                           ← numbered: it is a sequence
  1  short.example/abc        302
  2  files.example/movie.mp4  200

Details (collapsed): what was read (scope label), confidence, score, timings, engine version
```

Hex strip: Plex Mono, 16 bytes in pairs; signature bytes get the verdict's tinted background and
an underline, with a one-line caption naming the signature. If `file.signature` is null, show the
bytes with no highlight and the caption "No known signature in the first bytes".

## Copy rules

- Verdict labels exactly as in the verdict table; never "Clean", "Virus-free" or "100% safe".
- Headlines state the finding in plain words; reasons come from the registry messages.
- Errors say what happened and what to do: "Can't reach the LinkGuard server. Start it with `make dev`, then try again." Busy: "LinkGuard is checking other links. Try again in a few seconds."
- Buttons name the action: "Check link", "Check again", "Copy URL". No "→" suffixes.
- Never render a scanned URL as a clickable link; show it as mono text with a "Copy URL" button.

## Motion and accessibility

- One motion only: the verdict band fades in when the result arrives (150 ms). Respect `prefers-reduced-motion`.
- Visible focus ring (2 px `brand`), full keyboard use, labelled landmarks, `aria-live="polite"` on the progress/verdict region.
- Works at 360 px wide; dark mode follows the system setting.
