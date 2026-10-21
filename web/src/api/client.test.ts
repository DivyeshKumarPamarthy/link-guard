// The client turns every HTTP outcome into either data or an ApiError with a kind.
import { afterEach, expect, test, vi } from 'vitest'
import { API_BASE } from '../config.ts'
import { ACCEPTED, SCAN_ID, UNSAFE_DONE, errorBody, jsonResponse } from '../test/fixtures.ts'
import { getScan, submitScan } from './client.ts'

afterEach(() => {
  vi.unstubAllGlobals()
})

function stubFetch(answer: () => Promise<Response>) {
  const fetchMock = vi.fn(answer)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

test('submitScan POSTs the raw text as JSON and returns the scan id', async () => {
  const fetchMock = stubFetch(async () => jsonResponse(202, ACCEPTED))
  const accepted = await submitScan(' https://short.example/abc ')
  expect(accepted.scan_id).toBe(SCAN_ID)
  const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
  expect(url).toBe(`${API_BASE}/api/scans`)
  expect(init.method).toBe('POST')
  expect(JSON.parse(init.body as string)).toEqual({ url: ' https://short.example/abc ' })
})

test('getScan reads a result and ignores unknown fields', async () => {
  stubFetch(async () => jsonResponse(200, { ...UNSAFE_DONE, added_in_1_1: true }))
  const result = await getScan(SCAN_ID)
  expect(result.display_verdict).toBe('UNSAFE')
})

test.each([
  ['URL_EMPTY', 'Paste a link to check.'],
  ['URL_TOO_LONG', 'This link is longer than 2048 characters.'],
  ['URL_MULTIPLE', 'Paste one link at a time.'],
])('400 %s is an input error with the server message', async (code, message) => {
  stubFetch(async () => jsonResponse(400, errorBody(code, message)))
  await expect(submitScan('x')).rejects.toMatchObject({ kind: 'input', message })
})

test('a network failure means the server is unreachable', async () => {
  stubFetch(async () => {
    throw new TypeError('Failed to fetch')
  })
  await expect(submitScan('https://a.example/f')).rejects.toMatchObject({ kind: 'unreachable' })
  await expect(getScan(SCAN_ID)).rejects.toMatchObject({ kind: 'unreachable' })
})

test('503 SERVER_BUSY is a busy error', async () => {
  stubFetch(async () => jsonResponse(503, errorBody('SERVER_BUSY', 'busy')))
  await expect(submitScan('https://a.example/f')).rejects.toMatchObject({ kind: 'busy' })
})

test.each([
  ['500 on submit', () => jsonResponse(500, errorBody('INTERNAL_ERROR', 'x')), 'submit'],
  ['400 with another code', () => jsonResponse(400, errorBody('INVALID_REQUEST', 'x')), 'submit'],
  ['non-JSON body', () => new Response('<html>oops</html>', { status: 400 }), 'submit'],
  ['404 while polling', () => jsonResponse(404, errorBody('NOT_FOUND', 'x')), 'get'],
  ['unknown schema major while polling', () => jsonResponse(200, { ...UNSAFE_DONE, schema_version: '2.0' }), 'get'],
  ['non-JSON while polling', () => new Response('not json', { status: 200 }), 'get'],
])('%s is a server error', async (_name, answer, call) => {
  stubFetch(async () => answer())
  const run = call === 'submit' ? submitScan('https://a.example/f') : getScan(SCAN_ID)
  await expect(run).rejects.toMatchObject({ kind: 'server' })
})
