// Screen 7: the server is unreachable, busy (503) or failed. A plain panel, no verdict
// colours: these are not verdicts. No automatic retry; the user presses "Try again" (D33).
import type { ReactNode } from 'react'
import type { ApiErrorKind } from '../api/client.ts'
import { primaryButton, secondaryButton } from '../components/buttons.ts'

type ScreenErrorKind = Exclude<ApiErrorKind, 'input'>

const command = 'rounded-badge border border-line bg-paper px-1.5 py-0.5 font-mono text-[15px]'

const COPY: Record<ScreenErrorKind, { title: string; next: ReactNode }> = {
  unreachable: {
    title: "Can't reach the LinkGuard server.",
    next: (
      <>
        Start it with <code className={command}>make dev</code>, then try again.
      </>
    ),
  },
  busy: {
    title: 'LinkGuard is checking other links.',
    next: 'Try again in a few seconds.',
  },
  server: {
    title: 'Something went wrong on the LinkGuard server.',
    next: 'Try again; if it keeps happening, check the server terminal.',
  },
}

interface Props {
  kind: ScreenErrorKind
  onRetry: () => void
  onHome: () => void
}

export function ErrorScreen({ kind, onRetry, onHome }: Props) {
  const { title, next } = COPY[kind]
  return (
    <section role="alert" className="space-y-2.5 rounded-panel border border-line bg-surface p-6">
      <h1 className="text-section font-semibold">{title}</h1>
      <p className="max-w-prose leading-relaxed">{next}</p>
      <div className="flex flex-wrap gap-2 pt-2.5">
        <button type="button" onClick={onRetry} className={primaryButton}>
          Try again
        </button>
        <button type="button" onClick={onHome} className={secondaryButton}>
          Check another link
        </button>
      </div>
    </section>
  )
}
