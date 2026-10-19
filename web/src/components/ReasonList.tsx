// "Why": one line per finding, severity word + icon, message from the backend registry.
// Every row also shows its reason code, so a code this app has never heard of still renders
// as code + message (the generic card, spec §2) with no special list to keep in sync.
import { Circle, CircleDot, type LucideIcon } from 'lucide-react'
import type { Reason } from '../api/contract.ts'
import { showInvisible } from '../lib/text.ts'

const SEVERITY: Record<Reason['severity'], { label: string; Icon: LucideIcon }> = {
  high: { label: 'High', Icon: CircleDot },
  medium: { label: 'Medium', Icon: CircleDot },
  low: { label: 'Low', Icon: CircleDot },
  info: { label: 'Info', Icon: Circle },
}

export function ReasonList({ reasons }: { reasons: Reason[] }) {
  if (reasons.length === 0) return null
  return (
    <section aria-labelledby="why">
      <h2 id="why" className="text-section font-semibold">
        Why
      </h2>
      <ul className="mt-2 space-y-2">
        {reasons.map((reason, i) => {
          // A severity from a newer backend falls back to the quietest style.
          const { label, Icon } = SEVERITY[reason.severity] ?? SEVERITY.info
          return (
            <li key={i} className="flex gap-3">
              <span className="inline-flex w-20 shrink-0 items-center gap-1.5 font-medium text-muted">
                <Icon aria-hidden="true" size={14} strokeWidth={2} className="shrink-0" />
                {label}
              </span>
              <span className="min-w-0 max-w-prose break-words">
                {showInvisible(reason.message)}{' '}
                <span className="font-mono text-small text-muted">{showInvisible(reason.code)}</span>
              </span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
