# Module: Scorer v1 and explanations (M5, task T2.3)

Owner: Divyesh (D16) · Reviewer: team · Phase: B · Last updated: 2026-10-21

## What it does (2–3 sentences, plain language)

Turns the raw findings of a scan (reason codes + evidence) and the fetcher's facts about what
was read into the final, explained outcome: status, verdict, display verdict, score,
confidence, scope (with its label), headline and the sorted reasons. It is a pure function,
so the same input always gives the same answer and every verdict can be replayed from a file.

## Inputs and outputs
- Input: `findings` (list of `Finding(code, evidence)`), `ReadFacts` (bytes read, total size,
  Range confirmed, how the stream ended, headers-only), the `Registry`, `Thresholds` (config
  `LG_SUSPICIOUS_SCORE`=30, `LG_UNSAFE_SCORE`=60).
- Output: `ScoreOutcome` — the outcome fields of `ScanResult`, plus `unknown_codes`.
- Where the input comes from (T2.4, D66): `findings` = the fetcher's `findings` plus its
  `failure` (if any) plus the detector's findings; `ReadFacts` is copied from `FetchResult`
  (`bytes_read`, `total_size`, `range_supported`, `ended`, and `headers_only` = `metadata_only`,
  set by the fetcher's web-page stop, D53).
- Code: `backend/app/engine/scoring/scorer.py`, `backend/app/engine/scoring/scope.py`.

## How it works (5–10 lines; the steps you would draw on a whiteboard)

1. Look up every code in the registry (unknown code → weight 0, counted as "unable").
2. Build a `Reason` per finding (message rendered from the registry template) and sort them:
   weight desc, severity desc, code asc.
3. Status: any `rejected` code → rejected; else any `unsupported` → unsupported; else completed.
4. Score = sum over groups of the highest weight in that group, capped at 100.
5. Verdict = the stronger of the score verdict (≥ 60 UNSAFE, ≥ 30 SUSPICIOUS) and any hard
   rule; if that is still SAFE but an `unable` code is present → UNABLE_TO_VERIFY.
6. Scope from `ReadFacts`: full / partial / metadata-only / none. Full only when the stream
   ended on its own AND `total_size` is known and equals `bytes_read` (D54: a body read until
   the connection closed is partial); `FETCH_UNEXPECTED_ENCODING` forces partial. Confidence: high = full; medium = partial + confirmed Range + known size;
   low = everything else and every UNABLE_TO_VERIFY.
7. Display verdict: SAFE only for verdict SAFE + full scope + confidence ≥ medium; otherwise
   SAFE becomes NO_ISSUES_IN_CHECKED_PART.
8. Headline: NO_ISSUES → "No issues found in the checked part ({label})"; otherwise the top
   reason's registry headline, taken only from the codes that decided a rejected, unsupported
   or unable result (D49, D63); no reasons → "No problems found in the whole file".
   Scope labels (D64) are shown unchanged, e.g. "(First 5 MB of 200 MB)"; examples are in
   `docs/ui-style-guide.md`.

## Why it is designed this way (the decision and the simpler/harder alternative you rejected)

- Max per group (not a plain sum): one fact seen three ways (name, extension, content) must not
  count three times. A plain sum was rejected for that reason.
- Risk beats missing evidence, missing evidence never becomes SAFE (honesty rules).
- No logging inside `score_scan` (pure function); `log_unknown_codes()` is called by the
  orchestrator (T2.4) to write the ERROR log spec §9 asks for.
- Unknown codes count as "unable", so a typo in a detector can never produce a SAFE verdict.

## How it is tested (test files, acceptance rows it covers)

- `backend/tests/golden/` (17 cases, `<case>.input.json` → hand-written `<case>.expected.json`):
  thresholds 29/30/59/60 (29 and 59 use a per-case `weight_overrides`, since no real weight
  combination reaches them), hard rule, grouping, risk vs unable, partial never SAFE,
  encoding, web page (headers-only and full body), loop, rejected at hop, unsupported.
  Covers the scoring side of acceptance rows 2, 3, 4, 5, 7, 10, 11, 13, 14, 17, 18, 20.
- `backend/tests/unit/test_scorer.py`: thresholds from a test registry and from config,
  cap at 100, ordering, confidence table, unknown code, missing evidence, purity, and every
  registry code × four read shapes accepted by the `ScanResult` validator (D29), and D54:
  a body read until close is partial, a cleanly ended chunked body is full.
- `backend/tests/unit/test_config.py`: the threshold defaults equal spec §9 (30/60), startup
  refuses suspicious ≥ unsafe, and the active thresholds are logged at startup (D62).

## Known limitations

- Weights and thresholds are starter hypotheses (tuned in Phase F only).
- Thresholds live in config, not the registry, so the same `rules_version` could give
  different verdicts if someone changes `LG_*_SCORE`. Mitigations (D62): the values are
  logged at every startup, and a test fails if the defaults differ from spec §9.
- A missing evidence key renders as "unknown" instead of failing the scan.

## Likely viva questions (and your short answers)

- *Why can a partial scan never show "Safe"?* We did not read the whole file; the rest could
  hide anything. The display verdict says "No issues in the checked part" and the label says
  how much was read.
- *What if the fetch timed out but the name was `invoice.pdf.exe`?* Risk beats missing
  evidence: SUSPICIOUS (score 40), confidence low.
- *Why is the scorer pure?* Reproducible verdicts, golden tests, and Phase 2 can move fetching
  into a container without touching it.
- *What happens with a code missing from the registry?* Weight 0, treated as "unable", logged
  at ERROR by the orchestrator, and a test fails on it.
