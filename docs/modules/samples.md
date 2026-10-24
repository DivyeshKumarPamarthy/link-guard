# Module: Samples generator (M7, task T2.6)

Owner: Divyesh (track C, D16) · Reviewer: TBD · Phase: B · Last updated: 2026-10-24

## What it does (2–3 sentences, plain language)

`demo/make_samples.py` writes a small, harmless file for every format in spec §7 (a 1 KB
"hello" Windows program, a PDF, a PNG, a DOCX…) plus the disguised copies the demo needs
(`movie.mp4` that is really the program, `photo.jpg` that is really a PNG…). The demo server
serves them and the tests check that the detector recognises each one. Nothing is committed
and nothing is downloaded: every byte is built by the script.

## Inputs and outputs
- Input: nothing but the fixed seed `SEED` and fixed ZIP date in the script. Run with `make samples` (or `--out DIR`).
- Output: `samples/` (gitignored): 19 genuine files, `disguised/` with 5 disguises, and `SHA256SUMS` listing the hash of each.

| Genuine sample | Format (spec §7) | Disguise | Really is |
| --- | --- | --- | --- |
| `sample.exe` | PE (`MZ` + `PE\0\0`), only `xor eax,eax; ret` | `disguised/movie.mp4`, `disguised/invoice.pdf.exe` | `sample.exe` |
| `sample.elf`, `sample.dylib` | ELF (calls exit(0)); Mach-O header | `disguised/photo.jpg` | `sample.png` |
| `sample.zip`, `sample.7z`, `sample.rar`, `sample-v4.rar` | ZIP; empty 7z, RAR5, RAR4 | `disguised/report.docx` | `sample.zip` |
| `sample.pdf`, `sample.docx`, `sample.xlsx`, `sample.doc` | one-page PDF; Word; Excel; empty OLE container | `disguised/file.pdf` | an HTML "404 Not Found" page |
| `sample.js`, `sample.ps1`, `sample.bat` | text scripts that only print a greeting | | |
| `sample.mp4`, `sample.mp3`, `sample-frames.mp3` | `ftyp` + `mdat`; ID3 + 3 frames; 3 bare frames | | |
| `sample.png`, `sample.jpg` | 16×16 seeded-random PNG; 8×8 grey JPEG | | |

## How it works (5–10 lines; the steps you would draw on a whiteboard)

1. One small function per format builds its bytes with `struct.pack` (headers field by field), `zipfile` (stored, never compressed) or `zlib.crc32` (checksums).
2. "Random" content (PNG pixels, ZIP data, MP4 media bytes) comes from `random.Random(SEED)`, so it is the same on every run.
3. Anything that could depend on the machine is fixed: ZIP entry date and OS field, PE timestamp 0, PNG compression level 0, `\n` line endings written as bytes.
4. `disguised_samples()` reuses the genuine bytes under lying names; only `file.pdf` is new (an HTML error page).
5. `write_samples()` writes everything plus `SHA256SUMS`; the demo server's `/f`, `/disguised` and `/cd` serve from that folder.

## Why it is designed this way (the decision and the simpler/harder alternative you rejected)

- Generated, not committed (spec §11, plan M7): no binaries in git, antivirus can't break the repo, and the script documents exactly what each file contains.
- The "hello" PE is built from the format, not compiled: no compiler on the team's Macs, and a program whose only instruction is "return 0" is harmless even if someone runs it.
- Hash-stable on purpose: the test pins the hash of `SHA256SUMS`, so "same bytes on every machine" is checked, not hoped for.
- Rejected: downloading real installers and PDFs (licensing, needs the internet) and Pillow or other libraries for images (a new dependency for 30 lines of bytes).

## How it is tested (test files, acceptance rows it covers)

- `demo/tests/test_make_samples.py`: two runs give identical files; manifest matches the files; pinned manifest hash; every §7 format present; disguises reuse the real bytes; the PE header, PDF xref offsets, ZIP CRCs and RAR5 header CRCs are valid; every sample under 64 KB.
- `demo/tests/test_sample_endpoints.py`: `/disguised`, `/cd/{variant}` and `/index` serve the generated files.
- `backend/tests/unit/test_detect_samples.py`: `detect_type` over every generated file (type, family, confidence), a check that every generated file has an expected row, and the MZ highlight for `movie.mp4`. Skipped when `samples/` is missing; fails with "run make samples" when one file is missing.
- Feeds acceptance rows 1, 3–9 and 20–21 (T3.3).

## Known limitations

- The 7z, RAR and OLE samples are valid but empty archives; the Mach-O sample is a header only; the MP4 has no `moov` box, so players won't play it. They prove the detector, not that real tools open them (checked against the format specifications, not with 7-Zip, unrar or Office).
- Changing the generator on purpose means updating `EXPECTED_MANIFEST_SHA256` in the test.

## Likely viva questions (and your short answers)

- *Isn't generating an .exe dangerous?* Its only code is `xor eax, eax; ret`: it returns 0 and imports nothing. It is never run by LinkGuard, which only reads its first bytes.
- *How do you know the samples are the same on every laptop?* Fixed seed, fixed dates and no compression choices; a test compares the manifest's hash with a pinned value.
- *Why is `report.docx` only "SAFE with a note"?* It is a real ZIP; only its claimed subtype is wrong (spec §12 row 6).
- *Why is the HTML `file.pdf` detected as "text"?* The detector only knows signatures; recognising an HTML page is the router's job (D9, T3.1).
