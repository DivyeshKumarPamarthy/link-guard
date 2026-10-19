# Loop questions

Append-only. When a task stops with `needs_human` or `blocked`, `scripts/loop.py` adds a
section here with Claude's questions and proposed decisions. Write your answer after each
**A:** and move agreed decisions into `docs/decisions.md` yourself. See
`docs/loop/README.md`, "Answering questions".

## T1.5 · 2026-10-19 21:24 · branch task/T1.5

I added WHY docstrings to `detect_7z`, `detect_png` and `detect_jpeg`. The 135 detection tests and ruff pass. I did not make the reviewer's other two changes (a new decision row in `docs/decisions.md` and ticking T1.5 in `docs/phase1-tasks.md`): both files are on the loop's protected list and the loop bans edits to them, so a human has to make them.

- **Q:** Conflict: the reviewer asks for edits to docs/decisions.md and docs/phase1-tasks.md. Both files are on the protected list, and the loop instructions say never to edit them or tick a task box. Please make these two edits by hand when you merge, or tell the loop to allow them.
  **A:** 
- **Q:** Proposed decision (for the decisions.md row the reviewer asked for, linked to T1.5; D23 is the precedent): the detected_type names are pe-executable, dos-executable, elf-executable, macho-executable, java-class-or-macho, zip, docx, xlsx, jar, apk, 7z, rar4, rar5, pdf, ole, mp4, mp3, png, jpeg, text, unknown. This closes the open string left by D24. The row would also add three config variables: LG_ZIP_MAX_ENTRIES=10000, LG_TEXT_SAMPLE_BYTES=4096 and LG_TEXT_MIN_PRINTABLE_RATIO=0.95. Rationale: D24 left the type names to T1.5; spec §7 names the printable-ratio check and the entry cap but gives no numbers, and tunable numbers must come from config. The 4096 and 0.95 values are my choice, so please confirm or change them. Affects: spec §4, T2.2, T2.6.
  **A:** 
- **Q:** Once you have reviewed it, please tick T1.5 in docs/phase1-tasks.md. The verify command passes: 135 tests in test_detect_type.py.
  **A:** 
