// The demo links on the home screen (D79): listed only when App passes them (demo mode),
// and one click checks the link through the normal submit path.
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { SHOW_DEMO_LINKS } from '../config.ts'
import { DEMO_LINKS } from '../demoLinks.ts'
import { HomeScreen } from './HomeScreen.tsx'

afterEach(cleanup)

describe('demo links', () => {
  test('are off outside demo mode', () => {
    expect(SHOW_DEMO_LINKS).toBe(false)
  })

  test('are not shown when none are passed', () => {
    render(<HomeScreen initialUrl="" inputError={null} onSubmit={() => {}} />)
    expect(screen.queryByRole('heading', { name: 'Demo links' })).toBeNull()
  })

  test('list every demo link with its URL as text', () => {
    render(<HomeScreen initialUrl="" inputError={null} onSubmit={() => {}} demoLinks={DEMO_LINKS} />)
    expect(screen.getByRole('heading', { name: 'Demo links' })).toBeDefined()
    for (const link of DEMO_LINKS) {
      expect(screen.getByText(link.url)).toBeDefined()
    }
    // Buttons, never clickable links (CLAUDE.md: no scanned URL as a link).
    expect(screen.queryAllByRole('link')).toHaveLength(0)
  })

  test('one click submits that link', () => {
    const onSubmit = vi.fn()
    render(<HomeScreen initialUrl="" inputError={null} onSubmit={onSubmit} demoLinks={DEMO_LINKS} />)
    fireEvent.click(screen.getByRole('button', { name: new RegExp(DEMO_LINKS[1].label) }))
    expect(onSubmit).toHaveBeenCalledWith(DEMO_LINKS[1].url)
  })

  test('only point at the demo server or at addresses the backend must refuse', () => {
    for (const { url } of DEMO_LINKS) {
      expect(url).toMatch(/^(https?:\/\/[abc]\.demo\.test:\d+\/|http:\/\/169\.254\.169\.254\/|magnet:)/)
    }
  })
})
