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

/** Split lowercase hex ("4d5a90") into byte pairs (["4d", "5a", "90"]). */
export function hexPairs(hex: string): string[] {
  return hex.match(/.{2}/g) ?? []
}
