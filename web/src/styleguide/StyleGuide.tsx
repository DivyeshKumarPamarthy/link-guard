// Dev-only page at /styleguide (T0.10): every verdict state and the claimed-vs-actual
// panel, shown side by side in light and dark mode. Not included in production builds.
import { ClaimedVsActual } from '../components/ClaimedVsActual.tsx'
import { VerdictBadge } from '../components/VerdictBadge.tsx'
import { VerdictBand } from '../components/VerdictBand.tsx'
import { ALL_VERDICTS } from '../components/verdicts.ts'
import { DISGUISED_EXE, GENUINE_PNG, SAMPLE_HEADLINES, SPOOFED_NAME, UNKNOWN_BYTES } from './mockData.ts'

const COLOUR_TOKENS = ['paper', 'surface', 'ink', 'muted', 'line', 'brand'] as const
// Written out in full so Tailwind generates each class.
const SWATCH_CLASS: Record<(typeof COLOUR_TOKENS)[number], string> = {
  paper: 'bg-paper',
  surface: 'bg-surface',
  ink: 'bg-ink',
  muted: 'bg-muted',
  line: 'bg-line',
  brand: 'bg-brand',
}

function ThemeColumn({ theme }: { theme: 'light' | 'dark' }) {
  return (
    <section
      data-theme={theme}
      aria-label={`${theme} mode`}
      className="min-w-0 space-y-8 bg-paper p-4 text-ink md:p-8"
    >
      <h2 className="text-section font-semibold">{theme === 'light' ? 'Light mode' : 'Dark mode'}</h2>

      <div className="space-y-2">
        <h3 className="font-medium text-muted">Colours</h3>
        <ul className="flex flex-wrap gap-3">
          {COLOUR_TOKENS.map((token) => (
            <li key={token} className="flex items-center gap-2 text-small">
              <span className={`size-6 rounded-control border border-line ${SWATCH_CLASS[token]}`} />
              {token}
            </li>
          ))}
        </ul>
      </div>

      <div className="space-y-1">
        <h3 className="font-medium text-muted">Type</h3>
        <p className="text-title font-semibold">LinkGuard</p>
        <p className="text-verdict font-semibold">Verdict word</p>
        <p className="text-section font-semibold">Section title</p>
        <p>Body text in IBM Plex Sans.</p>
        <p className="text-small text-muted">Small secondary text</p>
        <p className="font-mono">https://files.example/movie.mp4 · 4d 5a 90 00</p>
      </div>

      <div className="space-y-2">
        <h3 className="font-medium text-muted">Verdict badges</h3>
        <ul className="flex flex-wrap gap-2">
          {ALL_VERDICTS.map((v) => (
            <li key={v}>
              <VerdictBadge verdict={v} />
            </li>
          ))}
        </ul>
      </div>

      <div className="space-y-3">
        <h3 className="font-medium text-muted">Verdict bands</h3>
        {ALL_VERDICTS.map((v) => (
          <VerdictBand key={v} verdict={v} headline={SAMPLE_HEADLINES[v]} />
        ))}
      </div>

      <div className="space-y-3">
        <h3 className="font-medium text-muted">Claimed vs actual</h3>
        <ClaimedVsActual file={DISGUISED_EXE} verdict="UNSAFE" />
        <ClaimedVsActual file={GENUINE_PNG} verdict="SAFE" />
        <ClaimedVsActual file={UNKNOWN_BYTES} verdict="UNABLE_TO_VERIFY" />
        <ClaimedVsActual file={SPOOFED_NAME} verdict="UNSAFE" />
      </div>

      <div className="space-y-2">
        <h3 className="font-medium text-muted">Controls (Tab to see the focus ring)</h3>
        <form className="flex flex-col gap-2 sm:flex-row" onSubmit={(e) => e.preventDefault()}>
          <label className="sr-only" htmlFor={`link-${theme}`}>
            Link to check
          </label>
          {/* Input border uses `muted`, not `line`: WCAG 1.4.11 needs 3:1 for the field outline. */}
          <input
            id={`link-${theme}`}
            className="min-w-0 flex-1 rounded-control border border-muted bg-surface px-3 py-2 font-mono text-ink"
            placeholder="https://…"
          />
          <button type="submit" className="rounded-control bg-brand px-4 py-2 font-medium text-paper">
            Check link
          </button>
        </form>
      </div>
    </section>
  )
}

export function StyleGuide() {
  return (
    <main className="min-h-screen">
      <header className="px-4 py-6 md:px-8">
        <h1 className="text-section font-semibold">LinkGuard style guide (dev only)</h1>
        <p className="text-small text-muted">Tokens from docs/ui-style-guide.md. Mock data only.</p>
      </header>
      <div className="grid lg:grid-cols-2">
        <ThemeColumn theme="light" />
        <ThemeColumn theme="dark" />
      </div>
    </main>
  )
}
