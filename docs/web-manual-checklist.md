# Web app manual verification checklist (task T3.2, spec §10)

This checklist accompanies the automated Vitest suite (`web/src/App.test.tsx`,
`web/src/lib/recentScans.test.ts`, `web/src/theme/contrast.test.ts`,
`web/src/styleguide/StyleGuide.test.tsx`).

## 1. All 7 screens and states

- [x] **Screen 1 — Home**: Title (`LinkGuard`), one-line summary, labelled `Link to check` input, `Check link` button, `What we check` list, and `Recent scans` list (when `localStorage` has entries) with `Clear` and `Check again` buttons.
- [x] **Screen 2 — Checking**: Shows `Checking… N s` and the middle-truncated mono URL inside `aria-live="polite"`; `Check link` button is not present while in flight.
- [x] **Screen 3 — Report (`SAFE`, `NO_ISSUES_IN_CHECKED_PART`, `SUSPICIOUS`, `UNSAFE`)**:
  - Verdict band with both icon and word (never colour alone) + headline.
  - `Claimed vs actual` panel with claimed name, `name_source` caption, `content_type`, detected label, confidence, and 16-byte `First bytes` hex strip with signature bytes highlighted.
  - `Why` list with severity badge, message, and reason code (unknown reason codes render as generic card).
  - `Where the link went` numbered list with non-clickable URL, `Copy URL` button, HTTP status, and address class.
  - Collapsed `Details` disclosure showing final site (with punycode for IDNs), final address, link type, what was read (`scope.label`), confidence, score, timings, and engine/rules versions.
- [x] **Screen 4 — Unable to verify (`UNABLE_TO_VERIFY`)**: Neutral grey band, headline reason, `What you can try` hints keyed by reason code, `Check again` and `Check another link` buttons; never says or implies "Safe".
- [x] **Screen 5 — Rejected (`REJECTED`)**: Purple band (`Not scanned: blocked address`), plain-language explanation, "This protects your computer and local network..." note, no internal IP/rule details; shows `Where the link went` only when blocked at a redirect hop (`SSRF_BLOCKED_AT_HOP`).
- [x] **Screen 6 — Unsupported (`UNSUPPORTED`)**: Dashed outline band (`Not supported yet`), names the link type (`Magnet links`, `Torrent files`, `FTP links`).
- [x] **Screen 7 — Error / busy**: Plain alert panel (no verdict colours) for server unreachable (`Start it with make dev...`), HTTP 503 `SERVER_BUSY` (`LinkGuard is checking other links...`), and HTTP 500 (`Something went wrong...`), with manual `Try again` and `Check another link` buttons.

## 2. Responsive layout at 360 px width

- [x] Input and `Check link` button stack vertically (`flex-col sm:flex-row`) with full-width tap targets and no horizontal scrollbar at 360 px viewport width.
- [x] Hex strip (`HexStrip.tsx`) wraps cleanly into two rows of 8 bytes at 360 px.
- [x] Long URLs and filenames middle-truncate (`URL_DISPLAY_CHARS = 60`) with `Show all` / `Show less` toggle and `break-all` so they never overflow a 360 px container.

## 3. Keyboard navigation, focus, and accessibility

- [x] Initial load and 400 input errors (`URL_EMPTY`, `URL_TOO_LONG`, `URL_MULTIPLE`) place focus in the `Link to check` input (`aria-invalid="true"`, `aria-describedby="link-error"`).
- [x] Every interactive control (`input`, `button`, `summary`, header `a`) is reachable via `Tab` / `Shift+Tab` and displays a 2 px `brand` `:focus-visible` outline (`index.css`).
- [x] Landmarks (`<header>`, `<main aria-live="polite">`, `<footer>`, labelled `<section aria-labelledby="...">`) are present.
- [x] Every light and dark colour pair passes WCAG AA (≥ 4.5:1 text contrast, verified automatically in `src/theme/contrast.test.ts`).

## 4. Dark mode & offline operation

- [x] Dark mode tokens activate automatically via `@media (prefers-color-scheme: dark)` in `src/index.css`.
- [x] All fonts (`@fontsource/ibm-plex-sans`, `@fontsource/ibm-plex-mono`) and icons (`lucide-react`) are bundled locally with zero CDN requests.
