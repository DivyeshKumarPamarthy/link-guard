// The one bold element of the report: what the file claims to be next to what its first
// bytes prove it is. Two cells side by side (stacked on a phone), then the first bytes.
// When the detected type is the problem, the "Actual" cell takes the verdict's tint.
// Remote values are shown as escaped text, never as HTML or links.
import type { DisplayVerdict, FileInfo } from '../api/contract.ts'
import { showInvisible } from '../lib/text.ts'
import { HexStrip } from './HexStrip.tsx'
import { highlightsActual, VERDICTS } from './verdicts.ts'

interface Props {
  file: FileInfo
  verdict: DisplayVerdict
}

// Where the claimed name came from, in the order the backend tries them (spec §7).
const NAME_SOURCE: Record<string, string> = {
  'content-disposition': "Name from the server's download header",
  'final-url': 'Name from the address the link ended at',
  'original-url': 'Name from the link you pasted',
}

// How sure the detector is; "probable" covers e.g. a program whose header lies past the bytes read.
const DETECTION_CONFIDENCE: Record<string, string> = {
  certain: 'Certain',
  probable: 'Probable',
  unconfirmed: 'Not confirmed',
}

const cellBox = 'flex min-w-0 flex-col gap-1.5 px-5 pt-4.5 pb-5'
const cellLabel = 'text-small font-semibold'

export function ClaimedVsActual({ file, verdict }: Props) {
  // Unknown values from a newer backend show nothing rather than a raw enum word.
  const nameSource = file.name_source ? NAME_SOURCE[file.name_source] : undefined
  const confidence = file.detection_confidence ? DETECTION_CONFIDENCE[file.detection_confidence] : undefined
  const { text, tint } = VERDICTS[verdict]
  const flagged = highlightsActual(verdict)

  return (
    <section aria-labelledby="claimed-vs-actual" className="space-y-2.5">
      <h2 id="claimed-vs-actual" className="text-label font-semibold text-muted">
        Claimed vs actual
      </h2>
      {/* 1 px gaps over a `line` background draw the dividers between the cells. */}
      <div className="flex flex-wrap gap-px overflow-hidden rounded-panel border border-line bg-line">
        <div className={`${cellBox} flex-[1_1_250px] bg-surface`}>
          <span className={`${cellLabel} text-muted`}>Claimed</span>
          <span className="font-mono text-evidence font-medium break-all">
            {file.claimed_name ? showInvisible(file.claimed_name) : 'No file name given'}
          </span>
          <span className="font-mono text-label break-all">{file.content_type ?? 'no content type'}</span>
          {nameSource && <span className="mt-1 text-small text-muted">{nameSource}</span>}
        </div>
        <div className={`${cellBox} flex-[1_1_250px] ${flagged ? tint : 'bg-surface'}`}>
          <span className={`${cellLabel} ${flagged ? 'text-ink' : 'text-muted'}`}>Actual</span>
          <span className={`text-evidence font-semibold break-words ${flagged ? text : 'text-ink'}`}>
            {file.detected_label ?? 'Unknown type'}
          </span>
          {confidence && <span className="text-label text-ink">{confidence}</span>}
        </div>
        <div className={`${cellBox} flex-[1_1_100%] gap-2.5 bg-surface`}>
          <span className={`${cellLabel} text-muted`}>First bytes</span>
          <HexStrip hex={file.first_bytes_hex} signature={file.signature} verdict={verdict} />
        </div>
      </div>
    </section>
  )
}
