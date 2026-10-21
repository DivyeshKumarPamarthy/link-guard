// The only place the web app talks to the backend (plain fetch, spec §2).
// Every failure becomes an ApiError with a `kind` the screens know how to explain.
import { API_BASE } from '../config.ts'
import { readScanResult, type ScanAccepted, type ScanResult } from './contract.ts'

/**
 * - input: 400 for the typed link (URL_EMPTY, URL_TOO_LONG, URL_MULTIPLE); shown under the input.
 * - unreachable: fetch itself failed, so the server is not running or not reachable.
 * - busy: 503 SERVER_BUSY; the user tries again in a few seconds.
 * - server: anything else (500, 404 while polling, a response we cannot read).
 */
export type ApiErrorKind = 'input' | 'unreachable' | 'busy' | 'server'

export class ApiError extends Error {
  readonly kind: ApiErrorKind

  constructor(kind: ApiErrorKind, message: string) {
    super(message)
    this.kind = kind
  }
}

const INPUT_CODES = ['URL_EMPTY', 'URL_TOO_LONG', 'URL_MULTIPLE']

async function send(path: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(`${API_BASE}${path}`, init)
  } catch {
    throw new ApiError('unreachable', 'The LinkGuard server could not be reached.')
  }
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json()
  } catch {
    throw new ApiError('server', 'The server sent a response that is not JSON.')
  }
}

/** Turn a non-2xx response into an ApiError. Only our own 400 messages are shown to the user. */
async function toApiError(response: Response): Promise<ApiError> {
  if (response.status === 503) return new ApiError('busy', 'The server is busy.')
  if (response.status === 400) {
    const body = (await readJson(response)) as { error?: { code?: unknown; message?: unknown } }
    const code = body?.error?.code
    const message = body?.error?.message
    if (typeof code === 'string' && INPUT_CODES.includes(code) && typeof message === 'string') {
      return new ApiError('input', message)
    }
  }
  return new ApiError('server', `The server answered ${response.status}.`)
}

/** POST /api/scans: create a scan for the raw text the user typed. */
export async function submitScan(url: string): Promise<ScanAccepted> {
  const response = await send('/api/scans', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  })
  if (response.status !== 202) throw await toApiError(response)
  const body = (await readJson(response)) as Partial<ScanAccepted> | null
  if (typeof body?.scan_id !== 'string' || typeof body.poll_after_ms !== 'number') {
    throw new ApiError('server', 'The server accepted the scan but sent no scan id.')
  }
  return body as ScanAccepted
}

/** GET /api/scans/{id}: read the scan once. */
export async function getScan(scanId: string): Promise<ScanResult> {
  const response = await send(`/api/scans/${encodeURIComponent(scanId)}`)
  if (response.status !== 200) throw await toApiError(response)
  try {
    return readScanResult(await readJson(response))
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw new ApiError('server', 'The server sent a result this app cannot read.')
  }
}
