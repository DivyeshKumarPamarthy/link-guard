# Module: Reason-code registry (X2, task T0.5)

Owner: Divyesh (track B, D16) · Reviewer: TBD · Phase: A · Last updated: 2026-10-19

## What it does (2–3 sentences, plain language)

`backend/app/registry/reason_codes.yaml` lists every reason code with its group, weight,
severity, outcome, required evidence and the message and headline the user sees. The loader
validates the file at startup, so a typo or a negative weight stops the app instead of quietly
changing verdicts.

## Inputs and outputs
- Input: `reason_codes.yaml` (37 codes, `rules_version: "1.0.0"`).
- Output: `Registry` (rules version + `ReasonCodeSpec` per code) via `get_registry()`.

## How it works (5–10 lines; the steps you would draw on a whiteboard)

1. Parse YAML with a SafeLoader subclass that also refuses duplicate keys (plain YAML keeps the last one silently).
2. Check the top level: exactly `rules_version` (quoted `x.y.z`) and a non-empty `codes` map.
3. Each entry is validated by a Pydantic model that forbids unknown keys (catches typos like `wieght`).
4. Rules: UPPER_SNAKE name with an allowed Phase 1 prefix; known group; weight ≥ 0; only `risk` codes
   may have weight > 0, and every `risk` code must; only `risk` codes may set `hard_min_verdict`.
5. Templates: every `{placeholder}` must be a declared evidence key, and the template must render.
6. A test scans backend Python files for quoted codes (`"TYPE_…"`) and fails if any is not registered.

## Why it is designed this way (the decision and the simpler/harder alternative you rejected)

- Wording and weights in one reviewable file instead of scattered constants; the scorer has no magic numbers.
- "Unable" codes have weight 0 by rule, so missing evidence can never add to *or* hide risk (D26).
- Rejected: Python constants or an Enum; a YAML file is easier for the whole team to review and discuss.

## How it is tested (test files, acceptance rows it covers)

`backend/tests/unit/test_registry.py` (27): the real file matches the spec §8 table exactly
(group, weight, severity, outcome for all 37 codes); only `TYPE_MISMATCH_EXEC` has a hard rule;
the spec example message renders; 18 broken registries each fail with the right message;
duplicates refused; the code-usage scan and a self-test of its pattern.

## Known limitations

- Templates write "a {detected_label}", so detector labels must read correctly after "a" (D27).
- API error codes (`URL_EMPTY`, …) are not reason codes; the usage scan skips them via `ErrorCode`.

## Likely viva questions (and your short answers)

- *How do you know every code shown to the user has a message?* The usage-scan test fails if a code is missing from the registry.
- *Why weight 0 for "unable" codes?* They mean "we couldn't check", not "risky"; the outcome rules handle them (UNABLE_TO_VERIFY).
- *Why refuse duplicate keys?* YAML would silently keep the second entry and change a weight without anyone noticing.
