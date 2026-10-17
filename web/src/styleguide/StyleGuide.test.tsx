import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, expect, test } from 'vitest'
import { VERDICTS } from '../components/verdicts.ts'
import { StyleGuide } from './StyleGuide.tsx'

afterEach(cleanup)

test('shows every verdict state in both light and dark mode', () => {
  render(<StyleGuide />)
  for (const mode of ['light mode', 'dark mode']) {
    const column = screen.getByRole('region', { name: mode })
    expect(column.getAttribute('data-theme')).toBe(mode.split(' ')[0])
    for (const { label } of Object.values(VERDICTS)) {
      // once as a badge and once as a band
      expect(within(column).getAllByText(label)).toHaveLength(2)
    }
    expect(within(column).getAllByRole('heading', { name: 'Claimed vs actual' }).length).toBeGreaterThan(0)
  }
})
