// The top of a report: the verdict word on the verdict's tint, then the headline.
// `children` is for extra lines inside the band, such as the read / not-read bar.
import { useId, type ReactNode } from 'react'
import type { DisplayVerdict } from '../api/contract.ts'
import { VERDICTS } from './verdicts.ts'

interface Props {
  verdict: DisplayVerdict
  headline: string
  children?: ReactNode
}

export function VerdictBand({ verdict, headline, children }: Props) {
  const { label, text, tint, body } = VERDICTS[verdict]
  const wordId = useId() // unique even when /styleguide shows all seven bands
  return (
    <section aria-labelledby={wordId} className={`animate-verdict-in space-y-3 rounded-panel p-7 ${tint}`}>
      <h1 id={wordId} className={`text-verdict font-semibold tracking-[-0.015em] break-words ${text}`}>
        {label}
      </h1>
      <p className={`text-lead break-words ${body}`}>{headline}</p>
      {children}
    </section>
  )
}
