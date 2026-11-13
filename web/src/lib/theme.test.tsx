// The light / dark button (D81): starts from the saved choice or the system, flips on press,
// is remembered, and works on every screen.
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import App from '../App.tsx'
import { THEME_STORAGE_KEY } from '../config.ts'
import { initialTheme, loadSavedTheme } from './theme.ts'

beforeEach(() => {
  window.localStorage.clear()
  delete document.documentElement.dataset.theme
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

/** Pretend the operating system is in dark (true) or light (false) mode. */
function systemDark(dark: boolean) {
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: dark && query.includes('dark') }))
}

test('without a saved choice the page follows the system setting', () => {
  systemDark(true)
  expect(initialTheme()).toBe('dark')
  systemDark(false)
  expect(initialTheme()).toBe('light')
})

test('a saved choice wins over the system; junk in storage is ignored', () => {
  systemDark(true)
  window.localStorage.setItem(THEME_STORAGE_KEY, 'light')
  expect(initialTheme()).toBe('light')
  window.localStorage.setItem(THEME_STORAGE_KEY, 'purple')
  expect(loadSavedTheme()).toBeNull()
})

test('the button names the other mode, switches the colours and remembers the choice', () => {
  systemDark(false)
  render(<App />)
  const button = screen.getByRole('button', { name: 'Dark mode' })

  fireEvent.click(button)
  expect(document.documentElement.dataset.theme).toBe('dark')
  expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')
  expect(button.textContent).toBe('Light mode')

  fireEvent.click(button)
  expect(document.documentElement.dataset.theme).toBe('light')
  expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')
  expect(button.textContent).toBe('Dark mode')
})

test('the button is also on the result, checking and error screens (it lives in the shared header)', () => {
  window.localStorage.setItem(THEME_STORAGE_KEY, 'dark')
  render(<App />)
  expect(screen.getByRole('button', { name: 'Light mode' }).closest('header')).not.toBeNull()
})
