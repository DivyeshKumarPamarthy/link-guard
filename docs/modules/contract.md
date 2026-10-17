# Module: API contract v1 (M1, task T0.4)

Owner: TBD (track B, D16 open) · Reviewer: TBD · Phase: A · Last updated: 2026-10-17

## What it does (2–3 sentences, plain language)

Defines, as Pydantic models, exactly what the API accepts and returns: the scan request, the
202 "accepted" reply, the full `ScanResult` and the error body. FastAPI turns these models into
`backend/openapi.json`, and `openapi-typescript` turns that into `web/src/api/types.ts`, so the
backend and web app share one definition.

## Inputs and outputs
- Input: Python models in `backend/app/contract/models.py`.
- Output: `backend/openapi.json` and `web/src/api/types.ts` (via `make openapi`); `readScanResult()` on the web side.

## How it works (5–10 lines; the steps you would draw on a whiteboard)

1. Enums (`State`, `Status`, `Verdict`, `DisplayVerdict`, `ScopeMode`, …) list every allowed value from spec §2.
2. Nested models: `Scope`, `FileInfo` (with `first_bytes_hex` and `Signature`), `RedirectHop`, `Reason`.
3. Every model ignores unknown fields (tolerant reader), so 1.x can add fields without breaking clients.
4. A validator on `ScanResult` enforces the outcome rules (D29): outcome fields null until `done`;
   verdict only for `completed`; REJECTED/UNSUPPORTED match status; plain SAFE only for full scope with confidence ≥ medium.
5. `scripts/export_openapi.py` writes OpenAPI (sorted keys, so the output is stable); FastAPI's unused 422 is removed (D25).
6. In responses every field is marked required, because the backend always sends it (null when empty).
7. Web: `readScanResult()` accepts any `1.x` version and refuses `2.x`.

## Why it is designed this way (the decision and the simpler/harder alternative you rejected)

- One source of truth: hand-written TypeScript types would drift from the backend.
- The honesty rules live in the contract, not only in the scorer, so *no* code path can store or return a dishonest result.
- Rejected: strict "forbid extra fields" for readers; it would break old clients whenever a field is added.

## How it is tested (test files, acceptance rows it covers)

- `backend/tests/contract/test_models.py` (25): spec examples validate and round-trip unchanged; extras tolerated; unknown codes accepted; bad versions, negative weights and bad hex refused; every outcome rule.
- `backend/tests/contract/test_openapi.py` (3): the committed `openapi.json` equals the live app; only two endpoints; no 422.
- `web/src/api/contract.test.ts` (8): the backend's example JSON reads on the web side; extras tolerated; v2 refused.
- CI job "contract" regenerates both files and fails on any difference.

## Known limitations

- `detected_type` is an open string until T1.5 fixes the type names (D24).
- The spec §2 example `scan_id` (`9f3c2d1e-…`) was not a valid UUID; the test fixture uses a full one.

## Likely viva questions (and your short answers)

- *How do backend and web stay in sync?* Types are generated from the backend's models; CI fails if they differ.
- *What happens when you add a field?* Old clients ignore it; a breaking change bumps `schema_version` to 2.0 and clients refuse it.
- *Why is `display_verdict` computed by the backend?* So the web app and the future extension always show the same thing (D4).
