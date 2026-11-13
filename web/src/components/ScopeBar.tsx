// Inside a "No issues in the checked part" band: a bar showing how much of the file was read,
// with the two sizes written out (the bar itself is decoration; the words carry the meaning).
// It only appears when the server told us the total size, so it never guesses.
import type { components } from '../api/types.ts'
import { formatSize } from '../lib/text.ts'

type Scope = components['schemas']['Scope']

/** The thinnest visible sliver, so 5 MB of 200 GB still shows as "something was read". */
const MIN_FILL_PX = 6

export function ScopeBar({ scope }: { scope: Scope }) {
  const total = scope.total_bytes
  const read = scope.bytes_analyzed
  if (total === null || total <= 0 || read >= total) return null
  const percent = (read / total) * 100

  return (
    <div className="mt-2 space-y-1.5">
      <div aria-hidden="true" className="flex h-2.5 rounded-[2px] border border-no-issues-fg">
        <div className="bg-no-issues-fg" style={{ width: `${percent}%`, minWidth: MIN_FILL_PX }} />
      </div>
      <div className="flex flex-wrap justify-between gap-x-4 gap-y-1 text-label text-ink">
        <span>Read: first {formatSize(read)}</span>
        <span>Not read: the other {formatSize(total - read)}</span>
      </div>
    </div>
  )
}
