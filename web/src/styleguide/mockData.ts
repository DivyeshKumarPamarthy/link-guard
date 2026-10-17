// Mock data for /styleguide only. Values follow the contract examples in docs/phase1-spec.md §2.
import type { DisplayVerdict, FileInfo } from '../api/contract.ts'

export const SAMPLE_HEADLINES: Record<DisplayVerdict, string> = {
  SAFE: 'No problems found in the whole file',
  NO_ISSUES_IN_CHECKED_PART: 'No issues found in the checked part (first 5 MB of 200 MB)',
  SUSPICIOUS: 'Suspicious: the name hides a .exe file behind .pdf',
  UNSAFE: 'Blocked: file named .mp4 is actually a Windows executable',
  UNABLE_TO_VERIFY: 'The server answered 404, so the file could not be checked',
  REJECTED: "LinkGuard won't contact this address because it points inside a private network.",
  UNSUPPORTED: "Magnet links aren't supported yet",
}

export const DISGUISED_EXE: FileInfo = {
  claimed_name: 'movie.mp4',
  name_source: 'content-disposition',
  content_type: 'video/mp4',
  detected_type: 'pe-executable',
  detected_label: 'Windows executable',
  family: 'executable',
  detection_confidence: 'certain',
  first_bytes_hex: '4d5a90000300000004000000ffff0000',
  signature: { offset: 0, length: 2, name: 'MZ (Windows executable)' },
}

export const GENUINE_PNG: FileInfo = {
  claimed_name: 'photo.png',
  name_source: 'final-url',
  content_type: 'image/png',
  detected_type: 'png',
  detected_label: 'PNG image',
  family: 'image',
  detection_confidence: 'certain',
  first_bytes_hex: '89504e470d0a1a0a0000000d49484452',
  signature: { offset: 0, length: 8, name: 'PNG image' },
}

export const UNKNOWN_BYTES: FileInfo = {
  claimed_name: 'data.bin',
  name_source: 'original-url',
  content_type: null,
  detected_type: null,
  detected_label: null,
  family: 'unknown',
  detection_confidence: 'unconfirmed',
  first_bytes_hex: '0001020304050607',
  signature: null,
}

/** Hostile name: an RTL override and an HTML payload. Must render as plain, escaped text. */
export const SPOOFED_NAME: FileInfo = {
  ...DISGUISED_EXE,
  claimed_name: 'invoice\u202efdp.exe <img src=x onerror=alert(1)>',
  content_type: 'application/pdf',
}
