// Light or dark mode (D81). The colours already switch on `data-theme` on the page root
// (index.css); this file only decides which value to set and remembers the user's choice in
// localStorage. Unavailable or corrupt storage is ignored: the page then follows the system.
import { THEME_STORAGE_KEY } from '../config.ts'

export type Theme = 'light' | 'dark'

/** The choice saved by the theme button, or null if the user never pressed it. */
export function loadSavedTheme(): Theme | null {
  try {
    const value = window.localStorage.getItem(THEME_STORAGE_KEY)
    return value === 'light' || value === 'dark' ? value : null
  } catch {
    return null
  }
}

/** The operating system's setting, used until the user picks a theme. */
export function systemTheme(): Theme {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

/** What to show when the page opens: the saved choice first, otherwise the system setting. */
export function initialTheme(): Theme {
  return loadSavedTheme() ?? systemTheme()
}

/** Switch the colours now and remember the choice for next time. */
export function applyTheme(theme: Theme, save: boolean): void {
  document.documentElement.dataset.theme = theme
  if (!save) return
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme)
  } catch {
    // Storage blocked (private window): the switch still works for this visit.
  }
}
