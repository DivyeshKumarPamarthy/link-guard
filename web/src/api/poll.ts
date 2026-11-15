// Polling: ask for the scan until it is done, waiting a little longer each time (spec §10).
import { MAX_POLL_DELAY_MS, MAX_POLL_TOTAL_MS, POLL_BACKOFF_FACTOR } from '../config.ts'
import { ApiError } from './client.ts'
import type { ScanResult } from './contract.ts'

/** The next wait: grow by POLL_BACKOFF_FACTOR, never above MAX_POLL_DELAY_MS. */
export function nextDelay(delayMs: number): number {
  return Math.min(Math.round(delayMs * POLL_BACKOFF_FACTOR), MAX_POLL_DELAY_MS)
}

export const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

/**
 * Wait, read the scan, repeat until `state` is `done`. Errors from `getScan` are not retried:
 * they go straight to the error screen, where the user decides to try again (D33).
 * `getScan` and `wait` are parameters so tests can run without a server or real time.
 *
 * It never waits for ever: a scan that is still not done after MAX_POLL_TOTAL_MS of waiting
 * was lost by the backend (for example it restarted mid-scan), so polling stops with a
 * server error and the user sees the error screen instead of an endless "Checking…".
 */
export async function pollUntilDone(
  scanId: string,
  firstDelayMs: number,
  getScan: (scanId: string) => Promise<ScanResult>,
  wait: (ms: number) => Promise<void> = sleep,
): Promise<ScanResult> {
  let delay = Math.min(firstDelayMs, MAX_POLL_DELAY_MS)
  let waited = 0 // the sum of the waits, not clock time, so tests need no real clock
  for (;;) {
    await wait(delay)
    waited += delay
    const result = await getScan(scanId)
    if (result.state === 'done') return result
    if (waited >= MAX_POLL_TOTAL_MS) {
      throw new ApiError('server', 'The scan did not finish in time.')
    }
    delay = nextDelay(delay)
  }
}
