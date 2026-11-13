// Screens 3–6: the result. Rendered from display_verdict only (D4), never recomputed here.
// Every remote value is React text (escaped), so a hostile filename or URL can't become HTML.
import { useState } from 'react'
import type { ScanResult } from '../api/contract.ts'
import { primaryButton, secondaryButton } from '../components/buttons.ts'
import { ClaimedVsActual } from '../components/ClaimedVsActual.tsx'
import { UrlText } from '../components/LongText.tsx'
import { ReasonList } from '../components/ReasonList.tsx'
import { RedirectList } from '../components/RedirectList.tsx'
import { ScopeBar } from '../components/ScopeBar.tsx'
import { VerdictBand } from '../components/VerdictBand.tsx'
import { showInvisible } from '../lib/text.ts'
import { hintsFor } from './hints.ts'

interface Props {
  result: ScanResult
  onCheckAgain: () => void
  onHome: () => void
}

const CONFIDENCE = { high: 'High', medium: 'Medium', low: 'Low' } as const

const LINK_TYPE: Record<string, string> = {
  http: 'Direct link',
  shortened: 'Shortened link (redirects to another site)',
}

/** One row of the Details list: a label and a value; `mono` for values the user may copy. */
interface DetailRow {
  name: string
  value: string
  mono?: boolean
}

function detailRows(result: ScanResult): DetailRow[] {
  const rows: DetailRow[] = []
  if (result.display_host) {
    // IDN hosts show both forms (spec §10).
    const punycode =
      result.punycode_host && result.punycode_host !== result.display_host
        ? ` (${showInvisible(result.punycode_host)})`
        : ''
    rows.push({ name: 'Final site', value: showInvisible(result.display_host) + punycode, mono: true })
  }
  if (result.final_url) rows.push({ name: 'Final address', value: showInvisible(result.final_url), mono: true })
  if (result.link_type) rows.push({ name: 'Link type', value: LINK_TYPE[result.link_type] ?? result.link_type })
  rows.push({ name: 'What was read', value: result.scope?.label ?? 'Nothing was read' })
  // Checks that could not run for this scan (spec §2); empty in Phase 1 unless something failed.
  if (result.unavailable_signals.length > 0) {
    rows.push({ name: 'Not checked', value: result.unavailable_signals.map(showInvisible).join(', ') })
  }
  if (result.confidence) rows.push({ name: 'Confidence', value: CONFIDENCE[result.confidence] ?? result.confidence })
  if (result.score !== null) rows.push({ name: 'Score', value: `${result.score} / 100` })
  if (result.timings_ms) {
    const timings = Object.entries(result.timings_ms).map(([name, ms]) => `${ms} ms ${name}`)
    rows.push({ name: 'Timings', value: timings.join(', ') })
  }
  rows.push({ name: 'Engine / rules', value: `${result.engine_version} / ${result.rules_version}` })
  return rows
}

/** Collapsed facts for the curious: where it ended, what was read, confidence, score, timings, versions. */
function Details({ result }: { result: ScanResult }) {
  const [open, setOpen] = useState(false)
  return (
    <section aria-labelledby="details-heading" className="border-y border-line">
      <h2 id="details-heading">
        <button
          type="button"
          aria-expanded={open}
          aria-controls="details-list"
          onClick={() => setOpen(!open)}
          className="flex min-h-12 w-full cursor-pointer items-center justify-between gap-3 text-left font-semibold"
        >
          <span>Details</span>
          <span className="text-label font-normal text-muted">{open ? 'Hide' : 'Show'}</span>
        </button>
      </h2>
      <div id="details-list">
        {open && (
          <dl className="pb-2">
            {detailRows(result).map((row) => (
              <div
                key={row.name}
                className="grid grid-cols-[minmax(96px,168px)_minmax(0,1fr)] gap-3 border-t border-line py-2.25 text-label leading-normal"
              >
                <dt className="text-muted">{row.name}</dt>
                {/* Hosts and URLs may break anywhere; words only at spaces. */}
                <dd className={`min-w-0 ${row.mono ? 'font-mono break-all' : 'break-words'}`}>{row.value}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>
    </section>
  )
}

export function ReportScreen({ result, onCheckAgain, onHome }: Props) {
  // The orchestrator guarantees a display verdict once state is done (D29).
  const verdict = result.display_verdict ?? 'UNABLE_TO_VERIFY'
  const headline = showInvisible(result.headline ?? '')
  const reasons = result.reasons ?? []
  const isScanned = verdict !== 'REJECTED' && verdict !== 'UNSUPPORTED'
  const isUnable = verdict === 'UNABLE_TO_VERIFY'

  return (
    <div className="space-y-8">
      <VerdictBand verdict={verdict} headline={headline}>
        {verdict === 'NO_ISSUES_IN_CHECKED_PART' && result.scope && <ScopeBar scope={result.scope} />}
      </VerdictBand>

      <UrlText url={result.input_url} label="Link checked:" />

      {verdict === 'REJECTED' && (
        <p className="max-w-prose">
          This protects your computer and local network. Links to your own computer, your router or
          company systems are never fetched.
        </p>
      )}

      {isScanned && result.file && <ClaimedVsActual file={result.file} verdict={verdict} />}
      {isScanned && <ReasonList reasons={reasons} />}

      {isUnable && (
        <section aria-labelledby="what-you-can-try" className="space-y-2.5">
          <h2 id="what-you-can-try" className="text-label font-semibold text-muted">
            What you can try
          </h2>
          <ul className="border-b border-line">
            {hintsFor(reasons.map((r) => r.code)).map((hint) => (
              <li key={hint} className="border-t border-line py-3">
                {hint}
              </li>
            ))}
          </ul>
        </section>
      )}

      <RedirectList hops={result.redirects ?? []} />
      {isScanned && <Details result={result} />}

      <div className="flex flex-wrap gap-2">
        {isUnable && (
          <button type="button" onClick={onCheckAgain} className={primaryButton}>
            Check again
          </button>
        )}
        <button type="button" onClick={onHome} className={isUnable ? secondaryButton : primaryButton}>
          Check another link
        </button>
      </div>
    </div>
  )
}
