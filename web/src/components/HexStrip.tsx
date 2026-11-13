// The first 16 bytes as hex pairs, in two rows of eight fixed-width cells so the bytes line
// up like a hex viewer. The bytes that identified the file type are highlighted with the
// verdict's tint, bold and underlined, with a caption naming them.
import type { DisplayVerdict, FileInfo } from '../api/contract.ts'
import { hexPairs } from '../lib/text.ts'
import { VERDICTS } from './verdicts.ts'

interface Props {
  hex: string
  signature: FileInfo['signature']
  verdict: DisplayVerdict
}

const BYTES_PER_GROUP = 8
const cell = 'flex h-7.5 items-center justify-center rounded-badge'

export function HexStrip({ hex, signature, verdict }: Props) {
  const { text, tint } = VERDICTS[verdict]
  const pairs = hexPairs(hex)
  const isSignature = (i: number) =>
    signature !== null && i >= signature.offset && i < signature.offset + signature.length

  const groups: string[][] = []
  for (let i = 0; i < pairs.length; i += BYTES_PER_GROUP) groups.push(pairs.slice(i, i + BYTES_PER_GROUP))

  return (
    <div className="space-y-2.5">
      <div className="flex flex-wrap gap-x-4.5 gap-y-1.5 font-mono text-[15px] leading-none" aria-label="First bytes">
        {groups.map((group, g) => (
          <div key={g} className="grid grid-cols-[repeat(8,30px)] gap-1">
            {group.map((pair, j) => {
              const i = g * BYTES_PER_GROUP + j
              return isSignature(i) ? (
                <mark key={i} className={`${cell} font-semibold underline underline-offset-3 ${text} ${tint}`}>
                  {pair}
                </mark>
              ) : (
                <span key={i} className={cell}>
                  {pair}
                </span>
              )
            })}
          </div>
        ))}
        {pairs.length === 0 && <span className="text-body text-muted">No bytes were read</span>}
      </div>
      <p className="text-small break-words text-muted">
        {signature ? `Highlighted: ${signature.name}` : 'No known signature in the first bytes'}
      </p>
    </div>
  )
}
