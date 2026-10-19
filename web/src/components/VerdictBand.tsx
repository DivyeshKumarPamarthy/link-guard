// The top of a report: verdict word + icon on the verdict's tint, then the headline.
import type { DisplayVerdict } from '../api/contract.ts'
import { VERDICTS } from './verdicts.ts'

export function VerdictBand({ verdict, headline }: { verdict: DisplayVerdict; headline: string }) {
  const { label, Icon, text, tint } = VERDICTS[verdict]
  return (
    <div className={`animate-verdict-in rounded-panel p-4 md:p-6 ${tint}`}>
      <p className={`flex items-center gap-2 text-verdict font-semibold ${text}`}>
        <Icon aria-hidden="true" size={28} strokeWidth={2} className="shrink-0" />
        {label}
      </p>
      <p className="mt-1 max-w-prose text-ink">{headline}</p>
    </div>
  )
}
