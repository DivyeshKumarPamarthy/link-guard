// Tolerant reader for API responses (contract v1, docs/phase1-spec.md §2).
// Clients must ignore unknown fields and refuse a schema major version they don't know.
import type { components } from './types.ts'

export type ScanResult = components['schemas']['ScanResult']
export type ScanAccepted = components['schemas']['ScanAccepted']
export type ErrorBody = components['schemas']['ErrorBody']
export type DisplayVerdict = components['schemas']['DisplayVerdict']
export type Reason = components['schemas']['Reason']
export type FileInfo = components['schemas']['FileInfo']

export const SUPPORTED_SCHEMA_MAJOR = '1'

export class ContractError extends Error {}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** Accept any 1.x response. Unknown fields are kept but never read, so they are harmless. */
export function readScanResult(data: unknown): ScanResult {
  if (!isObject(data)) throw new ContractError('The response is not a JSON object.')
  const version = data.schema_version
  if (typeof version !== 'string' || version.split('.')[0] !== SUPPORTED_SCHEMA_MAJOR) {
    throw new ContractError(`Unsupported schema_version: ${String(version)}`)
  }
  if (typeof data.scan_id !== 'string' || typeof data.state !== 'string') {
    throw new ContractError('The response is missing scan_id or state.')
  }
  return data as unknown as ScanResult
}
