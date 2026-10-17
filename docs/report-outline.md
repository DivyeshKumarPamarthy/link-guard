# Report outline and viva question bank

Fill this as the project progresses: each finished module adds its notes from `docs/modules/`.
Adjust chapter names to your college's report template.

## Chapters

1. **Introduction**: problem (disguised downloads, shortened links hide malware), objectives, scope (Must / Should from `roadmap.md`), what is out of scope and why.
2. **Literature survey / existing systems**: VirusTotal (judges known files, needs upload or hash), Chrome Safe Browsing (reputation of URLs/files), URL expanders (show destination, no file check). Table: feature × system, ending with the gap LinkGuard fills (structure-based, explained, before download).
3. **Requirements**: functional (paste link, verdict with reasons, redirect chain, extension pause/allow/block); non-functional (never executes files, offline demo, honest verdicts, response time on local demo).
4. **System design**: architecture diagram, data flow of one scan, API contract, verdict rules (Safe / Suspicious / Unsafe / Unable to verify, partial scans), threat model (`threat-model.md`), UI design (wireframes, style guide).
5. **Implementation**: one section per module from `docs/modules/` (router, safe fetcher, detector, verdict engine, API, web app, extension, then D/E modules if built).
6. **Testing and results**: test strategy, SSRF test table, acceptance matrix output, results table (caught / missed / false alarms / median scan time), screenshots.
7. **Limitations and future work**: partial reads, cloaking, no behavioural analysis, format list; ideas from `roadmap.md`.
8. **Conclusion**.
- References; Appendix: API docs (FastAPI `/docs` screenshots), user guide, setup guide.

State the use of AI coding tools as your college policy requires (decision D21).

## Draft notes for chapters 1–2 (T0.11)

*Draft notes by Claude Code (2026-10-17), not report text. The team rewrites these in its own
words. Every claim about another system is marked **[VERIFY + cite]** and needs a source from
the official documentation or a paper before it goes in the report.*

### Chapter 1: Introduction

**Problem statement (one paragraph to write).** People download files from links they find in
chats, forums and emails. Two tricks make this risky: (1) the file is not what its name says
(a Windows program named `movie.mp4`, or `invoice.pdf.exe`), and (2) shortened or redirecting
links hide where the download really comes from. Checking a file usually means downloading it
first, and existing tools mostly answer "is this file or site already known to be bad?". They
say little about *why*, and little about files nobody has reported yet.

**Objectives (Phases A–B, this semester).**
1. Check a public download link *before* the user downloads it, by reading only the response
   headers and the first bytes (at most 5 MB).
2. Identify the file's real type from its signature (magic bytes) and flag mismatches with the
   claimed name, extension and Content-Type.
3. Follow redirect chains safely and show every hop.
4. Never let the checker itself be abused to reach internal network addresses (SSRF).
5. Give an honest, explained verdict (Safe / Suspicious / Unsafe / Unable to verify) with
   reasons and a statement of how much of the file was read.
6. A polished web app that runs fully offline for the demo.

**Scope.** Must: Phases A, B, C, F; Should: D, E (from `roadmap.md`). Out of scope this
semester: the Chrome extension, torrent/ZIP inspection, reputation lookups, containers.
Out of scope entirely: running files, malware signatures, YARA, user accounts. Say *why* for
each (time, safety, focus on the explainable core).

### Chapter 2: Existing systems (literature survey outline)

| Feature | VirusTotal | Google Safe Browsing / Chrome download protection | URL expanders (e.g. unshorten-style sites) | LinkGuard |
| --- | --- | --- | --- | --- |
| Main question answered | Do known engines flag this file or URL? [VERIFY + cite] | Is this URL/file on a known-bad list or of bad reputation? [VERIFY + cite] | Where does this short link lead? | Is this file what it claims to be, and is the link safe to fetch? |
| Needs the file first | For file scans, an upload or a hash lookup [VERIFY + cite] | Works in the browser during/after download [VERIFY + cite] | No | No: reads headers and first bytes only |
| New, never-reported files | Depends on engine detections [VERIFY + cite] | Reputation may be unknown [VERIFY + cite] | Not checked | Structural check works without prior reports |
| Explains why | Engine names and labels [VERIFY + cite] | Short warning [VERIFY + cite] | Shows destination only | Reason list, claimed-vs-actual bytes, redirect chain |
| Privacy | Uploaded files may be shared with security partners [VERIFY + cite: check VirusTotal terms] | Hash-prefix lookups designed for privacy [VERIFY + cite] | URL sent to the service | Runs locally; nothing leaves the laptop in Phases A–B |
| Checks the file type | Yes, as part of analysis [VERIFY + cite] | Not described publicly in detail [VERIFY] | No | Yes, core feature |

**The gap LinkGuard fills (closing paragraph).** A local, explainable, *structure-based* check that
works before download and without relying on someone having reported the file, plus honest
reporting of what could not be checked. LinkGuard complements reputation services; it does not
replace them (Phase E adds a reputation lookup as one more signal).

**Sources to find (team task).** VirusTotal documentation and terms of service; Google Safe
Browsing API documentation and the Chrome download-protection description; one or two papers on
file-type identification by magic bytes; OWASP SSRF Prevention Cheat Sheet; one survey on
URL shorteners and malicious redirects.

## Viva question bank (prepare a 2–3 sentence answer each; add new ones after every rehearsal)

| Question | Key points |
| --- | --- |
| Why not just use VirusTotal? | It judges known files; LinkGuard catches disguised/new files from structure, explains why, works before download |
| What is SSRF and how do you prevent it? | Tricking a server into requesting internal addresses; every resolved IP on every redirect hop is checked, connection pinned to the checked IP, localhost-only backend |
| Do you run or open the file? | Never; only the first bytes are read and compared with signatures |
| What are magic bytes? Give examples | Fixed bytes at the start of a format: MZ (Windows exe), %PDF-, PNG's 89 50 4E 47 |
| What if the malware is after the first 5 MB? | Scope is reported; partial scans never shown as "Safe"; documented limitation |
| How is the score computed? Why those weights? | Highest weight per group, summed, capped at 100; thresholds 30/60; starter weights checked on the test set; hard rule for executables disguised as media |
| Why "Unable to verify" instead of Safe on errors? | Missing evidence is not evidence of safety |
| How does the extension stop a download? | MV3 can't block synchronously; it pauses on creation, checks, then resumes or cancels; small files may finish first, handled honestly |
| Why no login or database of users? | Single-user local tool, no personal data, nothing reachable from outside the laptop |
| Why SQLite, why FastAPI, why React? | Zero-setup, Python parsing tools + auto API docs, standard UI stack with typed client |
| What are the limitations? | Partial reads, cloaking servers, no behavioural analysis, limited formats |
| How did you test it without real malware? | Generated harmless samples and disguised copies, local demo server imitating good/bad/broken servers |
| What did each team member build? | Each owner explains their module from their note |
| How do you stop the scanner being used to attack your own network? | SSRF checks on resolved IPs at every hop; demo exemptions only exact host:port in test/demo profiles, refused at startup otherwise |
| What stops a wrong "Safe"? | Contract validator refuses plain SAFE for partial or low-confidence scans; crashes become Unable to verify (ANALYSIS_ERROR) |
| How do backend and web app agree on the data format? | Pydantic models → OpenAPI → generated TypeScript types; CI fails if they drift |
| Is the UI accessible? | Word + icon for every verdict; contrast computed from the real CSS in tests (WCAG AA); keyboard focus ring |
| What is a "Trojan Source" attack and could it affect your code? | Hidden bidi characters make code read differently from how it runs; a test fails if any source file contains one |
| How would you extend it? | More analyzers behind the same findings interface; run scans in separate containers |
