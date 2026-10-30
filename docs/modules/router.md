# Module: Link router (M3, task T3.1)

Owner: Divyesh (track A, D16) · Reviewer: team · Phase: B · Last updated: 2026-10-29

## What it does (2–3 sentences, plain language)

Cleans the text the user pasted, decides whether the link is an HTTP(S) download, an
unsupported link type (`magnet:`, `ftp:`, `.torrent`, `intent:`), or a blocked scheme
(`file:`, `data:`, `javascript:`, `gopher:`), and checks post-fetch link signals: HTML web
pages (by header or body sniff), cloud-sharing preview pages, and look-alike IDN domains.

## Inputs and outputs
- Input: raw URL string from the user (`clean_url`, `classify`), and `FetchResult` (`is_html_body`, `cloud_share_service`, `is_homograph_host`, `redirect_chain_view`).
- Output: normalized URL string, pure `Classification(action, link_type, finding)`, post-fetch `Finding`s (`LINK_IS_WEB_PAGE`, `LINK_CLOUD_SHARE_PAGE`, `URL_HOMOGRAPH`), and `ScanResult.redirects`.
- Code: `backend/app/engine/router/router.py`.

## How it works (5–10 lines; the steps you would draw on a whiteboard)

1. `clean_url(raw)` strips whitespace, surrounding quotes (`"..."`, `'...'`, curly quotes), `<...>`, or outer parentheses, and strips trailing sentence punctuation (`.`, `,`, `;`, `!`, or unbalanced `)` / `]`).
2. Backslashes in the authority and path (before `?` and `#`) are normalized to `/`; `https://` is added when the scheme is missing (including `host:port/path` and `//host/path`); scheme and ASCII host are lowercased while path and query case are preserved.
3. `classify(url)` (pure function) reuses `unsupported_link_kind(url)` (D50) for `magnet:`, `ftp:`, `intent:` and `.torrent` paths (`LINK_TYPE_UNSUPPORTED`), rejects non-web schemes (`URL_SCHEME_UNSUPPORTED`) and hostless/malformed URLs (`URL_INVALID`), and sends valid `http(s)` links to the fetcher.
4. After fetching, `is_html_body(body_head)` sniffs the first 1 KB (after UTF-8/UTF-16 BOM, whitespace, and HTML/XML comments) for `<!doctype html` or `<html`. If matched and `LINK_IS_WEB_PAGE` was not already added by `is_web_page_headers()`, it adds `LINK_IS_WEB_PAGE` once and skips file mismatch checks (D9, D53).
5. When `LINK_IS_WEB_PAGE` is present and the final host belongs to Google Drive, Dropbox, OneDrive or Mega, `cloud_share_service()` adds `LINK_CLOUD_SHARE_PAGE`.
6. `is_homograph_host()` checks whether an IDN host mixes alphabetic scripts (e.g. Cyrillic `а` + Latin `pple` in `аpple.com`) or uses Cyrillic/Greek confusable characters, emitting `URL_HOMOGRAPH` while leaving single-script Latin IDNs (`bücher.example`) unflagged.
7. `redirect_chain_view()` returns an empty list when hop 0 is rejected before any contact, and returns the full hop list when a redirect hop is blocked (`SSRF_BLOCKED_AT_HOP`) or contacted.

## Why it is designed this way (the decision and the simpler/harder alternative you rejected)

- **No hardcoded list of URL shorteners (spec §6, D8):** any chain that redirects to a different hostname sets `link_type = shortened` and emits `REDIR_CROSS_DOMAIN`. A static list of shortener domains goes stale and misses custom short domains.
- **Shared `unsupported_link_kind()` and `is_web_page_headers()` with the fetcher (D50, D53):** a pasted `.torrent` link and a short link redirecting to `.torrent` get the exact same answer, and `LINK_IS_WEB_PAGE` is never emitted twice.
- **Stop before file mismatch checks on HTML pages (D9):** an HTML error page served as `file.pdf` with `Content-Type: application/pdf` (acceptance row 7) is a web page (`UNABLE_TO_VERIFY`), not a text-file disguise (`TYPE_MISMATCH_TEXT`).

## How it is tested (test files, acceptance rows it covers)

- `backend/tests/unit/test_router.py`: table-driven tests covering all 17 M3 edge cases from the implementation plan — input cleaning (quotes, `<...>`, trailing punctuation, balanced parens, missing scheme, uppercase scheme/host, backslashes), empty/multiple/too-long rejections, `classify()` across all supported/unsupported/rejected schemes, HTML header and body sniff (UTF-8/UTF-16 BOM, comments, 1 KB boundary), cloud-share hosts, homograph mixed-script vs clean Latin IDN, redirect-chain view model, and full orchestrator integration for row 7 + cloud share.
- Covers acceptance rows 7, 8, 9, 17, 18a/b/c.

## Known limitations

- Cloud-share pages are never scraped or followed (by design, spec §6): LinkGuard explains that the link is a sharing page and advises using the direct download link.
- Whole-script non-Latin domains that do not use ASCII look-alike characters are not flagged as homographs; both Unicode and punycode forms are always shown in the UI (`Details`).

## Likely viva questions (and your short answers)

- *How does LinkGuard know a link is a shortened URL without a list like `bit.ly`?* By following redirects and comparing normalized ASCII (punycode) hostnames across contacted hops: if any hop changes host, `link_type` is `shortened`.
- *Why sniff the first 1 KB for `<!doctype html` or `<html` when you already check `Content-Type`?* Broken servers and file hosts often serve an HTML error or login page with `Content-Type: application/pdf` or `application/octet-stream` (row 7).
- *Why isn't `bücher.example` flagged as `URL_HOMOGRAPH` while `аpple.com` is?* All letters in `bücher` belong to the Latin script; `аpple.com` mixes Cyrillic `а` (`U+0430`) with Latin `pple`, which is how look-alike phishing domains are built.
