// Display helpers for hostile text (filenames, URLs, headers from remote servers).

// Zero-width, bidi marks/embeddings/overrides/isolates, BOM, line/paragraph separators.
const INVISIBLE = /[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff\u2028\u2029]/
// C0 and C1 control characters (includes NUL, tab, newline, ESC).
// eslint-disable-next-line no-control-regex -- matching control characters is the point
const CONTROL = /[\u0000-\u001f\u007f-\u009f]/

/**
 * Show invisible and control characters as visible escapes, e.g. "invoice\u202efdp.exe"
 * is displayed as `invoice\u202efdp.exe` instead of tricking the eye into "invoiceexe.pdf".
 */
export function showInvisible(text: string): string {
  let out = ''
  for (const ch of text) {
    if (INVISIBLE.test(ch) || CONTROL.test(ch)) {
      out += '\\u' + ch.codePointAt(0)!.toString(16).toUpperCase().padStart(4, '0')
    } else {
      out += ch
    }
  }
  return out
}

/**
 * Shorten long text in the middle ("https://files.exa…/movie.mp4") so both the site and the
 * file name stay visible. Text up to `max` characters is returned unchanged.
 */
export function middleTruncate(text: string, max: number): string {
  const chars = [...text]
  if (chars.length <= max) return text
  const keep = max - 1
  const head = Math.ceil(keep / 2)
  return chars.slice(0, head).join('') + '…' + chars.slice(chars.length - (keep - head)).join('')
}

/** Split lowercase hex ("4d5a90") into byte pairs (["4d", "5a", "90"]). */
export function hexPairs(hex: string): string[] {
  return hex.match(/.{2}/g) ?? []
}

/**
 * Human size with 1024-based units: "512 bytes", "47 KB", "5 MB", "1.5 GB". The same rules as
 * the backend's format_size (backend/app/engine/scoring/scope.py), so the scope bar's sizes
 * match the scope label the backend writes.
 */
export function formatSize(n: number): string {
  const oneDecimal = (x: number) => String(Math.round(x * 10) / 10)
  if (n < 1024) return n === 1 ? '1 byte' : `${n} bytes`
  if (n < 1024 ** 2) return `${Math.round(n / 1024)} KB`
  if (n < 1024 ** 3) return `${oneDecimal(n / 1024 ** 2)} MB`
  return `${oneDecimal(n / 1024 ** 3)} GB`
}
