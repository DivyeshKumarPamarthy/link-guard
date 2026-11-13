// Screen 1: title, one-line explanation, link input, "Check link", the demo links (demo mode
// only), "What we check", and the localStorage recent-scans list (spec §10 P1, D33).
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { primaryButton, smallButton } from '../components/buttons.ts'
import { VerdictBadge } from '../components/VerdictBadge.tsx'
import { URL_DISPLAY_CHARS } from '../config.ts'
import type { DemoLink } from '../demoLinks.ts'
import type { RecentScan } from '../lib/recentScans.ts'
import { middleTruncate, showInvisible } from '../lib/text.ts'

interface Props {
  initialUrl: string
  /** Our own 400 message (e.g. "Paste a link to check."), shown under the input. */
  inputError: string | null
  onSubmit: (url: string) => void
  recentScans?: RecentScan[]
  onClearRecent?: () => void
  onSelectRecent?: (item: RecentScan) => void
  /** Ready-made demo links; App passes them only in demo mode (SHOW_DEMO_LINKS). */
  demoLinks?: DemoLink[]
}

const WHAT_WE_CHECK = [
  "The file's real type, read from its first bytes",
  'Where shortened links really lead',
  'Whether the address is safe to contact',
]

const sectionLabel = 'text-label font-semibold text-muted'

export function HomeScreen({
  initialUrl,
  inputError,
  onSubmit,
  recentScans = [],
  onClearRecent,
  onSelectRecent,
  demoLinks = [],
}: Props) {
  const [url, setUrl] = useState(initialUrl)
  const inputRef = useRef<HTMLInputElement>(null)

  // Focus stays in the input, also after an input error (wireframe 1).
  useEffect(() => {
    inputRef.current?.focus()
  }, [inputError])

  function submit(event: FormEvent) {
    event.preventDefault()
    onSubmit(url)
  }

  return (
    <div className="space-y-10">
      <header className="space-y-2">
        <h1 className="text-title font-semibold tracking-[-0.01em]">LinkGuard</h1>
        <p className="text-[17px] leading-normal text-muted">Check a download link before you open the file.</p>
      </header>

      <form onSubmit={submit} noValidate className="space-y-2">
        <label htmlFor="link" className="block text-label font-semibold">
          Link to check
        </label>
        <div className="flex flex-wrap gap-2">
          <input
            id="link"
            ref={inputRef}
            type="text"
            inputMode="url"
            autoComplete="off"
            autoCapitalize="off"
            spellCheck={false}
            placeholder="https://…"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            aria-invalid={inputError !== null}
            aria-describedby={inputError ? 'link-error' : undefined}
            className="h-12 min-w-0 flex-[1_1_260px] rounded-control border border-muted bg-surface px-3.5 font-mono text-ink placeholder:text-muted"
          />
          <button type="submit" className={primaryButton}>
            Check link
          </button>
        </div>
        {inputError && (
          <p id="link-error" role="alert" className="text-label font-semibold">
            {inputError}
          </p>
        )}
      </form>

      {demoLinks.length > 0 && (
        <section aria-labelledby="demo-links" className="rounded-panel border border-line">
          <div className="space-y-1 px-4 py-3.5">
            <h2 id="demo-links" className={sectionLabel}>
              Demo links
            </h2>
            <p className="text-small text-muted">
              Shown in demo mode only. Each one points at the local demo server and is checked for real.
            </p>
          </div>
          <ul>
            {demoLinks.map((link) => (
              <li key={link.url} className="border-t border-line">
                <button
                  type="button"
                  onClick={() => onSubmit(link.url)}
                  className="flex min-h-11 w-full cursor-pointer flex-col gap-0.75 px-4 py-2.5 text-left"
                >
                  <span className="text-label">{link.label}</span>
                  <span className="font-mono text-xs leading-normal break-all text-muted">{link.url}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section aria-labelledby="what-we-check" className="space-y-2.5">
        <h2 id="what-we-check" className={sectionLabel}>
          What we check
        </h2>
        <ul className="border-b border-line">
          {WHAT_WE_CHECK.map((line) => (
            <li key={line} className="border-t border-line py-2.5">
              {line}
            </li>
          ))}
        </ul>
      </section>

      {recentScans.length > 0 && (
        <section aria-labelledby="recent-scans" className="space-y-2.5">
          <div className="flex items-center justify-between gap-3">
            <h2 id="recent-scans" className={sectionLabel}>
              Recent scans
            </h2>
            {onClearRecent && (
              <button
                type="button"
                onClick={onClearRecent}
                className="min-h-11 cursor-pointer px-1 text-label underline underline-offset-3"
              >
                Clear
              </button>
            )}
          </div>
          <ul>
            {recentScans.map((item) => (
              <li key={item.scan_id} className="flex flex-col gap-2 border-t border-line py-3">
                <div className="flex items-center justify-between gap-3">
                  <VerdictBadge verdict={item.display_verdict} />
                  {onSelectRecent && (
                    <button type="button" onClick={() => onSelectRecent(item)} className={smallButton}>
                      Check again
                    </button>
                  )}
                </div>
                <span className="font-mono text-small break-all">
                  {middleTruncate(showInvisible(item.url), URL_DISPLAY_CHARS)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
