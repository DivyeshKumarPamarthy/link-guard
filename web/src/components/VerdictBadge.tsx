// Small pill: icon + verdict word. Never colour alone (style guide rule).
import type { DisplayVerdict } from '../api/contract.ts'
import { VERDICTS } from './verdicts.ts'

export function VerdictBadge({ verdict }: { verdict: DisplayVerdict }) {
  const { label, Icon, text, tint } = VERDICTS[verdict]
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-badge px-3 py-1 text-small font-medium ${text} ${tint}`}
    >
      <Icon aria-hidden="true" size={16} strokeWidth={2} className="shrink-0" />
      {label}
    </span>
  )
}
