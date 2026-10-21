// A remote URL shown as mono text: never a link, invisible characters escaped, long values
// shortened in the middle with a "Show all" button, and a "Copy URL" button (style guide).
import { useState } from 'react'
import { URL_DISPLAY_CHARS } from '../config.ts'
import { middleTruncate, showInvisible } from '../lib/text.ts'

const buttonClass =
  'rounded-control border border-line px-2 py-0.5 text-small font-medium text-brand hover:bg-paper'

export function UrlText({ url }: { url: string }) {
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
    <span className="inline-flex min-w-0 flex-wrap items-center gap-2">
      <span className="min-w-0 break-all font-mono">
        {expanded || !isLong ? shown : middleTruncate(shown, URL_DISPLAY_CHARS)}
      </span>
      {isLong && (
        <button type="button" className={buttonClass} onClick={() => setExpanded(!expanded)}>
          {expanded ? 'Show less' : 'Show all'}
        </button>
      )}
      <button type="button" className={buttonClass} onClick={copy}>
        {copied ? 'Copied' : 'Copy URL'}
      </button>
    </span>
  )
}
