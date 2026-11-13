// The web app: one screen at a time, chosen by a small state machine.
// home → (submit) → checking → (poll until done) → report, or → error / back home with an input error.
import { useState } from 'react'
import { ApiError, getScan, submitScan, type ApiErrorKind } from './api/client.ts'
import type { ScanResult } from './api/contract.ts'
import { pollUntilDone } from './api/poll.ts'
import { smallButton } from './components/buttons.ts'
import { SHOW_DEMO_LINKS } from './config.ts'
import { DEMO_LINKS } from './demoLinks.ts'
import {
  clearRecentScans,
  loadRecentScans,
  saveRecentScan,
  type RecentScan,
} from './lib/recentScans.ts'
import { applyTheme, initialTheme, type Theme } from './lib/theme.ts'
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
  const [recentScans, setRecentScans] = useState<RecentScan[]>(() => loadRecentScans())
  const [theme, setTheme] = useState<Theme>(() => initialTheme())

  /** The theme button: flip light/dark, apply it at once and remember it in this browser. */
  function toggleTheme() {
    const next: Theme = theme === 'dark' ? 'light' : 'dark'
    applyTheme(next, true)
    setTheme(next)
  }

  /** Submit, then poll. While this runs the checking screen is shown, so there is no second submit. */
  async function check(url: string) {
    setScreen({ name: 'checking', url })
    try {
      const accepted = await submitScan(url)
      const result = await pollUntilDone(accepted.scan_id, accepted.poll_after_ms, getScan)
      setRecentScans(saveRecentScan(result))
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

  function handleClearRecent() {
    clearRecentScans()
    setRecentScans([])
  }

  const goHome = () => setScreen(HOME)

  return (
    <div className="mx-auto flex min-h-screen max-w-content flex-col px-5 pt-7 pb-12">
      {/* Every screen: the wordmark (except on home, which has its own title) and the theme button. */}
      <header className="flex items-center justify-between gap-3">
        {screen.name !== 'home' ? (
          <a href="/" className="inline-flex min-h-11 items-center text-lg font-semibold tracking-[-0.01em] text-ink">
            LinkGuard
          </a>
        ) : (
          <span />
        )}
        {/* Names the action: in light mode it offers "Dark mode", and the other way round. */}
        <button type="button" onClick={toggleTheme} className={smallButton}>
          {theme === 'dark' ? 'Light mode' : 'Dark mode'}
        </button>
      </header>
      <main aria-live="polite" className={`flex-1 ${screen.name === 'home' ? 'pt-7' : 'pt-8'}`}>
        {screen.name === 'home' && (
          <HomeScreen
            initialUrl={screen.url}
            inputError={screen.inputError}
            onSubmit={check}
            recentScans={recentScans}
            onClearRecent={handleClearRecent}
            onSelectRecent={(item) => check(item.url)}
            demoLinks={SHOW_DEMO_LINKS ? DEMO_LINKS : []}
          />
        )}
        {screen.name === 'checking' && <CheckingScreen url={screen.url} />}
        {screen.name === 'report' && (
          <ReportScreen result={screen.result} onCheckAgain={() => check(screen.url)} onHome={goHome} />
        )}
        {screen.name === 'error' && (
          <ErrorScreen kind={screen.kind} onRetry={() => check(screen.url)} onHome={goHome} />
        )}
      </main>
      <footer className="mt-10 border-t border-line pt-4 text-small text-muted">Runs on this computer only</footer>
    </div>
  )
}

export default App
