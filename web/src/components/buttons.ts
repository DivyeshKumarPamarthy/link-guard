// The three button looks, written once so every screen matches (docs/ui-style-guide.md).
// Buttons are at least 44 px tall so they are easy to hit on a phone. No hover effects (D79).

/** The one main action on a screen: "Check link", "Check another link", "Try again". */
export const primaryButton =
  'inline-flex min-h-12 cursor-pointer items-center rounded-control border border-brand bg-brand px-5.5 font-semibold text-surface'

/** A second action next to the primary one, e.g. "Check another link" beside "Check again". */
export const secondaryButton =
  'inline-flex min-h-12 cursor-pointer items-center rounded-control border border-muted bg-transparent px-5.5 font-semibold text-ink'

/** Small actions: "Copy URL", "Show all", "Check again" on a recent scan. */
export const smallButton =
  'inline-flex min-h-11 cursor-pointer items-center rounded-control border border-muted bg-transparent px-3.5 text-label font-medium text-ink'
