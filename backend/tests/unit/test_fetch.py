"""The streaming fetch against the real demo server (task T2.1, D44, D52–D60).

One test per demo endpoint, plus the HTTPS listeners. Acceptance rows in brackets.
"""

import gzip
import time
import tracemalloc

import pytest

from app.engine.fetcher.fetch import FetchResult, fetch
from app.engine.fetcher.redirects import Finding
from tests.demo_server import Demo, RecordingResolver, free_port

pytestmark = [
    pytest.mark.integration,
    pytest.mark.allow_hosts(["127.0.0.1"]),
    pytest.mark.asyncio,
]

SAMPLE = b"%PDF-1.4\n" + bytes(range(256)) * 16 + b"\n%%EOF\n"  # 4 KB, PDF-shaped
CAP = 5_242_880


@pytest.fixture(autouse=True)
def samples(demo: Demo) -> None:
    (demo.samples_dir / "small.pdf").write_bytes(SAMPLE)


async def run(demo: Demo, path: str, *, https: bool = False, **settings: object) -> FetchResult:
    port = demo.https_port if https else demo.http_port
    scheme = "https" if https else "http"
    config = demo.settings().model_copy(update=settings)  # e.g. a shorter deadline
    return await fetch(f"{scheme}://a.demo.test:{port}{path}", config, RecordingResolver(config))


# --- a whole small file ---------------------------------------------------------------------


async def test_small_file_is_read_whole(demo: Demo) -> None:
    """[1] Range honoured on a small file: everything read, full scope."""
    result = await run(demo, "/f/small.pdf")
    assert result.failure is None
    assert result.body_head == SAMPLE
    assert (result.ended, result.bytes_read, result.total_size) == (
        "complete",
        len(SAMPLE),
        len(SAMPLE),
    )
    assert result.range_supported is True
    assert result.whole_file is True
    assert result.status_code == 206
    assert result.headers["content-type"] == "application/pdf"
    assert result.final_url == f"http://a.demo.test:{demo.http_port}/f/small.pdf"
    assert [h.status for h in result.hops] == [206]
    assert set(result.timings) == {"fetch", "first_byte"}


async def test_https_with_a_valid_certificate(demo: Demo) -> None:
    """[21] Pinned TLS on the real fetch."""
    result = await run(demo, "/f/small.pdf", https=True)
    assert result.failure is None and result.whole_file is True


async def test_https_with_a_certificate_for_another_host(demo: Demo) -> None:
    """[22] FETCH_TLS_ERROR, nothing read."""
    config = demo.settings()
    url = f"https://a.demo.test:{demo.wrong_cert_port}/f/small.pdf"
    result = await fetch(url, config, RecordingResolver(config))
    assert result.failure == Finding("FETCH_TLS_ERROR")
    assert (result.ended, result.bytes_read) == ("error", 0)
    assert [h.url for h in result.hops] == [url]


# --- the byte cap (200 MB streams) ----------------------------------------------------------


async def capped(demo: Demo, path: str) -> tuple[FetchResult, float, int]:
    tracemalloc.start()
    started = time.monotonic()
    try:
        result = await run(demo, path)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return result, time.monotonic() - started, peak


async def test_big_stream_with_range_stops_at_the_cap(demo: Demo) -> None:
    """[2] 206 + Content-Range: Range confirmed, total size known, partial."""
    result, seconds, peak = await capped(demo, "/big?range=yes")
    assert result.failure is None
    assert (result.status_code, result.range_supported) == (206, True)
    assert result.total_size == 200 * 1024 * 1024
    assert (result.ended, result.bytes_read, len(result.body_head)) == ("cap", CAP, CAP)
    assert result.whole_file is False
    assert seconds < 15
    assert peak < 32 * 1024 * 1024  # Python memory stays near the cap, never the 200 MB


async def test_big_stream_ignoring_range_is_cut_at_the_cap(demo: Demo) -> None:
    """[13] Server ignores Range: 200 with the whole body; read the first cap bytes, abort."""
    result, seconds, peak = await capped(demo, "/big?range=no")
    assert result.failure is None
    assert (result.status_code, result.range_supported) == (200, False)
    assert (result.ended, result.bytes_read, len(result.body_head)) == ("cap", CAP, CAP)
    assert result.whole_file is False
    assert seconds < 15
    assert peak < 32 * 1024 * 1024


# --- slow, broken and odd bodies --------------------------------------------------------------


async def test_slow_drip_trips_the_minimum_throughput(demo: Demo) -> None:
    """[14] One byte every 0.3 s: after the grace period the fetch stops, bytes kept."""
    result = await run(demo, "/slow", min_throughput_grace_s=0.5)
    assert result.failure == Finding("FETCH_TIMEOUT")
    assert result.ended == "timeout"
    assert 1 <= result.bytes_read < 64
    assert result.body_head.startswith(b"%PDF"[: result.bytes_read])
    assert [h.status for h in result.hops] == [200]  # the interrupted hop is still listed


async def test_total_deadline_covers_everything(demo: Demo) -> None:
    started = time.monotonic()
    result = await run(demo, "/slow", total_deadline_s=1, min_throughput_grace_s=100)
    assert result.failure == Finding("FETCH_TIMEOUT")
    assert result.bytes_read >= 1
    assert time.monotonic() - started < 3


async def test_connection_reset_keeps_the_bytes(demo: Demo) -> None:
    """Promises 1 MB, sends 4096 bytes, drops the connection."""
    result = await run(demo, "/reset")
    assert result.failure == Finding("FETCH_INTERRUPTED")
    assert (result.ended, result.bytes_read) == ("interrupted", 4096)
    assert result.body_head == b"\0" * 4096


async def test_chunked_body_that_ends_cleanly_is_whole(demo: Demo) -> None:
    """D54: the terminating chunk marks the end, so the length is known once it arrives."""
    result = await run(demo, "/chunked")
    assert result.failure is None
    assert result.chunked is True and result.ended == "complete"
    assert result.body_head.startswith(b"%PDF-1.4")
    assert result.total_size == result.bytes_read == len(result.body_head)
    assert result.whole_file is True


async def test_gzip_body_is_decoded_up_to_the_cap_and_flagged(demo: Demo) -> None:
    """[20] Compressed although identity was asked: decoded, flagged, partial (D10)."""
    result = await run(demo, "/gzip/small.pdf")
    assert result.failure is None
    assert result.body_head == SAMPLE
    assert result.bytes_read == len(gzip.compress(SAMPLE, mtime=0))
    assert Finding("FETCH_UNEXPECTED_ENCODING", {"encoding": "gzip"}) in result.findings
    assert result.total_size is None and result.whole_file is False


async def test_empty_body(demo: Demo) -> None:
    """[19]"""
    result = await run(demo, "/empty")
    assert result.failure == Finding("FETCH_EMPTY")
    assert (result.ended, result.bytes_read) == ("complete", 0)


async def test_web_page_stops_before_the_body(demo: Demo) -> None:
    """[17] text/html: decided from headers, no body byte read, never "empty"."""
    result = await run(demo, "/page")
    assert result.failure == Finding("LINK_IS_WEB_PAGE")
    assert result.metadata_only is True
    assert (result.bytes_read, result.body_head) == (0, b"")


# --- error statuses -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "failure"),
    [
        (401, Finding("FETCH_AUTH_REQUIRED", {"status": 401})),  # [16]
        (403, Finding("FETCH_AUTH_REQUIRED", {"status": 403})),
        (404, Finding("FETCH_HTTP_ERROR", {"status": 404})),  # [15]
        (410, Finding("FETCH_HTTP_ERROR", {"status": 410})),
        (500, Finding("FETCH_HTTP_ERROR", {"status": 500})),
    ],
)
async def test_error_statuses(demo: Demo, status: int, failure: Finding) -> None:
    result = await run(demo, f"/status/{status}")
    assert result.failure == failure
    assert result.status_code == status
    assert result.bytes_read == 0
    assert [h.status for h in result.hops] == [status]


async def test_429_is_retried_once_after_a_short_retry_after(demo: Demo) -> None:
    """The demo asks for 1 s; one retry, then FETCH_RATE_LIMITED (never a loop)."""
    started = time.monotonic()
    result = await run(demo, "/status/429")
    assert time.monotonic() - started >= 1
    assert result.failure == Finding("FETCH_RATE_LIMITED")


async def test_429_with_a_longer_retry_after_is_not_retried(demo: Demo) -> None:
    started = time.monotonic()
    result = await run(demo, "/status/429", max_retry_after_s=0)
    assert time.monotonic() - started < 1
    assert result.failure == Finding("FETCH_RATE_LIMITED")


async def test_connection_refused(demo: Demo) -> None:
    closed = free_port()
    config = demo.settings(extra_ports=(closed,))
    result = await fetch(f"http://a.demo.test:{closed}/f", config, RecordingResolver(config))
    assert result.failure == Finding("FETCH_INTERRUPTED")
    assert result.bytes_read == 0


# --- redirects through the real fetch -------------------------------------------------------


async def test_redirect_chain_to_a_file(demo: Demo) -> None:
    """[8] a -> b -> c, then the file; HEAD redirects are followed without a GET."""
    result = await run(demo, "/redirect/chain?n=2&to=/f/small.pdf")
    assert result.failure is None
    assert result.body_head == SAMPLE
    assert [h.status for h in result.hops] == [302, 302, 206]
    assert result.display_host == "c.demo.test"
    assert result.changed_host is True
    assert Finding("REDIR_CROSS_DOMAIN", {"final_host": "c.demo.test"}) in result.findings


async def test_redirect_to_localhost_is_refused(demo: Demo) -> None:
    """[11]"""
    result = await run(demo, "/redirect/internal")
    assert result.failure == Finding("SSRF_BLOCKED_AT_HOP", {"hop": 1})
    assert result.bytes_read == 0
    assert result.final_url is None


async def test_redirect_loop(demo: Demo) -> None:
    """[10]"""
    result = await run(demo, "/redirect/loop")
    assert result.failure == Finding("REDIR_LOOP")
