// "What you can try" on the Unable-to-verify screen. Web-app copy keyed by reason code (D33);
// the registry keeps one message per code, these are the next steps for the user.
const HINTS: Record<string, string[]> = {
  FETCH_HTTP_ERROR: ['Check the link is complete and still works in your browser.'],
  FETCH_AUTH_REQUIRED: [
    'Check the link is complete and still works in your browser.',
    "If the site needs a login, LinkGuard can't check it.",
  ],
  FETCH_TIMEOUT: ['The site may be slow right now. Try again in a minute.'],
  FETCH_INTERRUPTED: ['The site may be slow right now. Try again in a minute.'],
  FETCH_RATE_LIMITED: ['Wait a little while, then check the link again.'],
  FETCH_TLS_ERROR: ['Be careful: the site could not prove who it is. Get the link from a source you trust.'],
  FETCH_DNS_ERROR: ['Check the address for typing mistakes.'],
  FETCH_EMPTY: ['The file is empty. Ask the sender for a working link.'],
  LINK_IS_WEB_PAGE: ['Open the page in your browser and copy the direct download link instead.'],
  REDIR_LOOP: ['The link is broken. Ask the sender for a direct download link.'],
  REDIR_TOO_MANY: ['Ask the sender for a direct download link.'],
}

const DEFAULT_HINT = ['Check the link is complete, then try again.']

/** Hints for every reason that has some, duplicates removed; a general hint otherwise. */
export function hintsFor(codes: string[]): string[] {
  const hints = codes.flatMap((code) => HINTS[code] ?? [])
  return hints.length > 0 ? [...new Set(hints)] : DEFAULT_HINT
}
