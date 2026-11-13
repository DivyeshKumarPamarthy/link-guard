// "Why": one row per finding, severity word, message from the backend registry, then the
// reason code. Every row shows its code, so a code this app has never heard of still renders
// as code + message (the generic card, spec §2) with no special list to keep in sync.
import type { Reason } from '../api/contract.ts'
import { showInvisible } from '../lib/text.ts'

const SEVERITY: Record<Reason['severity'], string> = {
  high: 'High',
  medium: 'Medium',
  low: 'Low',
  info: 'Info',
}

export function ReasonList({ reasons }: { reasons: Reason[] }) {
  return (
    <section aria-labelledby="why" className="space-y-2.5">
      <h2 id="why" className="text-label font-semibold text-muted">
        Why
      </h2>
      {reasons.length === 0 ? (
        <p className="border-y border-line py-3">No findings.</p>
      ) : (
        <ul className="border-b border-line">
          {reasons.map((reason, i) => (
            <li key={i} className="grid grid-cols-[72px_minmax(0,1fr)] gap-x-3 gap-y-1 border-t border-line py-3">
              {/* A severity from a newer backend falls back to the quietest word. */}
              <span className="text-label leading-[1.7] font-semibold">
                {SEVERITY[reason.severity] ?? SEVERITY.info}
              </span>
              <div className="flex min-w-0 flex-col gap-1">
                <span className="break-words">{showInvisible(reason.message)}</span>
                <span className="font-mono text-xs leading-normal break-all text-muted">
                  {showInvisible(reason.code)}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
