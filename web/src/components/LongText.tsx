// The link the user pasted, at the top of a report: mono text, never a link, invisible
// characters escaped, long values shortened in the middle, with "Copy URL" and (for long
// links) "Show all" buttons underneath (style guide).
import { useState } from 'react'
import { URL_DISPLAY_CHARS } from '../config.ts'
import { middleTruncate, showInvisible } from '../lib/text.ts'
import { smallButton } from './buttons.ts'

export function UrlText({ url, label }: { url: string; label: string }) {
  const [expanded, setExpanded] = useState(false)
  const [copied, setCopied] = useState(false)
  const shown = showInvisible(url)
  const isLong = [...shown].length > URL_DISPLAY_CHARS

  async function copy() {
    // The clipboard gets the real URL; the screen shows the escaped form.
    try {
      await navigator.clipboard.writeText(url)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }

  return (
    <div className="space-y-2">
      <p className="text-label leading-relaxed text-muted">
        {label}{' '}
        <span className="font-mono text-small break-all text-ink">
          {expanded || !isLong ? shown : middleTruncate(shown, URL_DISPLAY_CHARS)}
        </span>
      </p>
      <div className="flex flex-wrap gap-2">
        <button type="button" className={smallButton} onClick={copy}>
          {copied ? 'Copied' : 'Copy URL'}
        </button>
        {isLong && (
          <button
            type="button"
            className={smallButton}
            aria-expanded={expanded}
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? 'Show less' : 'Show all'}
          </button>
        )}
      </div>
    </div>
  )
}
