// Screen 1: title, one-line explanation, link input, "Check link", "What we check",
// and the localStorage recent-scans list below "What we check" (spec §10 P1, D33).
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { UrlText } from '../components/LongText.tsx'
import { VerdictBadge } from '../components/VerdictBadge.tsx'
import type { RecentScan } from '../lib/recentScans.ts'

interface Props {
  initialUrl: string
  /** Our own 400 message (e.g. "Paste a link to check."), shown under the input. */
  inputError: string | null
  onSubmit: (url: string) => void
  recentScans?: RecentScan[]
  onClearRecent?: () => void
  onSelectRecent?: (item: RecentScan) => void
}

const WHAT_WE_CHECK = [
  "The file's real type, read from its first bytes",
  'Where shortened links really lead',
  'Whether the address is safe to contact',
]

export function HomeScreen({
  initialUrl,
  inputError,
  onSubmit,
  recentScans = [],
  onClearRecent,
  onSelectRecent,
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
    <div className="space-y-8">
      <div>
        <h1 className="text-title font-semibold">LinkGuard</h1>
        <p className="mt-2 max-w-prose">Check a download link before you open the file.</p>
      </div>

      <form onSubmit={submit} noValidate>
        <label htmlFor="link" className="font-medium">
          Link to check
        </label>
        <div className="mt-1 flex flex-col gap-2 sm:flex-row">
          <input
            id="link"
            ref={inputRef}
            type="text"
            inputMode="url"
            autoComplete="off"
            spellCheck={false}
            placeholder="https://…"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            aria-invalid={inputError !== null}
            aria-describedby={inputError ? 'link-error' : undefined}
            className="min-w-0 flex-1 rounded-control border border-muted bg-surface px-3 py-2 font-mono"
          />
          <button
            type="submit"
            className="rounded-control bg-brand px-4 py-2 font-medium text-surface hover:opacity-90"
          >
            Check link
          </button>
        </div>
        {inputError && (
          <p id="link-error" className="mt-1 text-small text-unsafe-fg">
            {inputError}
          </p>
        )}
      </form>

      <section aria-labelledby="what-we-check">
        <h2 id="what-we-check" className="text-section font-semibold">
          What we check
        </h2>
        <ul className="mt-2 space-y-1">
          {WHAT_WE_CHECK.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </section>

      {recentScans.length > 0 && (
        <section aria-labelledby="recent-scans">
          <div className="flex items-baseline justify-between gap-4">
            <h2 id="recent-scans" className="text-section font-semibold">
              Recent scans
            </h2>
            {onClearRecent && (
              <button
                type="button"
                onClick={onClearRecent}
                className="text-small font-medium text-brand hover:underline"
              >
                Clear
              </button>
            )}
          </div>
          <ul className="mt-2 space-y-2">
            {recentScans.map((item) => (
              <li
                key={item.scan_id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-panel border border-line bg-surface p-3"
              >
                <div className="flex min-w-0 flex-wrap items-center gap-2">
                  <VerdictBadge verdict={item.display_verdict} />
                  <UrlText url={item.url} />
                </div>
                {onSelectRecent && (
                  <button
                    type="button"
                    onClick={() => onSelectRecent(item)}
                    className="rounded-control border border-line bg-surface px-3 py-1 text-small font-medium text-brand"
                  >
                    Check again
                  </button>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
