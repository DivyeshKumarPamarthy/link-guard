// Polling waits, reads, and stops at state=done, backing off to a 2 s ceiling.
import { expect, test } from 'vitest'
import { MAX_POLL_DELAY_MS } from '../config.ts'
import { RUNNING, SCAN_ID, UNSAFE_DONE } from '../test/fixtures.ts'
import { ApiError } from './client.ts'
import type { ScanResult } from './contract.ts'
import { nextDelay, pollUntilDone } from './poll.ts'

/** A fake server that answers with `answers` in order, and a wait that records delays. */
function fakes(answers: (ScanResult | Error)[]) {
  const waits: number[] = []
  const asked: string[] = []
  const getScan = async (id: string) => {
    asked.push(id)
    const next = answers.shift()!
    if (next instanceof Error) throw next
    return next
  }
  const wait = async (ms: number) => {
    waits.push(ms)
  }
  return { getScan, wait, waits, asked }
}

test('polls until the scan is done and returns the result', async () => {
  const { getScan, wait, asked } = fakes([RUNNING, { ...RUNNING, state: 'queued' }, UNSAFE_DONE])
  const result = await pollUntilDone(SCAN_ID, 500, getScan, wait)
  expect(result.display_verdict).toBe('UNSAFE')
  expect(asked).toEqual([SCAN_ID, SCAN_ID, SCAN_ID])
})

test('starts at poll_after_ms and backs off to the 2 s ceiling', async () => {
  const { getScan, wait, waits } = fakes([RUNNING, RUNNING, RUNNING, RUNNING, RUNNING, RUNNING, UNSAFE_DONE])
  await pollUntilDone(SCAN_ID, 500, getScan, wait)
  expect(waits).toEqual([500, 750, 1125, 1688, 2000, 2000, 2000])
})

test('a poll_after_ms above the ceiling is capped', async () => {
  const { getScan, wait, waits } = fakes([UNSAFE_DONE])
  await pollUntilDone(SCAN_ID, 10_000, getScan, wait)
  expect(waits).toEqual([MAX_POLL_DELAY_MS])
})

test('nextDelay never exceeds the ceiling', () => {
  expect(nextDelay(1900)).toBe(MAX_POLL_DELAY_MS)
})

test('an error while polling stops polling (no automatic retry)', async () => {
  const { getScan, wait, asked } = fakes([RUNNING, new ApiError('server', 'The server answered 500.'), UNSAFE_DONE])
  await expect(pollUntilDone(SCAN_ID, 1, getScan, wait)).rejects.toMatchObject({ kind: 'server' })
  expect(asked).toHaveLength(2)
})
