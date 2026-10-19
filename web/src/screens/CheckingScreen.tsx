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
    <div className="space-y-2">
      <p className="text-section font-semibold">Checking… {seconds} s</p>
      <p className="break-all font-mono text-muted">{middleTruncate(showInvisible(url.trim()), URL_DISPLAY_CHARS)}</p>
    </div>
  )
}
