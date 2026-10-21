// Screens 3–6: the result. Rendered from display_verdict only (D4), never recomputed here.
// Every remote value is React text (escaped), so a hostile filename or URL can't become HTML.
import type { ScanResult } from '../api/contract.ts'
import { ClaimedVsActual } from '../components/ClaimedVsActual.tsx'
import { UrlText } from '../components/LongText.tsx'
import { ReasonList } from '../components/ReasonList.tsx'
import { RedirectList } from '../components/RedirectList.tsx'
import { VerdictBand } from '../components/VerdictBand.tsx'
import { showInvisible } from '../lib/text.ts'
import { hintsFor } from './hints.ts'

interface Props {
  result: ScanResult
  onCheckAgain: () => void
  onHome: () => void
}

const primaryButton = 'rounded-control bg-brand px-4 py-2 font-medium text-surface hover:opacity-90'
const secondaryButton = 'rounded-control border border-line bg-surface px-4 py-2 font-medium text-brand'

const CONFIDENCE = { high: 'High', medium: 'Medium', low: 'Low' } as const

/** Collapsed facts for the curious: what was read, confidence, score, timings, versions. */
function Details({ result }: { result: ScanResult }) {
  const timings = result.timings_ms
  const rows: [string, string][] = [['What was read', result.scope?.label ?? 'Nothing was read']]
  if (result.confidence) rows.push(['Confidence', CONFIDENCE[result.confidence] ?? result.confidence])
  if (result.score !== null) rows.push(['Score', `${result.score} / 100`])
  if (timings) {
    rows.push([
      'Timings',
      Object.entries(timings)
        .map(([name, ms]) => `${ms} ms ${name}`)
        .join(', '),
    ])
  }
  rows.push(['Engine / rules', `${result.engine_version} / ${result.rules_version}`])

  return (
    <details className="rounded-panel border border-line bg-surface p-4">
      <summary className="cursor-pointer font-medium">Details</summary>
      <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-6 gap-y-2">
        {result.display_host && (
          <>
            <dt className="font-medium text-muted">Final site</dt>
            <dd className="min-w-0 break-all font-mono">
              {showInvisible(result.display_host)}
              {/* IDN hosts show both forms (spec §10). */}
              {result.punycode_host && result.punycode_host !== result.display_host &&
                ` (${showInvisible(result.punycode_host)})`}
            </dd>
          </>
        )}
        {rows.map(([name, value]) => (
          <div key={name} className="contents">
            <dt className="font-medium text-muted">{name}</dt>
            <dd className="min-w-0">{value}</dd>
          </div>
        ))}
      </dl>
    </details>
  )
}

export function ReportScreen({ result, onCheckAgain, onHome }: Props) {
  // The orchestrator guarantees a display verdict once state is done (D29).
  const verdict = result.display_verdict ?? 'UNABLE_TO_VERIFY'
  const headline = showInvisible(result.headline ?? '')
  const reasons = result.reasons ?? []
  const isScanned = verdict !== 'REJECTED' && verdict !== 'UNSUPPORTED'

  return (
    <div className="space-y-8">
      <VerdictBand verdict={verdict} headline={headline} />

      <p className="flex flex-wrap items-center gap-2 text-small text-muted">
        <span>Link checked:</span>
        <UrlText url={result.input_url} />
      </p>

      {verdict === 'UNABLE_TO_VERIFY' && (
        <section aria-labelledby="what-you-can-try">
          <h2 id="what-you-can-try" className="text-section font-semibold">
            What you can try
          </h2>
          <ul className="mt-2 max-w-prose space-y-1">
            {hintsFor(reasons.map((r) => r.code)).map((hint) => (
              <li key={hint}>{hint}</li>
            ))}
          </ul>
        </section>
      )}

      {verdict === 'REJECTED' && (
        <p className="max-w-prose">
          This protects your computer and local network. Links to your own computer, your router or
          company systems are never fetched.
        </p>
      )}

      {isScanned && result.file && <ClaimedVsActual file={result.file} verdict={verdict} />}
      {isScanned && <ReasonList reasons={reasons} />}
      <RedirectList hops={result.redirects ?? []} />
      {isScanned && <Details result={result} />}

      <div className="flex flex-wrap gap-3">
        {verdict === 'UNABLE_TO_VERIFY' && (
          <button type="button" onClick={onCheckAgain} className={primaryButton}>
            Check again
          </button>
        )}
        <button
          type="button"
          onClick={onHome}
          className={verdict === 'UNABLE_TO_VERIFY' ? secondaryButton : primaryButton}
        >
          Check another link
        </button>
      </div>
    </div>
  )
}
