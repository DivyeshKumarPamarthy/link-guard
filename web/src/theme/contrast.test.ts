// WCAG AA contrast check on the real tokens in src/index.css (T0.10).
// Text needs 4.5:1; the focus ring and the input outline need 3:1 (WCAG 1.4.11).
import { describe, expect, test } from 'vitest'
import css from '../index.css?raw'

type Tokens = Record<string, string>

function block(startMarker: string): Tokens {
  const start = css.indexOf(startMarker)
  if (start < 0) throw new Error(`block not found: ${startMarker}`)
  const body = css.slice(start, css.indexOf('}', start))
  const tokens: Tokens = {}
  for (const match of body.matchAll(/--lg-([a-z-]+):\s*(#[0-9a-f]{6}|transparent);/g)) {
    tokens[match[1]] = match[2]
  }
  return tokens
}

const light = block(":root,\n[data-theme='light'] {")
const darkSystem = block(":root:not([data-theme='light']) {")
const darkForced = block("[data-theme='dark'] {")

function luminance(hex: string): number {
  const channel = (i: number) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5)
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

const VERDICTS = ['safe', 'no-issues', 'suspicious', 'unsafe', 'unable', 'rejected']

describe.each([
  ['light', light],
  ['dark', darkSystem],
])('%s mode', (_name, t) => {
  test.each([
    ['ink', 'paper'],
    ['ink', 'surface'],
    ['muted', 'paper'],
    ['muted', 'surface'],
    ['brand', 'paper'],
    ['brand', 'surface'],
    ['paper', 'brand'], // button text on the primary button
    ['unsupported-fg', 'paper'],
    ['unsupported-fg', 'surface'],
  ])('text %s on %s is at least 4.5:1', (fg, bg) => {
    expect(contrast(t[fg], t[bg])).toBeGreaterThanOrEqual(4.5)
  })

  test.each(VERDICTS)('verdict %s text on its tint is at least 4.5:1', (v) => {
    expect(contrast(t[`${v}-fg`], t[`${v}-bg`])).toBeGreaterThanOrEqual(4.5)
  })

  test.each([
    ['brand', 'paper'], // focus ring
    ['brand', 'surface'],
    ['muted', 'surface'], // text-input outline
    ['muted', 'paper'],
  ])('non-text %s against %s is at least 3:1', (fg, bg) => {
    expect(contrast(t[fg], t[bg])).toBeGreaterThanOrEqual(3)
  })
})

test('the two copies of the dark tokens are identical', () => {
  expect(darkForced).toEqual(darkSystem)
})

test('light and dark define the same set of tokens', () => {
  expect(Object.keys(darkSystem).sort()).toEqual(Object.keys(light).sort())
  expect(Object.keys(light)).toHaveLength(20)
})

test('tokens match the style guide values', () => {
  expect(light.paper).toBe('#f5f7f9')
  expect(darkSystem.paper).toBe('#0f1720')
  expect(light['unsafe-fg']).toBe('#b3261e')
  expect(darkSystem['rejected-bg']).toBe('#2a2238')
})

test('line is too faint to be the only outline of an input (why inputs use muted)', () => {
  expect(contrast(light.line, light.paper)).toBeLessThan(3)
})
