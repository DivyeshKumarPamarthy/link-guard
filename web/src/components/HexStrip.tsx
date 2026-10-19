// The first 16 bytes as hex pairs. The bytes that identified the file type are
// highlighted with the verdict's tint and underlined, with a caption naming them.
import type { DisplayVerdict, FileInfo } from '../api/contract.ts'
import { hexPairs } from '../lib/text.ts'
import { VERDICTS } from './verdicts.ts'

interface Props {
  hex: string
  signature: FileInfo['signature']
  verdict: DisplayVerdict
}

export function HexStrip({ hex, signature, verdict }: Props) {
  const { text, tint } = VERDICTS[verdict]
  const pairs = hexPairs(hex)
  const isSignature = (i: number) =>
    signature !== null && i >= signature.offset && i < signature.offset + signature.length

  return (
    <div>
      <p className="flex flex-wrap gap-x-2 gap-y-1 font-mono text-body" aria-label="First bytes">
        {pairs.map((pair, i) =>
          isSignature(i) ? (
            <mark key={i} className={`rounded-sm px-0.5 underline underline-offset-4 ${text} ${tint}`}>
              {pair}
            </mark>
          ) : (
            <span key={i} className="px-0.5">
              {pair}
            </span>
          ),
        )}
        {pairs.length === 0 && <span className="text-muted">No bytes were read</span>}
      </p>
      <p className="mt-1 text-small text-muted">
        {signature
          ? `Highlighted: ${signature.name}`
          : 'No known signature in the first bytes'}
      </p>
    </div>
  )
}
