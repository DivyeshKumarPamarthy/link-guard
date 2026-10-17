# Module: Logging and safe() (X3, task T0.3)

Owner: TBD (track A, D16 open) · Reviewer: TBD · Phase: A · Last updated: 2026-10-17

## What it does (2–3 sentences, plain language)

Sets up plain-text logging to the terminal and provides `safe(value)`, which every log call must
use for remote data (URLs, filenames, headers, exception text). `safe()` removes characters that
could fake log lines or hide text, and replaces secrets in URLs with `REDACTED`.

## Inputs and outputs
- Input: any value (usually a string from a remote server).
- Output: a string safe to log. `setup_logging(level)` installs one handler on the root logger.

## How it works (5–10 lines; the steps you would draw on a whiteboard)

1. Remove ANSI escape sequences (colour codes, cursor moves, OSC terminal hyperlinks).
2. Remove control characters (Unicode category Cc: NUL, newline, tab, ESC, C1) so a filename cannot start a fake log line.
3. Remove invisible characters (zero-width, bidi overrides such as U+202E, isolates, BOM, line separators).
4. If the result looks like a URL (has a scheme and a host, or is a `magnet:` link): keep each
   query key, replace each value with `REDACTED`, and replace a userinfo password.
5. `setup_logging()` removes its own previous handler first, so calling it twice does not duplicate lines.

## Why it is designed this way (the decision and the simpler/harder alternative you rejected)

- Strip, don't escape: spec T0.3 says strip; logs are for developers, and the web UI shows the escaped form instead.
- Redact values but keep keys: `?X-Amz-Signature=REDACTED` still tells a developer it was a signed URL.
- Rejected: JSON/structured logging (cut by D17).
- Errors are logged as `type + safe(message)`, not tracebacks, because httpx error messages contain the URL (D30).

## How it is tested (test files, acceptance rows it covers)

`backend/tests/unit/test_safe_logging.py` (30 cases): signed S3 URL, token, bare value, `;`
separators, fragment, userinfo password, magnet trackers, ANSI CSI and OSC sequences, newline
forgery, RTL override, every zero-width/bidi character, NUL and C1, Unicode letters kept, and the
handler not duplicating.

## Known limitations

- uvicorn and Starlette log their own tracebacks on crashes; those bypass `safe()` (T3.5).
- Only query values and passwords are redacted; a secret in a URL *path* (`/share/<token>/file`) is not.

## Likely viva questions (and your short answers)

- *What is log injection?* Writing newlines or terminal escapes into logged data to fake entries or hide text; we strip them.
- *Why redact query values?* Signed download links carry credentials in the query string.
- *Why would a filename contain U+202E?* The right-to-left override makes `invoice[U+202E]fdp.exe` display as `invoiceexe.pdf`.
