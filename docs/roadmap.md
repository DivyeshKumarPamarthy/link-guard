# LinkGuard roadmap (phases A–F)

Source: mentor review (decision D20). Phases A, B, C and F are **Must Have** and on their own make a
complete project. D and E are **Should Have**. Nothing new starts after the feature freeze at the
end of Phase E. Semester lengths are assumptions to confirm.

Labels: **Must** = required for a complete project. **Should** = planned; dropped only by team
decision, recorded as future work. **Nice** = only after every Must and Should in that phase is done.

| Phase | When (assumed) | Status |
| --- | --- | --- |
| A Foundations | Semester 1, week 1 | Current |
| B Core scanner + web app | Semester 1, weeks 2–10 | Current |
| C Chrome extension + UI polish | Semester 2, weeks 1–4 | Not started |
| D Torrent + ZIP inspection | Semester 2, weeks 5–7 | Not started |
| E Known-threat lookup + hardened container | Semester 2, weeks 8–10, then feature freeze | Not started |
| F Results, report, demo | Semester 2, weeks 11–14 | Not started |

## A — Foundations (Must)
- Must: problem statement, literature survey outline, API contract, reason-code registry, wireframes, repo + CI, owners.
- Should: style guide tokens in Tailwind (`docs/ui-style-guide.md`).
- Done when: stack starts from README in < 15 min; mock result renders in the web skeleton; wireframes agreed.

## B — Core scanner + web app (Must) — detailed in `phase1-spec.md` and `phase1-tasks.md`
- Must: safe fetcher, link router, file-type detector, verdict engine, web app (all screens), demo server, samples, 22-row acceptance matrix in CI.
- Should: homograph warning, cloud-share hint, recent scans in localStorage.
- Nice: polyglot detection.
- Done when: 22 rows green; SSRF table rejected with zero connections; partial/failed scans never shown as plain Safe; demo runs with Wi-Fi off.

## C — Chrome extension + UI polish (Must)
- Must: MV3 extension — pause download → `POST /api/scans` → poll → resume (Safe), ask (Suspicious / Unable to verify / No issues in checked part), cancel + remove (Unsafe); popup with headline reason; options (on/off, backend URL `http://127.0.0.1:8000`); state in `chrome.storage`; web polish pass against the style guide.
- Should: warning page when blocked; skip local/intranet URLs; handle "finished before verdict" honestly.
- Nice: extension-side history in browser storage.
- Done when: disguised .exe blocked with reason; clean file resumes without clicks; restarting the extension mid-scan loses nothing; web and extension share verdict words and colours.

## D — Torrent + ZIP inspection (Should)
- Should: `.torrent` parsing with a small hardened bencode parser (no libtorrent): file list, executable in a media torrent, double extensions, archive-only "movie", path traversal names; ZIP listing without extraction (exe inside, encrypted, nested, bomb-like ratio); tail-range read when the server supports it.
- Nice: basic PE check (packed section names, high entropy).
- Done when: fake-movie torrent names the hidden .exe; clean Linux ISO torrent not flagged; zip-with-exe flagged; malformed input never crashes.

## E — Known-threat lookup + hardened container (Should)
- Should: one URL lookup + one hash lookup from free services (verify terms/quotas first), 5 s timeout, "signal unavailable" on failure, off switch, cached responses for demo day; backend container non-root, read-only filesystem, memory/CPU limits, `no-new-privileges`, ports on 127.0.0.1.
- Nice: one extra analyzer (PDF active content, Office macros or PE).
- Done when: with lookups off, all earlier acceptance rows pass; listed URL blocked before any fetch; container verified non-root + read-only.

## F — Results, report, demo (Must)
- Must: results table on the team's sample set (caught / missed / false alarms / median scan time); limitations; final report + PPT; demo script; two rehearsals (one offline); backup video; viva question bank. No new features.
- Done when: any teammate can explain any module; demo < 10 min from one command; report numbers come from the test run.

## Dropped (do not build)
Magnet links via the torrent network, YARA rules, 7z/RAR, blob: uploads, per-scan sandbox
containers, scan history server-side, caching, accounts, rate limiting beyond the busy guard.

## Ideas / future work
(Add ideas here instead of building them.)
