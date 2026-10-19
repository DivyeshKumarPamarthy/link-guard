// The one bold element of the report: what the file claims to be next to what its first
// bytes prove it is. Remote values are shown as escaped text, never as HTML or links.
import type { DisplayVerdict, FileInfo } from '../api/contract.ts'
import { showInvisible } from '../lib/text.ts'
import { HexStrip } from './HexStrip.tsx'

interface Props {
  file: FileInfo
  verdict: DisplayVerdict
}

export function ClaimedVsActual({ file, verdict }: Props) {
  return (
    <section aria-labelledby="claimed-vs-actual" className="rounded-panel border border-line bg-surface p-4 md:p-6">
      <h2 id="claimed-vs-actual" className="text-section font-semibold">
        Claimed vs actual
      </h2>
      <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-6 gap-y-3">
        <dt className="font-medium text-muted">Claimed</dt>
        <dd className="min-w-0 break-words">
          <span className="font-mono">
            {file.claimed_name ? showInvisible(file.claimed_name) : 'No file name given'}
          </span>
          {' · '}
          <span className="font-mono">{file.content_type ?? 'no content type'}</span>
        </dd>
        <dt className="font-medium text-muted">Actual</dt>
        <dd className="font-semibold">{file.detected_label ?? 'Unknown type'}</dd>
        <dt className="font-medium text-muted">First bytes</dt>
        <dd className="min-w-0">
          <HexStrip hex={file.first_bytes_hex} signature={file.signature} verdict={verdict} />
        </dd>
      </dl>
    </section>
  )
}
