# Module: File-type detection and mismatch checks (M4, tasks T1.5 + T2.2)

Owner: Divyesh (track B, D16) · Reviewer: TBD · Phase: B · Last updated: 2026-10-24

## What it does (2–3 sentences, plain language)

Works out what a file really is from its first bytes, using the spec §7 signature table, and
works out what the file *claims* to be from its name (Content-Disposition header, then the
URL) and its Content-Type. The mismatch checks compare the two and emit reason codes such as
`TYPE_MISMATCH_EXEC` ("named .mp4, actually a Windows executable").

## Inputs and outputs
- Input: the body head (`bytes`), whether the whole file was read, the `Content-Disposition`
  and `Content-Type` headers, the final and original URLs.
- Output: `detect_type(data) -> Detection(type, label, family, confidence, signature)` and
  `refine_zip_subtype(detection, data, full_scope) -> Detection` (`signatures.py`);
  `claimed_name(...) -> ClaimedName(display, compare, source)` and
  `extension_chain(name) -> ("pdf", "exe")` (`names.py`);
  `run_mismatch_checks(detection, data, claim, content_type) -> list[Finding]` (`mismatch.py`).
  A `Finding` is the plain `(code, evidence)` dataclass the fetcher and scorer already use; the
  evidence keys are exactly the ones declared in `reason_codes.yaml` (D67).

Types: `pe-executable`, `dos-executable`, `elf-executable`, `macho-executable`,
`java-class-or-macho`, `zip`, `docx`, `xlsx`, `jar`, `apk`, `7z`, `rar4`, `rar5`, `pdf`, `ole`,
`mp4`, `mp3`, `png`, `jpeg`, `text`, `unknown`.

## How it works (5–10 lines; the steps you would draw on a whiteboard)

Detection (T1.5):
1. Empty buffer, or a buffer that is only the start of a signature (`PK`, `Rar!`) → `unknown`.
2. One small function per format, tried riskiest family first (executables, then archives,
   documents, images, media, PDF, text). The first match wins, so `MZ…%PDF-` is an executable.
3. PE: `MZ` + `PE\0\0` at `e_lfanew` → certain; header beyond the buffer → probable PE;
   `PE\0\0` missing inside the buffer → probable `dos-executable`. `CAFEBABE` → "Java class or Mach-O", probable.
4. ZIP: walk the local-header names in the head (listing only, capped by `LG_ZIP_MAX_ENTRIES`).
   `[Content_Types].xml` + `word/` → DOCX, + `xl/` → XLSX; `AndroidManifest.xml` → APK;
   `META-INF/MANIFEST.MF` → JAR; nothing proven → "ZIP-based file (subtype unconfirmed)".
5. Full-scope ZIPs only (T2.2, D75): `refine_zip_subtype` reads `zipfile.namelist()` from an
   in-memory buffer (never opens or extracts an entry, catches every exception, same entry
   cap). A proven subtype becomes certain; no subtype becomes a certain plain "ZIP archive".
6. MP3: `ID3`, or a valid Layer III frame header; certain only when a second frame header sits
   exactly one frame length later. Text: BOM or no NUL bytes, then a printable-share test.
7. Claimed name: `filename*` (RFC 5987) → `filename` → final URL path → original URL path.

Mismatch checks (T2.2, `mismatch.py`; each one a separate function returning findings):
8. Only the last extension counts (lowercased, whitespace stripped). It is looked up in small
   tables: executable classes (PE `exe dll sys scr cpl ocx com pif`, ELF `so elf`, Mach-O
   `dylib`, Java `class`), detectable formats with their equivalence classes
   (`{mp4 m4a m4v mov}`, `{jpg jpeg jpe}`, `{msi doc xls}`, `.zip` also allows DOCX/XLSX),
   text/script extensions, and common binary formats we cannot detect (`gif`, `iso`, …).
   Any other extension (`.php`, `.81`, none) is an unknown claim: no extension checks.
9. `check_exec_mismatch`: executable content (probable counts) + a known non-executable
   extension → `TYPE_MISMATCH_EXEC`. `check_text_mismatch`: text + a binary extension →
   `TYPE_MISMATCH_TEXT` (not for `text/html`, D9). `check_other_mismatch`: any other wrong
   format or wrong class member (PNG as .jpg, ELF as .exe, JAR as .zip) → `TYPE_MISMATCH_OTHER`,
   never on an unconfirmed detection.
10. Name checks: `check_double_extension` (risky last, document/media decoy before it:
    `invoice.pdf.exe`), `check_risky_extension` (`scr lnk hta vbs cmd jar com pif`),
    `check_spoofed_name` (any Unicode Cc/Cf character, e.g. U+202E, listed as `U+202E`).
11. `check_content_type`: the media type (parameters dropped) is in a table row that does not
    hold the detected type → `TYPE_CONTENT_TYPE_MISMATCH`. Missing, generic
    (`application/octet-stream`), `text/html`, unlisted types and unknown content → no signal.
    A ZIP with an unconfirmed subtype fits every ZIP-family type (DOCX, JAR, …); a ZIP proven
    plain by the full listing fits only the generic ZIP types.
12. `check_polyglot` (P1): image/media/PDF that also holds `PK\x03\x04`, or image/media with
    `%PDF-` in the first 1024 bytes → `TYPE_POLYGLOT` with the first offset. Info codes:
    `TYPE_EXEC_PROBABLE` (MZ-based probable only) and `TYPE_UNKNOWN` (non-empty, unidentified).

## Why it is designed this way (the decision and the simpler/harder alternative you rejected)

- Our own table, not libmagic: every rule is visible and testable, and the app works without libmagic.
- One function per format and per check keeps each rule small and explainable; the list order encodes "riskiest wins".
- `filename*` is decoded once and not percent-decoded again, so `%2525` cannot become `%` by double decoding.
- MP3 means Layer III only; this also stops a UTF-16 BOM (`FF FE`) being read as audio.
- Rejected: walking ZIP entries by their sizes. Searching for each `PK\x03\x04` also works when
  sizes are deferred to a data descriptor, and the entry cap bounds the work.
- Extension tables are allowlists (D68): an extension we do not know is "no signal", so
  `download.php` or `app-1.2.81` never raise false alarms; but any decoy we do know (even
  `.gif`, which we cannot detect) still catches a disguised program.
- A disguise gets one type code, not two: executable content is EXEC (never also OTHER), text
  is TEXT. The name codes (`EXT_*`) can add to it; the scorer only counts the highest weight
  per group (spec §9), so nothing is double-counted.
- Polyglot rules are narrow (D73): a ZIP storing a PDF uncompressed has `%PDF-` near the start,
  so ZIPs are never searched for it.

## How it is tested (test files, acceptance rows it covers)

`backend/tests/unit/test_detect_type.py`: every spec §7 format from inline byte fixtures, labels
read correctly after "a" (D27), PE/ZIP/MP3/PDF/text edge cases from the plan's M4 table,
too-short buffers, 20 Content-Disposition variants, hostile names, and the extension chain.

`backend/tests/unit/test_mismatch.py` (T2.2): clean files of every format (with matching names
and Content-Types) produce no mismatch codes; one or more positive and negative cases per check,
including the plan's M4 edge rows (marked "edge:"); the full-scope ZIP refinement (real DOCX,
plain ZIP, corrupt/truncated archive, over-cap listing, partial scope); and a check that every
code emitted is in the registry with exactly its declared evidence keys. Generated samples are
checked later by `test_detect_samples.py` (T2.6).

## Known limitations

- UTF-16 text without a BOM is reported as `unknown`.
- PE files are not split into `.exe`/`.dll` (Phase 3); a DLL named `.exe` is consistent.
- An unconfirmed ZIP (partial scope) never gets `TYPE_MISMATCH_OTHER`, even when named `.pdf`.
- Homoglyph names are not flagged; ZWJ/ZWNJ in genuine names can raise `EXT_SPOOFED_NAME` (D72).
- Extensions and media types outside the tables are "no signal" (see `docs/limitations.md`).
- The executor (T2.4) must call `refine_zip_subtype` after `detect_type`, then `run_mismatch_checks`.

## Likely viva questions (and your short answers)

- *Why trust bytes over the filename?* Anyone can rename a file; the format's own header is much harder to fake without breaking the file.
- *Why is a bare `MZ` still an executable?* Risk evidence beats missing evidence; we say "probable", never "safe".
- *Why only look in the first 1024 bytes for `%PDF-`?* PDF readers accept the header there, so an attacker can put it there too.
- *Could a filename like `../../etc/passwd` write somewhere?* No: only the last segment is kept and it is never used as a path, only compared and shown escaped.
- *Why is a `.docx` served as `application/zip` not a mismatch?* A DOCX is a ZIP; servers often send the generic ZIP type, so it is in the same equivalence class.
- *Does reading the ZIP listing unpack the archive?* No: `namelist()` only parses the central directory; no entry is opened or decompressed, and any error keeps the head result.
- *What does U+202E do?* It reverses the text after it, so `photo<U+202E>gpj.exe` displays as `photoexe.jpg`; we flag it.
- *Why does `setup.1.2.exe` not count as a double extension?* The part before `.exe` must be a known document/media type; `2` is not.
