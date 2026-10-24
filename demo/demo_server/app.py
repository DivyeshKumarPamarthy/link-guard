"""Demo server endpoints (spec §11, task T1.1).

Each endpoint imitates one kind of server the fetcher must handle: a good file, a huge file,
a slow or broken connection, a compressed body, redirects, error statuses, a web page.
"""

import asyncio
import gzip
import html
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from urllib.parse import quote

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import (
    FileResponse,
    HTMLResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from starlette.routing import Route

from demo_server.config import DemoSettings
from demo_server.streams import TINY_PDF, RangeNotSatisfiable, big_chunks, parse_range

# Explicit types (not the mimetypes module) so every OS serves the same Content-Type.
CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".mp4": "video/mp4",
    ".m4a": "audio/mp4",
    ".mov": "video/quicktime",
    ".mp3": "audio/mpeg",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".zip": "application/zip",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".7z": "application/x-7z-compressed",
    ".rar": "application/vnd.rar",
    ".msi": "application/x-msi",
    ".doc": "application/msword",
    ".xls": "application/vnd.ms-excel",
    ".exe": "application/vnd.microsoft.portable-executable",
    ".js": "text/javascript",
    ".ps1": "text/plain",
    ".bat": "text/plain",
    ".txt": "text/plain",
    ".html": "text/html",
}
ERROR_STATUSES = {401, 403, 404, 410, 429, 500}

PAGE_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>LinkGuard demo page</title></head>
<body><h1>A web page, not a file</h1>
<p>LinkGuard should report this link as a web page (LINK_IS_WEB_PAGE).</p></body></html>
"""


class DeliberateReset(Exception):
    """Raised mid-body by /reset so the server drops the connection (an interrupted download)."""


def content_type_for(name: str) -> str:
    return CONTENT_TYPES.get(Path(name).suffix.lower(), "application/octet-stream")


def sample_path(samples_dir: Path, name: str) -> Path | None:
    """The sample file called `name`, or None. Names are plain file names, never paths."""
    if not name or name.startswith(".") or "/" in name or "\\" in name:
        return None
    path = samples_dir / name
    return path if path.is_file() else None


def missing_sample(name: str) -> PlainTextResponse:
    # Plan M7: a missing sample must say so clearly (e.g. antivirus removed it).
    return PlainTextResponse(
        f"Sample {name!r} not found in samples/. Run `make samples` to generate it.",
        status_code=404,
    )


# /cd/{variant}: a tricky Content-Disposition header and the sample served with it. The
# Content-Type is octet-stream ("no signal"), so the header's file name is the only claim.
# Non-ASCII and NUL can't go into an HTTP header raw, so those use RFC 5987 `filename*`.
CD_VARIANTS = {
    "filename-star": (
        "attachment; filename=\"fallback.pdf\"; filename*=UTF-8''r%C3%A9sum%C3%A9.pdf",
        "sample.pdf",
    ),
    "traversal": ('attachment; filename="../../etc/passwd.pdf"', "sample.pdf"),
    "quotes": ('attachment; filename="report \\"final\\".pdf"', "sample.pdf"),
    # U+202E (right-to-left override): "invoice<RLO>fdp.exe" displays as "invoiceexe.pdf".
    "rtl": ("attachment; filename*=UTF-8''invoice%E2%80%AEfdp.exe", "sample.exe"),
    "nul": ("attachment; filename*=UTF-8''report%00.pdf", "sample.pdf"),
}


def index_html(names: list[str]) -> str:
    """A directory-listing-style page, like the ones web servers generate for folders."""
    rows = "\n".join(f'<li><a href="/f/{quote(n)}">{html.escape(n)}</a></li>' for n in names)
    return (
        "<!doctype html>\n<html><head><title>Index of /f/</title></head>\n"
        f"<body><h1>Index of /f/</h1>\n<ul>\n{rows}\n</ul></body></html>\n"
    )


def create_app(settings: DemoSettings) -> Starlette:
    async def sample_file(request: Request) -> Response:
        """/f/{name}: a sample with its real Content-Type; Range and HEAD supported."""
        name = request.path_params["name"]
        path = sample_path(settings.samples_dir, name)
        if path is None:
            return missing_sample(name)
        return FileResponse(path, media_type=content_type_for(name))

    async def disguised(request: Request) -> Response:
        """/disguised/{name}: a sample whose name lies (movie.mp4 that is really a program).

        Content-Type and Content-Disposition both repeat the lie, as a malicious server would.
        """
        name = request.path_params["name"]
        path = sample_path(settings.samples_dir / "disguised", name)
        if path is None:
            return missing_sample(f"disguised/{name}")
        return FileResponse(
            path,
            media_type=content_type_for(name),
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

    async def content_disposition(request: Request) -> Response:
        """/cd/{variant}: a sample sent with one of the CD_VARIANTS file-name tricks."""
        variant = CD_VARIANTS.get(request.path_params["variant"])
        if variant is None:
            return PlainTextResponse(f"choose one of {sorted(CD_VARIANTS)}", status_code=404)
        header, sample = variant
        path = sample_path(settings.samples_dir, sample)
        if path is None:
            return missing_sample(sample)
        return FileResponse(
            path, media_type="application/octet-stream", headers={"Content-Disposition": header}
        )

    async def index(request: Request) -> Response:
        """/index: an HTML folder listing of the genuine samples (a page, not a file)."""
        names = sorted(p.name for p in settings.samples_dir.glob("*") if p.is_file())
        return HTMLResponse(index_html(names))

    async def big(request: Request) -> Response:
        """/big?range=yes|no: a 200 MB MP4-shaped stream generated on the fly.

        range=no imitates servers that ignore Range and always send the whole body.
        """
        total = settings.big_size_bytes
        honour_range = request.query_params.get("range", "yes") != "no"
        headers = {
            "Content-Type": "video/mp4",
            "Content-Disposition": 'attachment; filename="big-video.mp4"',
        }
        start, end = 0, total - 1
        status = 200
        if honour_range:
            headers["Accept-Ranges"] = "bytes"
            try:
                requested = parse_range(request.headers.get("range"), total)
            except RangeNotSatisfiable:
                return Response(status_code=416, headers={"Content-Range": f"bytes */{total}"})
            if requested is not None:
                start, end = requested
                status = 206
                headers["Content-Range"] = f"bytes {start}-{end}/{total}"
        headers["Content-Length"] = str(end - start + 1)
        if request.method == "HEAD":
            return Response(status_code=status, headers=headers)
        return StreamingResponse(big_chunks(start, end), status_code=status, headers=headers)

    async def slow(request: Request) -> Response:
        """/slow: headers at once, then one byte every slow_interval_s (a slow-drip server)."""

        async def drip() -> AsyncIterator[bytes]:
            body = TINY_PDF * (settings.slow_total_bytes // len(TINY_PDF) + 1)
            for byte in body[: settings.slow_total_bytes]:
                await asyncio.sleep(settings.slow_interval_s)
                yield bytes([byte])

        return StreamingResponse(
            drip(),
            headers={
                "Content-Type": "application/pdf",
                "Content-Length": str(settings.slow_total_bytes),
            },
        )

    async def reset(request: Request) -> Response:
        """/reset: promises a large body, sends reset_after_bytes, then drops the connection."""

        def broken_body() -> Iterator[bytes]:
            yield b"\0" * settings.reset_after_bytes
            raise DeliberateReset("demo /reset: dropping the connection on purpose")

        return StreamingResponse(
            broken_body(),
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Length": str(settings.reset_declared_bytes),
            },
        )

    async def chunked(request: Request) -> Response:
        """/chunked: a small PDF-shaped body sent in pieces with no Content-Length."""

        def pieces() -> Iterator[bytes]:
            for i in range(0, len(TINY_PDF), 16):
                yield TINY_PDF[i : i + 16]

        return StreamingResponse(pieces(), media_type="application/pdf")

    async def gzipped(request: Request) -> Response:
        """/gzip/{name}: a sample sent gzip-compressed even though clients ask for identity."""
        name = request.path_params["name"]
        path = sample_path(settings.samples_dir, name)
        if path is None:
            return missing_sample(name)
        body = gzip.compress(path.read_bytes(), mtime=0)  # mtime=0: same bytes every run
        return Response(
            body,
            headers={"Content-Type": content_type_for(name), "Content-Encoding": "gzip"},
        )

    async def redirect_chain(request: Request) -> Response:
        """/redirect/chain?n=2&to=/f/x.pdf: n redirects, each to the next demo hostname.

        a.demo.test -> b.demo.test -> c.demo.test (then back to a). The last redirect goes to
        the path `to` on the next host. `to` must be a path, so this is not an open redirect.
        """
        try:
            hops = int(request.query_params.get("n", "1"))
        except ValueError:
            return PlainTextResponse("n must be a number", status_code=400)
        target = request.query_params.get("to", "/f/sample.pdf")
        if not 1 <= hops <= settings.max_chain_hops:
            return PlainTextResponse(f"n must be 1 to {settings.max_chain_hops}", status_code=400)
        if not target.startswith("/") or target.startswith("//"):
            return PlainTextResponse("to must be a path such as /f/sample.pdf", status_code=400)

        hosts = settings.chain_hosts
        current = request.url.hostname or hosts[0]
        next_host = hosts[(hosts.index(current) + 1) % len(hosts)] if current in hosts else hosts[0]
        origin = f"{request.url.scheme}://{next_host}:{request.url.port}"
        if hops == 1:
            location = origin + target
        else:
            location = f"{origin}/redirect/chain?n={hops - 1}&to={quote(target, safe='/')}"
        return RedirectResponse(location, status_code=302)

    async def redirect_loop(request: Request) -> Response:
        """/redirect/loop -> /redirect/loop/b -> /redirect/loop ... (relative Locations)."""
        return RedirectResponse("/redirect/loop/b", status_code=302)

    async def redirect_loop_b(request: Request) -> Response:
        return RedirectResponse("/redirect/loop", status_code=302)

    async def redirect_internal(request: Request) -> Response:
        """/redirect/internal: a public-looking link that sends the client to localhost."""
        return RedirectResponse("http://127.0.0.1/", status_code=302)

    async def redirect_downgrade(request: Request) -> Response:
        """/redirect/https-to-http?to=/f/x: from the HTTPS listener to plain HTTP."""
        target = request.query_params.get("to", "/f/sample.pdf")
        if not target.startswith("/") or target.startswith("//"):
            return PlainTextResponse("to must be a path such as /f/sample.pdf", status_code=400)
        host = request.url.hostname or settings.chain_hosts[0]
        return RedirectResponse(f"http://{host}:{settings.http_port}{target}", status_code=302)

    async def status(request: Request) -> Response:
        """/status/{code}: an error status (401, 403, 404, 410, 429 with Retry-After, 500)."""
        code = request.path_params["code"]
        if code not in ERROR_STATUSES:
            return PlainTextResponse(f"choose one of {sorted(ERROR_STATUSES)}", status_code=400)
        headers = {"Retry-After": str(settings.retry_after_s)} if code == 429 else None
        return PlainTextResponse(f"demo status {code}", status_code=code, headers=headers)

    async def page(request: Request) -> Response:
        """/page: an ordinary HTML web page."""
        return HTMLResponse(PAGE_HTML)

    async def empty(request: Request) -> Response:
        """/empty: a 200 response with a 0-byte body."""
        return Response(
            b"",
            headers={
                "Content-Type": "application/pdf",
                "Content-Disposition": 'attachment; filename="empty.pdf"',
            },
        )

    get_and_head = ["GET", "HEAD"]
    return Starlette(
        routes=[
            Route("/f/{name}", sample_file, methods=get_and_head),
            Route("/disguised/{name}", disguised, methods=get_and_head),
            Route("/cd/{variant}", content_disposition, methods=get_and_head),
            Route("/index", index, methods=get_and_head),
            Route("/big", big, methods=get_and_head),
            Route("/slow", slow, methods=get_and_head),
            Route("/reset", reset, methods=get_and_head),
            Route("/chunked", chunked, methods=get_and_head),
            Route("/gzip/{name}", gzipped, methods=get_and_head),
            Route("/redirect/chain", redirect_chain, methods=get_and_head),
            Route("/redirect/loop", redirect_loop, methods=get_and_head),
            Route("/redirect/loop/b", redirect_loop_b, methods=get_and_head),
            Route("/redirect/internal", redirect_internal, methods=get_and_head),
            Route("/redirect/https-to-http", redirect_downgrade, methods=get_and_head),
            Route("/status/{code:int}", status, methods=get_and_head),
            Route("/page", page, methods=get_and_head),
            Route("/empty", empty, methods=get_and_head),
        ]
    )
