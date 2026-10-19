# Module: Configuration profiles (X4, task T0.2)

Owner: Divyesh (track C, D16) · Reviewer: TBD · Phase: A · Last updated: 2026-10-19

## What it does (2–3 sentences, plain language)

Reads every tunable number (caps, timeouts, ports, limits) from `LG_*` environment variables
into one frozen `Settings` object, so no number is hard-coded anywhere else. It also refuses to
start if a demo-only exemption is switched on in the `dev` or `prod` profile.

## Inputs and outputs
- Input: environment variables (`LG_PROFILE`, `LG_HEAD_FETCH_BYTES`, …; full list in `.env.example`).
- Output: `Settings` (pydantic-settings model) via `get_settings()`; WARNING log lines from `log_active_exemptions()`.

## How it works (5–10 lines; the steps you would draw on a whiteboard)

1. `Settings` lists each variable with its type and the default from spec §4 (plus D23 additions).
2. pydantic-settings reads `LG_<NAME>` for each field; types are checked (`"abc"` for a port fails).
3. Comma lists (`80,443`, `host=ip`, `host:port`) are parsed by small `field_validator`s.
4. After parsing, `_guard_profile` checks: if the profile is not `test`/`demo` and any of
   `LG_STATIC_HOSTS`, `LG_SSRF_EXEMPT`, `LG_EXTRA_CA_BUNDLE` is set → `ValidationError` → startup stops.
5. At startup, `log_active_exemptions()` prints one WARNING per active exemption.
6. `get_settings()` caches the object so the environment is read once per process.

## Why it is designed this way (the decision and the simpler/harder alternative you rejected)

- The demo server runs on `127.0.0.1`, which the SSRF rules must block. Rather than an
  "allow private addresses" switch (forbidden in CLAUDE.md), exemptions are exact `host:port`
  pairs that only exist in `test`/`demo` (D2). The guard makes it impossible to ship them by accident.
- Rejected: reading `os.environ` directly in each module. Defaults and validation would be scattered and untestable.
- `LG_BIND_HOST` is not forced to loopback here because docker needs `0.0.0.0` *inside* the container (D31, open).

## How it is tested (test files, acceptance rows it covers)

`backend/tests/unit/test_config.py` (29 cases): spec defaults, env overrides, bad ports and caps,
the guard for each demo variable in `dev` and `prod`, the full demo config refused in `prod`
(spec §11), malformed exemptions, warnings logged. `tests/conftest.py` clears `LG_*` variables
before every test so a developer's shell cannot change results.

## Known limitations

- No `.env` file is loaded automatically; variables must be in the environment (docker-compose will load `.env` in T2.5).
- The throughput grace period (5 s) and `Retry-After` value are not variables yet (D23).

## Likely viva questions (and your short answers)

- *Why not hard-code the 5 MB cap?* Tuning and tests need different values; CLAUDE.md requires all tunables in config.
- *What stops someone enabling the demo exemption in production?* The profile guard fails startup.
- *Why exact host:port and not "allow 127.0.0.1"?* A broad switch would let any link reach localhost services; an exact pair allows only the demo server.
