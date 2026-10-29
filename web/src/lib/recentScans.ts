// Recent scans stored in browser localStorage only (spec §10 P1, decision D33).
// Never sent to the server; corrupt or unavailable storage is ignored gracefully.
import type { DisplayVerdict, ScanResult } from '../api/contract.ts'
import { VERDICTS } from '../components/verdicts.ts'
import { MAX_RECENT_SCANS, RECENT_SCANS_STORAGE_KEY } from '../config.ts'

export interface RecentScan {
  scan_id: string
  url: string
  display_verdict: DisplayVerdict
  time: string
}

function isRecentScan(item: unknown): item is RecentScan {
  if (typeof item !== 'object' || item === null) return false
  const record = item as Record<string, unknown>
  return (
    typeof record.scan_id === 'string' &&
    typeof record.url === 'string' &&
    typeof record.time === 'string' &&
    typeof record.display_verdict === 'string' &&
    record.display_verdict in VERDICTS
  )
}

export function loadRecentScans(): RecentScan[] {
  try {
    const raw = window.localStorage.getItem(RECENT_SCANS_STORAGE_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(isRecentScan).slice(0, MAX_RECENT_SCANS)
  } catch {
    return []
  }
}

export function saveRecentScan(result: ScanResult): RecentScan[] {
  if (!result.display_verdict) return loadRecentScans()
  const entry: RecentScan = {
    scan_id: result.scan_id,
    url: result.input_url,
    display_verdict: result.display_verdict,
    time: result.completed_at ?? result.created_at,
  }
  const existing = loadRecentScans().filter((item) => item.scan_id !== entry.scan_id)
  const updated = [entry, ...existing].slice(0, MAX_RECENT_SCANS)
  try {
    window.localStorage.setItem(RECENT_SCANS_STORAGE_KEY, JSON.stringify(updated))
  } catch {
    // Private browsing or quota exceeded: keep working in memory.
  }
  return updated
}

export function clearRecentScans(): void {
  try {
    window.localStorage.removeItem(RECENT_SCANS_STORAGE_KEY)
  } catch {
    // Ignore storage errors.
  }
}
