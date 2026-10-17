// Contract test on the client side (T0.4): the backend's own example JSON must be readable,
// and unknown extra fields must be tolerated.
import { describe, expect, test } from 'vitest'
import unsafeExample from '../../../backend/tests/contract/examples/scan_result_unsafe.json'
import queuedExample from '../../../backend/tests/contract/examples/scan_result_queued.json'
import { ContractError, readScanResult } from './contract.ts'

describe('readScanResult', () => {
  test('reads the spec example', () => {
    const result = readScanResult(unsafeExample)
    expect(result.display_verdict).toBe('UNSAFE')
    expect(result.file?.signature?.name).toBe('MZ (Windows executable)')
  })

  test('reads a queued scan with null outcome fields', () => {
    expect(readScanResult(queuedExample).verdict).toBeNull()
  })

  test('tolerates unknown extra fields', () => {
    const withExtras = { ...unsafeExample, added_in_1_1: { anything: true }, schema_version: '1.1' }
    expect(readScanResult(withExtras).headline).toBe(unsafeExample.headline)
  })

  test('refuses an unknown major version', () => {
    expect(() => readScanResult({ ...unsafeExample, schema_version: '2.0' })).toThrow(ContractError)
  })

  test.each([null, 'text', [1], {}])('refuses a non-result %#', (value) => {
    expect(() => readScanResult(value)).toThrow(ContractError)
  })
})
