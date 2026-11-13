// One place that maps each display_verdict to its words and colours
// (docs/ui-style-guide.md, verdict table). The verdict word always carries the meaning;
// colour only supports it. Class names are written out in full so Tailwind can find them;
// never build them from strings.
import type { DisplayVerdict } from '../api/contract.ts'

export interface VerdictStyle {
  label: string
  text: string // verdict word colour
  tint: string // tinted background, plus a border for REJECTED and UNSUPPORTED
  body: string // headline colour inside the band
}

export const VERDICTS: Record<DisplayVerdict, VerdictStyle> = {
  SAFE: { label: 'Safe', text: 'text-safe-fg', tint: 'bg-safe-bg', body: 'text-ink' },
  NO_ISSUES_IN_CHECKED_PART: {
    label: 'No issues in the checked part',
    text: 'text-no-issues-fg',
    tint: 'bg-no-issues-bg',
    body: 'text-ink',
  },
  SUSPICIOUS: { label: 'Suspicious', text: 'text-suspicious-fg', tint: 'bg-suspicious-bg', body: 'text-ink' },
  UNSAFE: { label: 'Unsafe', text: 'text-unsafe-fg', tint: 'bg-unsafe-bg', body: 'text-ink' },
  UNABLE_TO_VERIFY: { label: 'Unable to verify', text: 'text-unable-fg', tint: 'bg-unable-bg', body: 'text-ink' },
  // Not a verdict on the file (nothing was fetched), so it gets no risk colour: ink on the
  // grey tint with a firm 2 px ink border, told apart from "Unable to verify" by word and border.
  REJECTED: {
    label: 'Not scanned: blocked address',
    text: 'text-rejected-fg',
    tint: 'bg-rejected-bg border-2 border-ink',
    body: 'text-ink',
  },
  UNSUPPORTED: {
    label: 'Not supported yet',
    text: 'text-unsupported-fg',
    tint: 'bg-unsupported-bg border border-dashed border-muted',
    body: 'text-muted',
  },
}

export const ALL_VERDICTS = Object.keys(VERDICTS) as DisplayVerdict[]

/** Verdicts where the detected type is the problem, so "Actual" takes the verdict's tint. */
export function highlightsActual(verdict: DisplayVerdict): boolean {
  return verdict === 'UNSAFE' || verdict === 'SUSPICIOUS' || verdict === 'UNABLE_TO_VERIFY'
}
