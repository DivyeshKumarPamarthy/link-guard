// Small tag with the verdict word. The word carries the meaning, never colour alone.
import type { DisplayVerdict } from '../api/contract.ts'
import { VERDICTS } from './verdicts.ts'

export function VerdictBadge({ verdict }: { verdict: DisplayVerdict }) {
  const { label, text, tint } = VERDICTS[verdict]
  return (
    <span className={`inline-block rounded-badge px-2 py-0.75 text-small font-semibold ${text} ${tint}`}>
      {label}
    </span>
  )
}
