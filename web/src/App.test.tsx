// End-to-end tests of the web app against a fake backend (no real server, no internet):
// submit → poll → report, every result screen, the error states and hostile remote text.
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'
import type { ScanResult } from './api/contract.ts'
import App from './App.tsx'
import { SPOOFED_NAME } from './styleguide/mockData.ts'
import {
  ACCEPTED,
  REJECTED_DONE,
  RUNNING,
  UNABLE_404,
  UNSAFE_DONE,
  UNSUPPORTED_DONE,
  errorBody,
  jsonResponse,
} from './test/fixtures.ts'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

type Answer = Response | Error

/** Fake backend: POST answers come from `post`, GET answers from `gets` in order. */
function fakeBackend(post: () => Answer, gets: (() => Answer)[] = []) {
  const calls: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      calls.push(`${method} ${new URL(url).pathname}`)
      const answer = method === 'POST' ? post() : (gets.shift() ?? (() => jsonResponse(404, {})))()
      if (answer instanceof Error) throw answer
      return answer
    }),
  )
  return calls
}

const accepted = () => jsonResponse(202, ACCEPTED)
const done = (result: ScanResult) => () => jsonResponse(200, result)

function submit(url: string) {
  fireEvent.change(screen.getByLabelText('Link to check'), { target: { value: url } })
  fireEvent.click(screen.getByRole('button', { name: 'Check link' }))
}

describe('home', () => {
  test('shows the title, the labelled input, the button and what we check', () => {
    render(<App />)
    expect(screen.getByRole('heading', { name: 'LinkGuard' })).toBeDefined()
    expect(screen.getByLabelText('Link to check')).toBeDefined()
    expect(screen.getByRole('button', { name: 'Check link' })).toBeDefined()
    expect(screen.getByText("The file's real type, read from its first bytes")).toBeDefined()
    expect(screen.getByRole('main').getAttribute('aria-live')).toBe('polite')
  })
})

describe('submit and polling', () => {
  test('shows the checking screen, polls until done, then renders the report', async () => {
    const calls = fakeBackend(accepted, [done(RUNNING), done({ ...RUNNING, state: 'queued' }), done(UNSAFE_DONE)])
    render(<App />)
    submit('https://short.example/abc')

    expect(screen.getByText(/Checking… 0 s/)).toBeDefined()
    expect(screen.getByText('https://short.example/abc')).toBeDefined()
    // the submit button is gone while the scan is in flight
    expect(screen.queryByRole('button', { name: 'Check link' })).toBeNull()

    expect(await screen.findByText('Unsafe')).toBeDefined()
    expect(calls).toEqual([
      'POST /api/scans',
      `GET /api/scans/${ACCEPTED.scan_id}`,
      `GET /api/scans/${ACCEPTED.scan_id}`,
      `GET /api/scans/${ACCEPTED.scan_id}`,
    ])
  })

  test('the report shows headline, claimed vs actual, reasons, redirects and details', async () => {
    fakeBackend(accepted, [done(UNSAFE_DONE)])
    render(<App />)
    submit('https://short.example/abc')

    expect(await screen.findByText('Blocked: file named .mp4 is actually a Windows executable')).toBeDefined()
    expect(screen.getByRole('heading', { name: 'Claimed vs actual' })).toBeDefined()
    expect(screen.getByText('Highlighted: MZ (Windows executable)')).toBeDefined()
    expect(screen.getByText('The file is named .mp4 but its content is a Windows executable.')).toBeDefined()
    const why = screen.getByRole('heading', { name: 'Why' }).parentElement!
    expect(within(why).getByText('High')).toBeDefined()
    const hops = screen.getByRole('heading', { name: 'Where the link went' }).parentElement!
    expect(hops.querySelectorAll('li')).toHaveLength(2)
    expect(screen.getByText('Whole file checked (47 KB)')).toBeDefined()
    expect(screen.getByText('70 / 100')).toBeDefined()
    expect(screen.getByText('812 ms total, 640 ms fetch')).toBeDefined()
    expect(screen.getByText('1.0.0 / 1.0.0')).toBeDefined()
  })

  test('scanned URLs are never clickable links', async () => {
    fakeBackend(accepted, [done(UNSAFE_DONE)])
    render(<App />)
    submit('https://short.example/abc')
    await screen.findByText('Unsafe')
    const hrefs = [...document.querySelectorAll('a')].map((a) => a.getAttribute('href'))
    expect(hrefs).toEqual(['/']) // only the LinkGuard header link
    expect(screen.getAllByRole('button', { name: 'Copy URL' }).length).toBeGreaterThan(0)
  })

  test('"Check another link" goes back to an empty home screen', async () => {
    fakeBackend(accepted, [done(UNSAFE_DONE)])
    render(<App />)
    submit('https://short.example/abc')
    fireEvent.click(await screen.findByRole('button', { name: 'Check another link' }))
    expect((screen.getByLabelText('Link to check') as HTMLInputElement).value).toBe('')
  })
})

describe('result screens', () => {
  test('unable to verify: neutral band, why, what to try, check again; never "Safe"', async () => {
    const calls = fakeBackend(accepted, [done(UNABLE_404), done(UNABLE_404)])
    render(<App />)
    submit('https://a.example/missing.zip')

    expect(await screen.findByText('Unable to verify')).toBeDefined()
    expect(screen.getByText('What you can try')).toBeDefined()
    expect(screen.getByText('Check the link is complete and still works in your browser.')).toBeDefined()
    expect(screen.getByText('Nothing was read')).toBeDefined()
    expect(screen.queryByText(/^Safe$/)).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Check again' }))
    expect(await screen.findByText('Unable to verify')).toBeDefined()
    expect(calls.filter((c) => c.startsWith('POST'))).toHaveLength(2)
  })

  test('rejected: explains the block without internal details', async () => {
    fakeBackend(accepted, [done(REJECTED_DONE)])
    render(<App />)
    submit('http://192.168.1.1/admin')

    expect(await screen.findByText('Not scanned: blocked address')).toBeDefined()
    expect(
      screen.getByText("LinkGuard won't contact this address because it points inside a private network."),
    ).toBeDefined()
    expect(screen.queryByText('Details')).toBeNull()
    expect(screen.queryByRole('heading', { name: 'Why' })).toBeNull()
  })

  test('unsupported: names the link type', async () => {
    fakeBackend(accepted, [done(UNSUPPORTED_DONE)])
    render(<App />)
    submit('magnet:?xt=urn:btih:abc')

    expect(await screen.findByText('Not supported yet')).toBeDefined()
    expect(screen.getByText("Magnet links aren't supported yet; they are planned for a later phase.")).toBeDefined()
  })

  test('an unknown reason code renders as a generic card: code + message', async () => {
    const unknown = { code: 'NEW_CHECK_FROM_V1_1', severity: 'low' as const, weight: 5, group: 'new', message: 'A newer check found something.', evidence: {} }
    fakeBackend(accepted, [done({ ...UNSAFE_DONE, reasons: [unknown] })])
    render(<App />)
    submit('https://short.example/abc')

    expect(await screen.findByText('NEW_CHECK_FROM_V1_1')).toBeDefined()
    expect(screen.getByText(/A newer check found something\./)).toBeDefined()
  })
})

describe('error states', () => {
  test.each([
    ['URL_EMPTY', 'Paste a link to check.'],
    ['URL_MULTIPLE', 'Paste one link at a time.'],
    ['URL_TOO_LONG', 'This link is longer than 2048 characters.'],
  ])('400 %s shows the message under the input and keeps focus there', async (code, message) => {
    fakeBackend(() => jsonResponse(400, errorBody(code, message)))
    render(<App />)
    submit('one two')

    expect(await screen.findByText(message)).toBeDefined()
    const input = screen.getByLabelText('Link to check') as HTMLInputElement
    expect(input.getAttribute('aria-invalid')).toBe('true')
    expect(input.getAttribute('aria-describedby')).toBe('link-error')
    expect(document.activeElement).toBe(input)
    expect(input.value).toBe('one two')
  })

  test('server unreachable: says how to start it, and "Try again" resubmits', async () => {
    let up = false
    const calls = fakeBackend(() => (up ? jsonResponse(202, ACCEPTED) : new TypeError('Failed to fetch')), [done(UNSAFE_DONE)])
    render(<App />)
    submit('https://short.example/abc')

    expect(await screen.findByText("Can't reach the LinkGuard server.")).toBeDefined()
    expect(screen.getByText('Start it with `make dev`, then try again.')).toBeDefined()

    up = true
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('Unsafe')).toBeDefined()
    expect(calls.filter((c) => c.startsWith('POST'))).toHaveLength(2)
  })

  test('503 busy: asks to try again in a few seconds, with no automatic retry', async () => {
    const calls = fakeBackend(() => jsonResponse(503, errorBody('SERVER_BUSY', 'busy')))
    render(<App />)
    submit('https://short.example/abc')

    expect(await screen.findByText('LinkGuard is checking other links.')).toBeDefined()
    expect(screen.getByText('Try again in a few seconds.')).toBeDefined()
    expect(calls).toEqual(['POST /api/scans'])
  })

  test('500 on submit: something went wrong', async () => {
    fakeBackend(() => jsonResponse(500, errorBody('INTERNAL_ERROR', 'boom')))
    render(<App />)
    submit('https://short.example/abc')

    expect(await screen.findByText('Something went wrong on the LinkGuard server.')).toBeDefined()
    expect(screen.queryByText('boom')).toBeNull() // server text is never shown for 500
  })

  test('an error while polling also shows the error screen', async () => {
    fakeBackend(accepted, [done(RUNNING), () => jsonResponse(500, errorBody('INTERNAL_ERROR', 'x'))])
    render(<App />)
    submit('https://short.example/abc')

    expect(await screen.findByText('Something went wrong on the LinkGuard server.')).toBeDefined()
  })

  test('the error screen is not a verdict: no verdict words', async () => {
    fakeBackend(() => new TypeError('Failed to fetch'))
    render(<App />)
    submit('https://short.example/abc')
    await screen.findByRole('alert')
    for (const word of ['Safe', 'Unsafe', 'Unable to verify']) {
      expect(screen.queryByText(word)).toBeNull()
    }
  })
})

describe('hostile remote text', () => {
  const HOSTILE = '<img src=x onerror=alert(1)>'

  test('renders a hostile filename as text, never as HTML', async () => {
    const result = { ...UNSAFE_DONE, file: { ...SPOOFED_NAME, claimed_name: HOSTILE } }
    fakeBackend(accepted, [done(result)])
    render(<App />)
    submit('https://short.example/abc')

    expect(await screen.findByText(HOSTILE)).toBeDefined()
    expect(document.querySelector('img')).toBeNull()
  })

  test('hostile URLs, headline and reason text stay text; bidi overrides are shown escaped', async () => {
    const rtl = String.fromCodePoint(0x202e)
    const result: ScanResult = {
      ...UNSAFE_DONE,
      input_url: `https://evil.example/${HOSTILE}`,
      headline: `Headline ${HOSTILE}`,
      redirects: [{ url: `https://evil.example/${rtl}gpj.exe`, status: 200, address_class: 'public' }],
      reasons: [{ ...UNSAFE_DONE.reasons![0], message: `Reason ${HOSTILE}` }],
    }
    fakeBackend(accepted, [done(result)])
    render(<App />)
    submit('https://evil.example/x')

    expect(await screen.findByText(`Headline ${HOSTILE}`)).toBeDefined()
    expect(document.querySelector('img')).toBeNull()
    expect(document.body.textContent).toContain(`Reason ${HOSTILE}`)
    expect(document.body.textContent).toContain('\\u202Egpj.exe')
    expect(document.body.textContent).not.toContain(rtl)
  })
})
