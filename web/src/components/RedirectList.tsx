// "Where the link went": a numbered list because the hops are a sequence (style guide).
import type { components } from '../api/types.ts'
import { UrlText } from './LongText.tsx'

type RedirectHop = components['schemas']['RedirectHop']

export function RedirectList({ hops }: { hops: RedirectHop[] }) {
  if (hops.length === 0) return null
  return (
    <section aria-labelledby="where-the-link-went">
      <h2 id="where-the-link-went" className="text-section font-semibold">
        Where the link went
      </h2>
      <ol className="mt-2 space-y-2">
        {hops.map((hop, i) => (
          <li key={i} className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
            <span className="w-4 shrink-0 font-medium text-muted">{i + 1}</span>
            <UrlText url={hop.url} />
            <span className="font-mono text-small">{hop.status ?? 'no answer'}</span>
            <span className="text-small text-muted">{hop.address_class}</span>
          </li>
        ))}
      </ol>
    </section>
  )
}
