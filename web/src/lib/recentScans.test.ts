import { beforeEach, describe, expect, test } from 'vitest'
import { RECENT_SCANS_STORAGE_KEY } from '../config.ts'
import { UNSAFE_DONE } from '../test/fixtures.ts'
import { clearRecentScans, loadRecentScans, saveRecentScan } from './recentScans.ts'

beforeEach(() => {
  window.localStorage.clear()
})

describe('recentScans', () => {
  test('starts empty and saves completed scans newest first', () => {
    expect(loadRecentScans()).toEqual([])
    saveRecentScan(UNSAFE_DONE)
    const second = { ...UNSAFE_DONE, scan_id: '00000000-0000-4000-8000-000000000002', input_url: 'https://a.example/2.pdf' }
    const list = saveRecentScan(second)
    expect(list).toHaveLength(2)
    expect(list[0]?.scan_id).toBe(second.scan_id)
    expect(list[1]?.scan_id).toBe(UNSAFE_DONE.scan_id)
  })

  test('caps the list at 20 entries', () => {
    for (let i = 0; i < 25; i++) {
      saveRecentScan({
        ...UNSAFE_DONE,
        scan_id: `00000000-0000-4000-8000-${String(i).padStart(12, '0')}`,
        input_url: `https://a.example/${i}.pdf`,
      })
    }
    const list = loadRecentScans()
    expect(list).toHaveLength(20)
    expect(list[0]?.url).toBe('https://a.example/24.pdf')
  })

  test('tolerates corrupt JSON in localStorage and clears cleanly', () => {
    window.localStorage.setItem(RECENT_SCANS_STORAGE_KEY, '{not valid json')
    expect(loadRecentScans()).toEqual([])
    saveRecentScan(UNSAFE_DONE)
    expect(loadRecentScans()).toHaveLength(1)
    clearRecentScans()
    expect(loadRecentScans()).toEqual([])
  })
})
