// The web app: one screen at a time, chosen by a small state machine.
// home → (submit) → checking → (poll until done) → report, or → error / back home with an input error.
import { useState } from 'react'
import { ApiError, getScan, submitScan, type ApiErrorKind } from './api/client.ts'
import type { ScanResult } from './api/contract.ts'
import { pollUntilDone } from './api/poll.ts'
import { CheckingScreen } from './screens/CheckingScreen.tsx'
import { ErrorScreen } from './screens/ErrorScreen.tsx'
import { HomeScreen } from './screens/HomeScreen.tsx'
import { ReportScreen } from './screens/ReportScreen.tsx'

type Screen =
  | { name: 'home'; url: string; inputError: string | null }
  | { name: 'checking'; url: string }
  | { name: 'report'; url: string; result: ScanResult }
  | { name: 'error'; url: string; kind: Exclude<ApiErrorKind, 'input'> }

const HOME: Screen = { name: 'home', url: '', inputError: null }

function App() {
  const [screen, setScreen] = useState<Screen>(HOME)

  /** Submit, then poll. While this runs the checking screen is shown, so there is no second submit. */
  async function check(url: string) {
    setScreen({ name: 'checking', url })
    try {
      const accepted = await submitScan(url)
      const result = await pollUntilDone(accepted.scan_id, accepted.poll_after_ms, getScan)
      setScreen({ name: 'report', url, result })
    } catch (error) {
      const kind = error instanceof ApiError ? error.kind : 'server'
      if (kind === 'input') {
        setScreen({ name: 'home', url, inputError: (error as ApiError).message })
      } else {
        setScreen({ name: 'error', url, kind })
      }
    }
  }

  const goHome = () => setScreen(HOME)

  return (
    <div className="mx-auto flex min-h-screen max-w-content flex-col px-4 md:px-8">
      {screen.name !== 'home' && (
        <header className="pt-6">
          <a href="/" className="text-section font-semibold text-ink">
            LinkGuard
          </a>
        </header>
      )}
      <main aria-live="polite" className="flex-1 py-8">
        {screen.name === 'home' && (
          <HomeScreen initialUrl={screen.url} inputError={screen.inputError} onSubmit={check} />
        )}
        {screen.name === 'checking' && <CheckingScreen url={screen.url} />}
        {screen.name === 'report' && (
          <ReportScreen result={screen.result} onCheckAgain={() => check(screen.url)} onHome={goHome} />
        )}
        {screen.name === 'error' && (
          <ErrorScreen kind={screen.kind} onRetry={() => check(screen.url)} onHome={goHome} />
        )}
      </main>
      <footer className="border-t border-line py-4 text-small text-muted">Runs on this computer only</footer>
    </div>
  )
}

export default App
