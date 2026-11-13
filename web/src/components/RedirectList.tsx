// "Where the link went": a numbered list because the hops are a sequence (style guide).
// Each hop URL is shown in full as wrapped mono text, never a link; a blocked hop is bold.
import type { components } from '../api/types.ts'
import { showInvisible } from '../lib/text.ts'

type RedirectHop = components['schemas']['RedirectHop']

export function RedirectList({ hops }: { hops: RedirectHop[] }) {
  if (hops.length === 0) return null
  return (
    <section aria-labelledby="where-the-link-went" className="space-y-2.5">
      <h2 id="where-the-link-went" className="text-label font-semibold text-muted">
        Where the link went
      </h2>
      <ol className="border-b border-line">
        {hops.map((hop, i) => {
          const value = `text-ink ${hop.address_class === 'blocked' ? 'font-semibold' : ''}`
          return (
            <li key={i} className="grid grid-cols-[24px_minmax(0,1fr)] gap-x-3 gap-y-1 border-t border-line py-3">
              <span className="font-mono text-label leading-relaxed text-muted">{i + 1}</span>
              <div className="flex min-w-0 flex-col gap-1">
                <span className="font-mono text-label leading-relaxed break-all">{showInvisible(hop.url)}</span>
                <div className="flex flex-wrap gap-x-5 gap-y-0.5 text-small text-muted">
                  <span>
                    Status: <span className={value}>{hop.status ?? 'no answer'}</span>
                  </span>
                  <span>
                    Address: <span className={value}>{hop.address_class}</span>
                  </span>
                </div>
              </div>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
