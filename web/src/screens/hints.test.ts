// "What you can try" hints are keyed by reason code (D33) and always give the user a next step.
import { expect, test } from 'vitest'
import { hintsFor } from './hints.ts'

test('a known code gets its own hint', () => {
  expect(hintsFor(['LINK_IS_WEB_PAGE'])).toEqual([
    'Open the page in your browser and copy the direct download link instead.',
  ])
})

test('hints from several codes are combined without duplicates', () => {
  const hints = hintsFor(['FETCH_HTTP_ERROR', 'FETCH_AUTH_REQUIRED'])
  expect(hints).toEqual([
    'Check the link is complete and still works in your browser.',
    "If the site needs a login, LinkGuard can't check it.",
  ])
})

test('unknown or missing codes still get a general hint', () => {
  expect(hintsFor(['SOMETHING_NEW'])).toEqual(['Check the link is complete, then try again.'])
  expect(hintsFor([])).toEqual(['Check the link is complete, then try again.'])
})
