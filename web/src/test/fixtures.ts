// Scan results for tests, shaped like the mock backend's answers (spec §2 example).
import type { ScanResult } from '../api/contract.ts'
import { DISGUISED_EXE } from '../styleguide/mockData.ts'

export const SCAN_ID = '9f3c2d1e-0000-4000-8000-000000000001'

/** What GET returns before the scan finishes: outcome fields are null. */
export const RUNNING: ScanResult = {
  schema_version: '1.0',
  scan_id: SCAN_ID,
  state: 'running',
  status: null,
  input_url: 'https://short.example/abc',
  normalized_url: null,
  final_url: null,
  display_host: null,
  punycode_host: null,
  link_type: null,
  verdict: null,
  display_verdict: null,
  score: null,
  confidence: null,
  scope: null,
  headline: null,
  file: null,
  redirects: [],
  reasons: null,
  unavailable_signals: [],
  timings_ms: null,
  engine_version: '1.0.0',
  rules_version: '1.0.0',
  created_at: '2026-10-16T10:15:00Z',
  completed_at: null,
}

/** The spec §2 example: a Windows program disguised as movie.mp4 behind a short link. */
export const UNSAFE_DONE: ScanResult = {
  ...RUNNING,
  state: 'done',
  status: 'completed',
  normalized_url: 'https://short.example/abc',
  final_url: 'https://files.example/movie.mp4',
  display_host: 'files.example',
  punycode_host: 'files.example',
  link_type: 'shortened',
  verdict: 'UNSAFE',
  display_verdict: 'UNSAFE',
  score: 70,
  confidence: 'high',
  scope: { mode: 'full', bytes_analyzed: 48213, total_bytes: 48213, range_supported: true, label: 'Whole file checked (47 KB)' },
  headline: 'Blocked: file named .mp4 is actually a Windows executable',
  file: DISGUISED_EXE,
  redirects: [
    { url: 'https://short.example/abc', status: 302, address_class: 'public' },
    { url: 'https://files.example/movie.mp4', status: 200, address_class: 'public' },
  ],
  reasons: [
    {
      code: 'TYPE_MISMATCH_EXEC',
      severity: 'high',
      weight: 70,
      group: 'type',
      message: 'The file is named .mp4 but its content is a Windows executable.',
      evidence: { claimed_ext: 'mp4', detected: 'pe-executable' },
    },
    {
      code: 'REDIR_CROSS_DOMAIN',
      severity: 'info',
      weight: 0,
      group: 'redirect',
      message: 'The link ended on a different site: files.example.',
      evidence: { final_host: 'files.example' },
    },
  ],
  timings_ms: { total: 812, fetch: 640 },
  completed_at: '2026-10-16T10:15:01Z',
}

/**
 * Acceptance row 9 against the demo server and the generated samples (T2.6): a 2-hop chain to
 * /disguised/movie.mp4, which is the 1 KB hello PE. Every value is what the backend produces
 * for it: the real first 16 bytes of the sample, the detector's label and signature, the
 * registry's messages, D48's private address class for demo-exempt hops, D64's scope label.
 * It is written by hand until the real executor exists (T2.4); T3.2 swaps in a captured one.
 */
export const DEMO_DISGUISED_CHAIN: ScanResult = {
  ...RUNNING,
  scan_id: '9f3c2d1e-0000-4000-8000-000000000009',
  input_url: 'http://a.demo.test:8081/redirect/chain?n=2&to=/disguised/movie.mp4',
  state: 'done',
  status: 'completed',
  normalized_url: 'http://a.demo.test:8081/redirect/chain?n=2&to=/disguised/movie.mp4',
  final_url: 'http://c.demo.test:8081/disguised/movie.mp4',
  display_host: 'c.demo.test',
  punycode_host: 'c.demo.test',
  link_type: 'shortened',
  verdict: 'UNSAFE',
  display_verdict: 'UNSAFE',
  score: 80,
  confidence: 'high',
  scope: { mode: 'full', bytes_analyzed: 1024, total_bytes: 1024, range_supported: true, label: 'Whole file checked (1 KB)' },
  headline: 'Blocked: file named .mp4 is actually a Windows executable',
  file: {
    claimed_name: 'movie.mp4',
    name_source: 'content-disposition',
    content_type: 'video/mp4',
    detected_type: 'pe-executable',
    detected_label: 'Windows executable',
    family: 'executable',
    detection_confidence: 'certain',
    first_bytes_hex: '4d5a90000300000004000000ffff0000',
    signature: { offset: 0, length: 2, name: 'MZ (Windows executable)' },
  },
  redirects: [
    { url: 'http://a.demo.test:8081/redirect/chain?n=2&to=/disguised/movie.mp4', status: 302, address_class: 'private' },
    { url: 'http://b.demo.test:8081/redirect/chain?n=1&to=/disguised/movie.mp4', status: 302, address_class: 'private' },
    { url: 'http://c.demo.test:8081/disguised/movie.mp4', status: 200, address_class: 'private' },
  ],
  reasons: [
    {
      code: 'TYPE_MISMATCH_EXEC',
      severity: 'high',
      weight: 70,
      group: 'type',
      message: 'The file is named .mp4 but its content is a Windows executable.',
      evidence: { claimed_ext: 'mp4', detected: 'pe-executable', detected_label: 'Windows executable' },
    },
    {
      code: 'TYPE_CONTENT_TYPE_MISMATCH',
      severity: 'low',
      weight: 10,
      group: 'header',
      message: 'The server says this is video/mp4, but its content is a Windows executable.',
      evidence: { content_type: 'video/mp4', detected_label: 'Windows executable' },
    },
    {
      code: 'REDIR_CROSS_DOMAIN',
      severity: 'info',
      weight: 0,
      group: 'redirect',
      message: 'The link ended on a different site: c.demo.test.',
      evidence: { final_host: 'c.demo.test' },
    },
  ],
  unavailable_signals: [],
  timings_ms: { total: 41, fetch: 38, first_byte: 12 },
  completed_at: '2026-10-16T10:15:01Z',
}

/** A 404: the scan finished but nothing could be read. */
export const UNABLE_404: ScanResult = {
  ...RUNNING,
  state: 'done',
  status: 'completed',
  verdict: 'UNABLE_TO_VERIFY',
  display_verdict: 'UNABLE_TO_VERIFY',
  score: 0,
  confidence: 'low',
  scope: { mode: 'none', bytes_analyzed: 0, total_bytes: null, range_supported: false, label: 'Nothing was read' },
  headline: 'The server answered 404, so the file could not be fetched.',
  reasons: [
    {
      code: 'FETCH_HTTP_ERROR',
      severity: 'info',
      weight: 0,
      group: 'fetch',
      message: 'The server answered 404, so the file could not be fetched.',
      evidence: { status: 404 },
    },
  ],
  completed_at: '2026-10-16T10:15:01Z',
}

export const REJECTED_DONE: ScanResult = {
  ...RUNNING,
  input_url: 'http://192.168.1.1/admin',
  state: 'done',
  status: 'rejected',
  display_verdict: 'REJECTED',
  scope: { mode: 'none', bytes_analyzed: 0, total_bytes: null, range_supported: false, label: 'Nothing was read' },
  headline: "LinkGuard won't contact this address because it points inside a private network.",
  reasons: [
    {
      code: 'URL_PRIVATE_ADDRESS',
      severity: 'info',
      weight: 0,
      group: 'url',
      message: "LinkGuard won't contact this address because it points inside a private network.",
      evidence: {},
    },
  ],
  completed_at: '2026-10-16T10:15:01Z',
}

export const UNSUPPORTED_DONE: ScanResult = {
  ...RUNNING,
  input_url: 'magnet:?xt=urn:btih:abc',
  state: 'done',
  status: 'unsupported',
  link_type: 'magnet',
  display_verdict: 'UNSUPPORTED',
  scope: { mode: 'none', bytes_analyzed: 0, total_bytes: null, range_supported: false, label: 'Nothing was read' },
  headline: "Magnet links aren't supported yet; they are planned for a later phase.",
  reasons: [
    {
      code: 'LINK_TYPE_UNSUPPORTED',
      severity: 'info',
      weight: 0,
      group: 'link',
      message: "Magnet links aren't supported yet; they are planned for a later phase.",
      evidence: { link_kind: 'Magnet links' },
    },
  ],
  completed_at: '2026-10-16T10:15:01Z',
}

/** Builds a fetch Response with a JSON body. */
export function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

export function errorBody(code: string, message: string) {
  return { schema_version: '1.0', error: { code, message } }
}

export const ACCEPTED = { schema_version: '1.0', scan_id: SCAN_ID, state: 'queued', poll_after_ms: 1 }
