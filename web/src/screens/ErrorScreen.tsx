// Screen 7: the server is unreachable, busy (503) or failed. A plain panel, no verdict
// colours: these are not verdicts. No automatic retry; the user presses "Try again" (D33).
import type { ApiErrorKind } from '../api/client.ts'

type ScreenErrorKind = Exclude<ApiErrorKind, 'input'>

const COPY: Record<ScreenErrorKind, { title: string; next: string }> = {
  unreachable: {
    title: "Can't reach the LinkGuard server.",
    next: 'Start it with `make dev`, then try again.',
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
    <div className="space-y-6">
      <div role="alert" className="rounded-panel border border-line bg-surface p-4 md:p-6">
        <p className="text-section font-semibold">{title}</p>
        <p className="mt-1 max-w-prose">{next}</p>
      </div>
      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={onRetry}
          className="rounded-control bg-brand px-4 py-2 font-medium text-surface hover:opacity-90"
        >
          Try again
        </button>
        <button
          type="button"
          onClick={onHome}
          className="rounded-control border border-line bg-surface px-4 py-2 font-medium text-brand"
        >
          Check another link
        </button>
      </div>
    </div>
  )
}
