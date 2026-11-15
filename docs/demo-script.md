# LinkGuard demo script (task T4.2)

Status: **draft, not rehearsed.** The steps and the expected results were read from the API
during a live `make demo` run on 2026-11-15 (decision D85). The verdict words are the web app's
labels for those results. Nobody has yet walked through this in a browser in front of a clock,
and it has not been tried with Wi-Fi off: both belong to the rehearsal (T4.3). The
"What to say" lines are left empty on purpose: the team writes them.

## Before the panel arrives

1. Once, while online: `make setup`.
2. `make demo`, then open <http://127.0.0.1:5173>. Ctrl-C in the terminal stops everything.
3. Check that the home page shows the "Demo links" panel with nine rows. If it does not, the
   web app is not in demo mode (it was started some other way than `make demo`).
4. If `make demo` prints "port … is already in use", stop the program it names and run it again.
   Docker Desktop with another project's container on port 8000 is the usual cause.

`make demo` starts three programs on this computer only (127.0.0.1): the demo server (ports
8081, 8443, 8444), the API in the `demo` profile (port 8000) and the web app (port 5173). It
does not use Docker or the internet. `make dev` (Docker) cannot run this demo.

## Steps

Each step is one click on a row of the "Demo links" panel. After each result, press
"Check another link" to return to the home page.

### 1. A genuine PDF

- Link: `http://a.demo.test:8081/f/sample.pdf`
- Verdict: **Safe**. Headline: "No problems found in the whole file".
- Claimed vs actual: claimed `sample.pdf`, `application/pdf` (name from the address the link
  ended at); actual "PDF document", Certain. First bytes `25 50 44 46 2d …`, highlighted: `%PDF-`.
- Why: "No findings."
- Details: "Whole file checked (600 bytes)", confidence High, score 0 / 100.
- What to say:

### 2. A Windows program named movie.mp4, behind two redirects

- Link: `http://a.demo.test:8081/redirect/chain?n=2&to=/disguised/movie.mp4`
- Verdict: **Unsafe**. Headline: "Blocked: file named .mp4 is actually a Windows executable".
- Claimed vs actual: claimed `movie.mp4`, `video/mp4` (name from the server's download header);
  actual "Windows executable", Certain. First bytes `4d 5a …`, highlighted: "MZ (Windows
  executable)".
- Why, three rows:
  - High: "The file is named .mp4 but its content is a Windows executable." (`TYPE_MISMATCH_EXEC`)
  - Low: "The server says this is video/mp4, but its content is a Windows executable."
    (`TYPE_CONTENT_TYPE_MISMATCH`)
  - Info: "The link ended on a different site: c.demo.test." (`REDIR_CROSS_DOMAIN`)
- Where the link went, three hops: `a.demo.test` status 302, `b.demo.test` status 302,
  `c.demo.test/disguised/movie.mp4` status 206. Address: private on each (the demo server is
  on this computer).
- Details: "Whole file checked (1 KB)", confidence High, score 80 / 100, link type "Shortened
  link (redirects to another site)".
- What to say:

### 3. A double extension: invoice.pdf.exe

- Link: `http://a.demo.test:8081/disguised/invoice.pdf.exe`
- Verdict: **Suspicious**. Headline: "Suspicious: the name hides a .exe file behind .pdf".
- Claimed vs actual: claimed `invoice.pdf.exe`; actual "Windows executable", Certain. The file
  really is a program, so there is no type mismatch here: the name is the problem.
- Why: Medium: "The name ends in .pdf.exe: it looks like a .pdf file but is a .exe file."
  (`EXT_DOUBLE`)
- Details: score 40 / 100.
- What to say:

### 4. A 200 MB file, only the first 5 MB read

- Link: `http://a.demo.test:8081/big?range=yes`
- Verdict: **No issues in the checked part**. Headline: "No issues found in the checked part
  (First 5 MB of 200 MB)". The band also shows the bar: "Read: first 5 MB", "Not read: the other
  195 MB".
- Claimed vs actual: claimed `big-video.mp4`, `video/mp4`; actual "video file (MP4 family)",
  Certain. Highlighted: "ftyp (MP4 family)".
- Why: Info: "Only part of the file was checked (First 5 MB of 200 MB)." (`SCAN_PARTIAL`)
- Details: confidence Medium, score 0 / 100.
- What to say:

### 5. The cloud metadata address

- Link: `http://169.254.169.254/latest/meta-data/`
- Verdict: **Not scanned: blocked address**. Headline: "Not scanned: this address points inside
  a private network". Below it: "This protects your computer and local network. …"
- No "Claimed vs actual", no "Why" list and no hops: nothing was contacted.
- What to say:

### 6. A redirect into this computer

- Link: `http://a.demo.test:8081/redirect/internal`
- Verdict: **Not scanned: blocked address**. Headline: "Not scanned: the link redirects into a
  private network".
- Where the link went, two hops: `a.demo.test/redirect/internal` status 302; then
  `http://127.0.0.1/` status "no answer", address **blocked** (shown in bold).
- What to say:

### 7. A web page served as file.pdf

- Link: `http://a.demo.test:8081/disguised/file.pdf`
- Verdict: **Unable to verify**. Headline: "This link opens a web page, not a file".
- Why: Info: "This link opens a web page, not a downloadable file." (`LINK_IS_WEB_PAGE`)
- What you can try: "Open the page in your browser and copy the direct download link instead."
- Buttons: "Check again" and "Check another link".
- Details: "Whole file checked (191 bytes)", confidence Low.
- What to say:

### 8. A server with the wrong certificate

- Link: `https://a.demo.test:8444/f/sample.png`
- Verdict: **Unable to verify**. Headline: "The site's security certificate could not be
  verified".
- Why: Info: "The secure connection failed: the site's certificate could not be verified."
  (`FETCH_TLS_ERROR`)
- What you can try: "Be careful: the site could not prove who it is. Get the link from a source
  you trust."
- Where the link went: one hop, status "no answer".
- What to say:

### 9. A magnet link

- Link: `magnet:?xt=urn:btih:0123456789abcdef`
- Verdict: **Not supported yet**. Headline: "Magnet links aren't supported yet".
- What to say:

## After the nine links

- The home page now lists the nine checks under "Recent scans", each with its verdict word and
  a "Check again" button; "Clear" empties the list (it is kept in this browser only).
- The "Dark mode" / "Light mode" button at the top right works on every screen.

## Not yet checked (for the rehearsal, T4.3)

- The whole run with Wi-Fi off. `make demo` already stops uv from going online, but nobody has
  switched the network off and tried it.
- Timing: how long the nine steps take when spoken.
- The same run on a second laptop (T4.5).
