# Module: File-type detection (M4, task T1.5)

Owner: Divyesh (track B, D16) · Reviewer: TBD · Phase: B · Last updated: 2026-10-19

## What it does (2–3 sentences, plain language)

Works out what a file really is from its first bytes, using the spec §7 signature table, and
works out what the file *claims* to be from its name (Content-Disposition header, then the
URL). The mismatch checks that compare the two and emit reason codes come next (T2.2).

## Inputs and outputs
- Input: the body head (`bytes`), the `Content-Disposition` header, the final and original URLs.
- Output: `detect_type(data) -> Detection(type, label, family, confidence, signature)`
  (`app/engine/detect/signatures.py`); `claimed_name(...) -> ClaimedName(display, compare, source)`
  and `extension_chain(name) -> ("pdf", "exe")` (`app/engine/detect/names.py`).

Types: `pe-executable`, `dos-executable`, `elf-executable`, `macho-executable`,
`java-class-or-macho`, `zip`, `docx`, `xlsx`, `jar`, `apk`, `7z`, `rar4`, `rar5`, `pdf`, `ole`,
`mp4`, `mp3`, `png`, `jpeg`, `text`, `unknown`.

## How it works (5–10 lines; the steps you would draw on a whiteboard)

1. Empty buffer, or a buffer that is only the start of a signature (`PK`, `Rar!`) → `unknown`.
2. One small function per format, tried riskiest family first (executables, then archives,
   documents, images, media, PDF, text). The first match wins, so `MZ…%PDF-` is an executable.
3. PE: `MZ` + `PE\0\0` at `e_lfanew` → certain; header beyond the buffer → probable PE;
   `PE\0\0` missing inside the buffer → probable `dos-executable`. `CAFEBABE` → "Java class or Mach-O", probable.
4. ZIP: walk the local-header names in the head (listing only, capped by `LG_ZIP_MAX_ENTRIES`).
   `[Content_Types].xml` + `word/` → DOCX, + `xl/` → XLSX; `AndroidManifest.xml` → APK;
   `META-INF/MANIFEST.MF` → JAR; nothing proven → "ZIP-based file (subtype unconfirmed)".
5. MP3: `ID3`, or a valid Layer III frame header; certain only when a second frame header sits
   exactly one frame length later.
6. Text: BOM (UTF-8/UTF-16) or no NUL bytes, then the printable share of the first
   `LG_TEXT_SAMPLE_BYTES` must reach `LG_TEXT_MIN_PRINTABLE_RATIO`. Always "probable".
7. Claimed name: `filename*` (RFC 5987, UTF-8/ISO-8859-1 only) → `filename` → final URL path →
   original URL path; take the last segment (`/` and `\`), strip trailing dots/spaces.
8. `signature` marks the matching bytes for the hex strip only when they lie in the first 16 bytes.

## Why it is designed this way (the decision and the simpler/harder alternative you rejected)

- Our own table, not libmagic: every rule is visible and testable, and the app works without libmagic.
- One function per format keeps each rule small and explainable; the list order encodes "riskiest wins".
- `filename*` is decoded once and not percent-decoded again, so `%2525` cannot become `%` by double decoding.
- MP3 means Layer III only; this also stops a UTF-16 BOM (`FF FE`) being read as audio.
- Rejected: walking ZIP entries by their sizes. Searching for each `PK\x03\x04` also works when
  sizes are deferred to a data descriptor, and the entry cap bounds the work.

## How it is tested (test files, acceptance rows it covers)

`backend/tests/unit/test_detect_type.py`: every spec §7 format from inline byte fixtures, labels
read correctly after "a" (D27), PE/ZIP/MP3/PDF/text edge cases from the plan's M4 table,
too-short buffers, 20 Content-Disposition variants (quotes, escapes, RFC 5987, bad charsets,
unterminated quotes), hostile names (`../`, `\`, NUL, U+202E, trailing dots), and the extension chain.
Generated samples are checked later by `test_detect_samples.py` (T2.6).

## Known limitations

- UTF-16 text without a BOM is reported as `unknown`.
- ZIP subtype is decided from the head only; the full-scope `zipfile` listing is T2.2.
- PE files are not split into `.exe`/`.dll` (Phase 3). Polyglot detection (`TYPE_POLYGLOT`) is T2.2.
- No reason codes are emitted here; T2.2 maps `probable` executables to `TYPE_EXEC_PROBABLE`
  and `unknown` to `TYPE_UNKNOWN`.

## Likely viva questions (and your short answers)

- *Why trust bytes over the filename?* Anyone can rename a file; the format's own header is much harder to fake without breaking the file.
- *Why is a bare `MZ` still an executable?* Risk evidence beats missing evidence; we say "probable", never "safe".
- *Why only look in the first 1024 bytes for `%PDF-`?* PDF readers accept the header there, so an attacker can put it there too.
- *Could a filename like `../../etc/passwd` write somewhere?* No: only the last segment is kept and it is never used as a path, only compared and shown escaped.
