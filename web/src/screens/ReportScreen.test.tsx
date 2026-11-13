// The report details added with the D80 design: the read / not-read bar, "No findings.",
// the tinted "Actual" cell and the Details toggle.
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, test } from 'vitest'
import type { ScanResult } from '../api/contract.ts'
import { ClaimedVsActual } from '../components/ClaimedVsActual.tsx'
import { DISGUISED_EXE, GENUINE_PNG } from '../styleguide/mockData.ts'
import { UNSAFE_DONE } from '../test/fixtures.ts'
import { ReportScreen } from './ReportScreen.tsx'

afterEach(cleanup)

const MB = 1024 ** 2

/** The 200 MB demo file with only the first 5 MB read (the "200 MB file" demo link). */
const PARTIAL: ScanResult = {
  ...UNSAFE_DONE,
  verdict: 'SAFE',
  display_verdict: 'NO_ISSUES_IN_CHECKED_PART',
  headline: 'No issues found in the checked part (First 5 MB of 200 MB)',
  score: 0,
  scope: { mode: 'partial', bytes_analyzed: 5 * MB, total_bytes: 200 * MB, range_supported: true, label: 'First 5 MB of 200 MB' },
  reasons: [],
  redirects: [],
}

const show = (result: ScanResult) => render(<ReportScreen result={result} onCheckAgain={() => {}} onHome={() => {}} />)

describe('scope bar', () => {
  test('a partial scan says how much was read and how much was not', () => {
    show(PARTIAL)
    expect(screen.getByText('Read: first 5 MB')).toBeDefined()
    expect(screen.getByText('Not read: the other 195 MB')).toBeDefined()
  })

  test('is left out when the total size is unknown, so it never guesses', () => {
    show({ ...PARTIAL, scope: { ...PARTIAL.scope!, total_bytes: null, label: 'First 5 MB (total size unknown)' } })
    expect(screen.queryByText(/^Read: /)).toBeNull()
  })

  test('only appears on "No issues in the checked part"', () => {
    show({ ...PARTIAL, display_verdict: 'UNSAFE' })
    expect(screen.queryByText(/^Read: /)).toBeNull()
  })
})

test('a scan with no findings says so instead of hiding "Why"', () => {
  show(PARTIAL)
  expect(screen.getByRole('heading', { name: 'Why' })).toBeDefined()
  expect(screen.getByText('No findings.')).toBeDefined()
})

test('Details opens and closes with one button that reports its state', () => {
  show(UNSAFE_DONE)
  const toggle = screen.getByRole('button', { name: /Details/ })
  expect(toggle.getAttribute('aria-expanded')).toBe('false')
  expect(screen.queryByText('Engine / rules')).toBeNull()
  fireEvent.click(toggle)
  expect(toggle.getAttribute('aria-expanded')).toBe('true')
  expect(screen.getByText('Engine / rules')).toBeDefined()
  fireEvent.click(toggle)
  expect(screen.queryByText('Engine / rules')).toBeNull()
})

describe('"Actual" cell', () => {
  test('takes the verdict tint when the detected type is the problem', () => {
    render(<ClaimedVsActual file={DISGUISED_EXE} verdict="UNSAFE" />)
    expect(screen.getByText('Windows executable').className).toContain('text-unsafe-fg')
  })

  test('stays plain on a Safe result', () => {
    render(<ClaimedVsActual file={GENUINE_PNG} verdict="SAFE" />)
    expect(screen.getByText(GENUINE_PNG.detected_label!).className).toContain('text-ink')
  })
})
