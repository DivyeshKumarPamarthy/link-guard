// Screen 2: "Checking… 4 s" and the submitted URL, nothing else (style guide).
import { useEffect, useState } from 'react'
import { URL_DISPLAY_CHARS } from '../config.ts'
import { middleTruncate, showInvisible } from '../lib/text.ts'

export function CheckingScreen({ url }: { url: string }) {
  const [seconds, setSeconds] = useState(0)

  useEffect(() => {
    const timer = setInterval(() => setSeconds((s) => s + 1), 1000)
    return () => clearInterval(timer)
  }, [])

  return (
    <div className="space-y-3 border-y border-line py-7">
      {/* tabular-nums keeps the line from jiggling as the seconds tick */}
      <h1 className="text-title font-semibold tracking-[-0.01em] tabular-nums">Checking… {seconds} s</h1>
      <p className="font-mono text-label leading-relaxed break-all text-muted">
        {middleTruncate(showInvisible(url.trim()), URL_DISPLAY_CHARS)}
      </p>
    </div>
  )
}
