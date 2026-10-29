# LinkGuard offline demo script (task T4.2)

Time budget: **8–10 minutes** · Runs **completely offline** (Wi-Fi off) on a single laptop.

## 1. One-command startup (before the panel enters, or live in < 1 minute)

```zsh
make demo
```

What `make demo` does:
1. Runs `demo/make_samples.py` to generate the 19 genuine samples and 5 disguised samples into `samples/` (deterministic, fixed seed, verified by `samples/SHA256SUMS`).
2. Starts `docker compose up --build` with all ports bound strictly to `127.0.0.1`:
   - Web UI: <http://127.0.0.1:5173>
   - Backend API: <http://127.0.0.1:8000> (`LG_PROFILE=demo`, `a.demo.test` / `b.demo.test` / `c.demo.test` mapped to the demo container)
   - Demo server: `127.0.0.1:8081` (HTTP), `127.0.0.1:8443` (HTTPS), `127.0.0.1:8444` (wrong-host cert HTTPS)

*(Alternative without Docker: run `make samples`, then in three terminals run `make demo-server`, `cd backend && LG_PROFILE=demo LG_STATIC_HOSTS="a.demo.test=127.0.0.1,b.demo.test=127.0.0.1,c.demo.test=127.0.0.1" LG_SSRF_EXEMPT="a.demo.test:8081,b.demo.test:8081,c.demo.test:8081,a.demo.test:8443,b.demo.test:8443,c.demo.test:8443,a.demo.test:8444" LG_ALLOWED_PORTS="80,443,8081,8443,8444" LG_EXTRA_CA_BUNDLE="../demo/certs/test-ca.pem" uv run python -m app`, and `cd web && npm run dev`.)*

Turn **Wi-Fi off** to show the panel that LinkGuard uses zero external APIs or CDNs.

---

## 2. Step-by-step live demo (7 scenarios)

Open <http://127.0.0.1:5173>.

### Step 1 — Clean file (`SAFE`)
- **Paste:** `http://a.demo.test:8081/f/sample.pdf`
- **Expected result:**
  - Verdict band: **Safe** (green shield with check) — *"No problems found in the whole file"*
  - **Claimed vs actual:** Claimed `sample.pdf` (`application/pdf`) · Actual `PDF document` (`Certain`)
  - **First bytes:** `[25 50 44 46 2d] 31 2e 34 ...` with `%PDF-` highlighted
  - **Details:** `Whole file checked (510 bytes)`, Confidence `High`, Score `0 / 100`
- **Talking point:** Plain "Safe" is shown *only* because the entire file arrived (`scope = full`) and the magic bytes match the claimed extension and `Content-Type`.

### Step 2 — Disguised Windows executable behind a shortened redirect chain (`UNSAFE`)
- **Paste:** `http://a.demo.test:8081/redirect/chain?n=2&to=/disguised/movie.mp4`
- **Expected result:**
  - Verdict band: **Unsafe** (red octagon with ×) — *"Blocked: file named .mp4 is actually a Windows executable"*
  - **Claimed vs actual:** Claimed `movie.mp4` (from `Content-Disposition`, `video/mp4`) · Actual `Windows executable` (`Certain`), hex strip highlights `4d 5a` (`MZ (Windows executable)`)
  - **Why:**
    - `High` — `TYPE_MISMATCH_EXEC` (weight 70, hard rule `UNSAFE`)
    - `Low` — `TYPE_CONTENT_TYPE_MISMATCH` (weight 10)
    - `Info` — `REDIR_CROSS_DOMAIN` (`c.demo.test`)
  - **Where the link went:** 3 hops (`a.demo.test` 302 → `b.demo.test` 302 → `c.demo.test` 200), URLs shown as non-clickable text with `Copy URL`.
- **Talking point:** Even though both the URL and the server's `Content-Type` claim `video/mp4`, the first bytes prove a 32-bit PE header (`MZ` + `PE\0\0`).

### Step 3 — Double extension (`SUSPICIOUS`)
- **Paste:** `http://a.demo.test:8081/disguised/invoice.pdf.exe`
- **Expected result:**
  - Verdict band: **Suspicious** (amber triangle with !) — *"Suspicious: the name hides a .exe file behind .pdf"*
  - **Why:** `EXT_DOUBLE` (weight 40 → `SUSPICIOUS`).
- **Talking point:** Windows Explorer hides known extensions by default, making `invoice.pdf.exe` look like `invoice.pdf`.

### Step 4 — Large 200 MB stream capped at 5 MB (`NO_ISSUES_IN_CHECKED_PART`)
- **Paste:** `http://a.demo.test:8081/big?range=yes`
- **Expected result:**
  - Verdict band: **No issues in the checked part** (teal half-shield) — *"No issues found in the checked part (First 5 MB of 200 MB)"*
  - **Why:** `SCAN_PARTIAL`
  - **Details:** `First 5 MB of 200 MB`, Confidence `Medium`, finishes in < 2 seconds without downloading the remaining 195 MB.
- **Talking point:** Honesty rule — LinkGuard only read the first 5 MB, so it never calls a partial scan plain "Safe".

### Step 5 — SSRF protection: direct private IP and redirect hop to `127.0.0.1` (`REJECTED`)
- **Paste 5a:** `http://169.254.169.254/latest/meta-data/`
  - **Expected result:** **Not scanned: blocked address** — *"LinkGuard won't contact this address because it points inside a private network."* (`URL_PRIVATE_ADDRESS`, zero connections made).
- **Paste 5b:** `http://a.demo.test:8081/redirect/internal`
  - **Expected result:** **Not scanned: blocked address** — *"A redirect at step 1 pointed inside a private network, so LinkGuard stopped there."* (`SSRF_BLOCKED_AT_HOP`), showing hop 1 (`a.demo.test` 302) and hop 2 (`http://127.0.0.1/` `no answer` · `blocked`).
- **Talking point:** Every redirect hop goes through the exact same DNS resolution and IP classification check as the initial URL, and connects to the pinned IP so DNS rebinding cannot swap in `127.0.0.1`.

### Step 6 — Missing evidence is never Safe (`UNABLE_TO_VERIFY`)
- **Paste 6a (Web page disguised as PDF):** `http://a.demo.test:8081/disguised/file.pdf`
  - **Expected result:** **Unable to verify** (`LINK_IS_WEB_PAGE`) — sniffed `<!DOCTYPE html>` in the first 1 KB despite `Content-Type: application/pdf`.
- **Paste 6b (Wrong TLS certificate):** `https://a.demo.test:8444/f/sample.png`
  - **Expected result:** **Unable to verify** (`FETCH_TLS_ERROR`) — pinned connection sends `sni_hostname=a.demo.test`, rejecting the certificate for `wrong-host.example`.

### Step 7 — Unsupported link types (`UNSUPPORTED`) & LocalStorage Recent Scans
- **Paste:** `magnet:?xt=urn:btih:0123456789abcdef`
  - **Expected result:** **Not supported yet** — *"Magnet links aren't supported yet; they are planned for a later phase."*
- Click **Check another link** to return to the Home screen and point out the **Recent scans** list stored locally in the browser (`localStorage`), with verdict badges and the **Clear** button.
