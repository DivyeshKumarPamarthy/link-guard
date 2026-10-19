// One place that maps each display_verdict to its words, icon and colours
// (docs/ui-style-guide.md, verdict table). Class names are written out in full so
// Tailwind can find them; never build them from strings.
import {
  Ban,
  CircleDashed,
  CircleQuestionMark,
  OctagonX,
  ShieldCheck,
  ShieldHalf,
  TriangleAlert,
  type LucideIcon,
} from 'lucide-react'
import type { DisplayVerdict } from '../api/contract.ts'

export interface VerdictStyle {
  label: string
  Icon: LucideIcon
  text: string // verdict text colour
  tint: string // tinted background (+ border for the dashed UNSUPPORTED style)
}

export const VERDICTS: Record<DisplayVerdict, VerdictStyle> = {
  SAFE: { label: 'Safe', Icon: ShieldCheck, text: 'text-safe-fg', tint: 'bg-safe-bg' },
  NO_ISSUES_IN_CHECKED_PART: {
    label: 'No issues in the checked part',
    Icon: ShieldHalf,
    text: 'text-no-issues-fg',
    tint: 'bg-no-issues-bg',
  },
  SUSPICIOUS: {
    label: 'Suspicious',
    Icon: TriangleAlert,
    text: 'text-suspicious-fg',
    tint: 'bg-suspicious-bg',
  },
  UNSAFE: { label: 'Unsafe', Icon: OctagonX, text: 'text-unsafe-fg', tint: 'bg-unsafe-bg' },
  UNABLE_TO_VERIFY: {
    label: 'Unable to verify',
    Icon: CircleQuestionMark,
    text: 'text-unable-fg',
    tint: 'bg-unable-bg',
  },
  REJECTED: {
    label: 'Not scanned: blocked address',
    Icon: Ban,
    text: 'text-rejected-fg',
    tint: 'bg-rejected-bg',
  },
  UNSUPPORTED: {
    label: 'Not supported yet',
    Icon: CircleDashed,
    text: 'text-unsupported-fg',
    tint: 'bg-unsupported-bg border border-dashed border-line',
  },
}

export const ALL_VERDICTS = Object.keys(VERDICTS) as DisplayVerdict[]
