import { expect, test } from 'vitest'
import { hexPairs, showInvisible } from './text.ts'

const RLO = String.fromCodePoint(0x202e)
const ZWSP = String.fromCodePoint(0x200b)
const BS = String.fromCodePoint(0x5c)

test('shows an RTL override as a visible escape', () => {
  expect(showInvisible(`invoice${RLO}fdp.exe`)).toBe(`invoice${BS}u202Efdp.exe`)
})

test('shows zero-width and control characters as escapes', () => {
  expect(showInvisible(`a${ZWSP}b\u0000c\nd`)).toBe(
    `a${BS}u200Bb${BS}u0000c${BS}u000Ad`,
  )
})

test('leaves ordinary text, including non-Latin letters, unchanged', () => {
  expect(showInvisible('фильм.mp4 — 映画')).toBe('фильм.mp4 — 映画')
})

test('splits hex into byte pairs', () => {
  expect(hexPairs('4d5a90')).toEqual(['4d', '5a', '90'])
  expect(hexPairs('')).toEqual([])
})
