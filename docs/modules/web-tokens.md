# Module: Web tokens, components and /styleguide (M6, task T0.10)

Owner: TBD (track C, D16 open) · Reviewer: TBD · Phase: A · Last updated: 2026-10-17

## What it does (2–3 sentences, plain language)

Sets up Tailwind CSS with only the colours, type scale and radii from `docs/ui-style-guide.md`,
in light and dark mode, with fonts bundled from npm. Adds the shared report components (verdict
badge, verdict band, hex strip, claimed-vs-actual panel) and a dev-only `/styleguide` page that
shows every state side by side in both themes.

## Inputs and outputs
- Input: `web/src/index.css` (tokens), mock data in `web/src/styleguide/mockData.ts`.
- Output: utilities like `bg-paper`, `text-unsafe-fg`, `rounded-panel`, `text-verdict`; components in `web/src/components/`.

## How it works (5–10 lines; the steps you would draw on a whiteboard)

1. Each colour is a CSS variable (`--lg-paper`), light values on `:root`.
2. Dark values apply when the system is dark, or inside `data-theme="dark"` (used by `/styleguide`).
3. `@theme inline` maps them to Tailwind colours, and Tailwind's default palette is removed, so only guide colours exist.
4. `verdicts.ts` maps each `display_verdict` to its exact label, lucide icon and colour classes.
5. `HexStrip` splits `first_bytes_hex` into pairs and highlights the `signature` bytes; caption names them.
6. `ClaimedVsActual` shows remote values as text only, with invisible characters shown as escapes (`showInvisible`).
7. `main.tsx` renders `/styleguide` only when `import.meta.env.DEV`; the production build drops it (verified: 0 occurrences in the bundle).

## Why it is designed this way (the decision and the simpler/harder alternative you rejected)

- Tokens from one file, palette restricted: nobody can use a colour the guide doesn't have.
- Text-input outline uses `muted`, not `line`: `line` is 1.29:1 against `paper`, below WCAG 1.4.11's 3:1 (team: please add this to the style guide).
- Rejected: a component library (CLAUDE.md) and CDN fonts (offline demo).
- TypeScript 5.9 instead of 6 (D28): openapi-typescript needs it; `strict` and `DOM.Iterable` set explicitly.

## How it is tested (test files, acceptance rows it covers)

- `src/theme/contrast.test.ts` (42): computes WCAG contrast from the real `index.css` for every text pair (≥ 4.5:1) and the focus ring and input outline (≥ 3:1), in light and dark; the two dark copies must match; values match the guide.
- `src/components/components.test.tsx` (17): exact labels plus an icon for all seven verdicts; Safe and No-issues look different; hex highlight on exactly the signature bytes; null-signature caption; hostile `<img onerror>` filename rendered as text; RTL override shown escaped.
- `src/lib/text.test.ts` (4), `src/styleguide/StyleGuide.test.tsx` (1): every state in both themes.
- Visual check: headless Chrome screenshots at 1440 px and a true 360 px (iframe); a squeezed icon on wrapped labels was fixed (`shrink-0`).

## Known limitations

- Wireframes (team task) are not in `docs/wireframes/` yet, so layouts follow the guide's ASCII sketches only.
- Middle-truncation of long URLs and "Copy URL" come with the report page (T1.6/T2.6).

## Likely viva questions (and your short answers)

- *How does dark mode work?* CSS variables change value under `prefers-color-scheme: dark`; components only use the variable names.
- *How did you check accessibility?* A test computes WCAG contrast ratios from the real CSS for every pair we use.
- *How is the verdict shown to colour-blind users?* Always word plus icon, never colour alone.
- *Why show `\u202E` instead of the real name?* The override character reverses the text and hides the real extension.
