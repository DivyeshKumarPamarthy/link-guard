// Every tunable number of the web app lives here, so nothing is hard-coded in components.

/** Where the backend API runs. It binds to 127.0.0.1 only (D18); override with VITE_API_BASE. */
export const API_BASE: string = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000'

/** Polling starts at the server's poll_after_ms and backs off to this ceiling (spec §10). */
export const MAX_POLL_DELAY_MS = 2000

/** Each wait is this many times longer than the one before, up to MAX_POLL_DELAY_MS. */
export const POLL_BACKOFF_FACTOR = 1.5

/** Long URLs are shown shortened in the middle to this many characters, with an expand button. */
export const URL_DISPLAY_CHARS = 60

/** Spec §10 (P1): at most this many recent scans are kept in browser localStorage. */
export const MAX_RECENT_SCANS = 20

/** The home screen lists the demo links (src/demoLinks.ts) only in `vite --mode demo` (npm run dev:demo). */
export const SHOW_DEMO_LINKS: boolean = import.meta.env.MODE === 'demo'

/** Key used in window.localStorage for the recent-scans list. */
export const RECENT_SCANS_STORAGE_KEY = 'linkguard.recent_scans'

/** Key used in window.localStorage for the light / dark choice (D81). */
export const THEME_STORAGE_KEY = 'linkguard.theme'
