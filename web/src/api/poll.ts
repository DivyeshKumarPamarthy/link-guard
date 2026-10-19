// Polling: ask for the scan until it is done, waiting a little longer each time (spec §10).
import { MAX_POLL_DELAY_MS, POLL_BACKOFF_FACTOR } from '../config.ts'
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
 */
export async function pollUntilDone(
  scanId: string,
  firstDelayMs: number,
  getScan: (scanId: string) => Promise<ScanResult>,
  wait: (ms: number) => Promise<void> = sleep,
): Promise<ScanResult> {
  let delay = Math.min(firstDelayMs, MAX_POLL_DELAY_MS)
  for (;;) {
    await wait(delay)
    const result = await getScan(scanId)
    if (result.state === 'done') return result
    delay = nextDelay(delay)
  }
}
