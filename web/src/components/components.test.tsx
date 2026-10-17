// Tests for the shared report components used by /styleguide and later the report page.
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, test } from 'vitest'
import { DISGUISED_EXE, SPOOFED_NAME, UNKNOWN_BYTES } from '../styleguide/mockData.ts'
import { ClaimedVsActual } from './ClaimedVsActual.tsx'
import { HexStrip } from './HexStrip.tsx'
import { VerdictBadge } from './VerdictBadge.tsx'
import { VerdictBand } from './VerdictBand.tsx'
import { ALL_VERDICTS } from './verdicts.ts'

afterEach(cleanup)

// Exact labels from the style guide's verdict table.
const LABELS = {
  SAFE: 'Safe',
  NO_ISSUES_IN_CHECKED_PART: 'No issues in the checked part',
  SUSPICIOUS: 'Suspicious',
  UNSAFE: 'Unsafe',
  UNABLE_TO_VERIFY: 'Unable to verify',
  REJECTED: 'Not scanned: blocked address',
  UNSUPPORTED: 'Not supported yet',
} as const

describe('VerdictBadge', () => {
  test('there are exactly seven display verdicts', () => {
    expect(ALL_VERDICTS.sort()).toEqual(Object.keys(LABELS).sort())
  })

  test.each(Object.entries(LABELS))('%s shows the word "%s" and an icon', (verdict, label) => {
    const { container } = render(<VerdictBadge verdict={verdict as keyof typeof LABELS} />)
    expect(screen.getByText(label)).toBeDefined()
    // word + icon, never colour alone; the icon is decorative for screen readers
    expect(container.querySelector('svg[aria-hidden="true"]')).not.toBeNull()
  })

  test('"No issues in the checked part" never looks like "Safe"', () => {
    const { container: safe } = render(<VerdictBadge verdict="SAFE" />)
    const { container: partial } = render(<VerdictBadge verdict="NO_ISSUES_IN_CHECKED_PART" />)
    expect(safe.innerHTML).not.toEqual(partial.innerHTML)
    expect(partial.querySelector('span')?.className).toContain('text-no-issues-fg')
  })
})

describe('VerdictBand', () => {
  test('shows the verdict word and the headline', () => {
    render(<VerdictBand verdict="UNSAFE" headline="Blocked: file named .mp4 is actually a Windows executable" />)
    expect(screen.getByText('Unsafe')).toBeDefined()
    expect(screen.getByText('Blocked: file named .mp4 is actually a Windows executable')).toBeDefined()
  })
})

describe('HexStrip', () => {
  test('shows 16 bytes and highlights only the signature bytes', () => {
    const { container } = render(
      <HexStrip hex={DISGUISED_EXE.first_bytes_hex} signature={DISGUISED_EXE.signature} verdict="UNSAFE" />,
    )
    const marks = [...container.querySelectorAll('mark')].map((m) => m.textContent)
    expect(marks).toEqual(['4d', '5a'])
    expect(container.querySelectorAll('mark, p[aria-label] > span')).toHaveLength(16)
    expect(screen.getByText('Highlighted: MZ (Windows executable)')).toBeDefined()
  })

  test('without a signature nothing is highlighted and the caption says so', () => {
    const { container } = render(<HexStrip hex={UNKNOWN_BYTES.first_bytes_hex} signature={null} verdict="UNABLE_TO_VERIFY" />)
    expect(container.querySelectorAll('mark')).toHaveLength(0)
    expect(screen.getByText('No known signature in the first bytes')).toBeDefined()
  })

  test('an empty body says no bytes were read', () => {
    render(<HexStrip hex="" signature={null} verdict="UNABLE_TO_VERIFY" />)
    expect(screen.getByText('No bytes were read')).toBeDefined()
  })
})

describe('ClaimedVsActual', () => {
  test('shows claimed name, content type and detected type', () => {
    render(<ClaimedVsActual file={DISGUISED_EXE} verdict="UNSAFE" />)
    expect(screen.getByText('movie.mp4')).toBeDefined()
    expect(screen.getByText('video/mp4')).toBeDefined()
    expect(screen.getByText('Windows executable')).toBeDefined()
  })

  test('renders a hostile filename as text, never as HTML', () => {
    const { container } = render(<ClaimedVsActual file={SPOOFED_NAME} verdict="UNSAFE" />)
    expect(container.querySelector('img')).toBeNull()
    expect(container.textContent).toContain('<img src=x onerror=alert(1)>')
  })

  test('shows the RTL override escaped instead of letting it reverse the name', () => {
    const { container } = render(<ClaimedVsActual file={SPOOFED_NAME} verdict="UNSAFE" />)
    const backslash = String.fromCodePoint(0x5c)
    expect(container.textContent).toContain(`invoice${backslash}u202Efdp.exe`)
    expect(container.textContent).not.toContain(String.fromCodePoint(0x202e))
  })

  test('missing values get plain words instead of blanks', () => {
    render(<ClaimedVsActual file={{ ...UNKNOWN_BYTES, claimed_name: null }} verdict="UNABLE_TO_VERIFY" />)
    expect(screen.getByText('No file name given')).toBeDefined()
    expect(screen.getByText('no content type')).toBeDefined()
    expect(screen.getByText('Unknown type')).toBeDefined()
  })
})
