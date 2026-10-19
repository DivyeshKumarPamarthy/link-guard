"""Smoke tests for every demo endpoint, run in-process (task T1.1)."""

import gzip
from collections.abc import Iterator
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from demo_server.app import DeliberateReset, create_app
from demo_server.config import DemoSettings
from demo_server.streams import MP4_HEADER, TINY_PDF, big_byte, big_chunks, parse_range

SAMPLE = TINY_PDF * 50  # a 'sample.pdf' of a few KB


@pytest.fixture
def settings(tmp_path: Path) -> DemoSettings:
    samples = tmp_path / "samples"
    samples.mkdir()
    (samples / "sample.pdf").write_bytes(SAMPLE)
    return DemoSettings(
        samples_dir=samples,
        certs_dir=tmp_path / "certs",
        big_size_bytes=300_000,  # small in tests; the real default is 200 MB
        slow_interval_s=0.01,
        slow_total_bytes=5,
    )


@pytest.fixture
def client(settings: DemoSettings) -> Iterator[TestClient]:
    with TestClient(create_app(settings), base_url="http://a.demo.test:8081") as c:
        yield c


# --- /f/{name} ---------------------------------------------------------------------------


def test_sample_file_with_real_content_type(client: TestClient) -> None:
    r = client.get("/f/sample.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["accept-ranges"] == "bytes"
    assert r.content == SAMPLE


def test_sample_file_range_request(client: TestClient) -> None:
    r = client.get("/f/sample.pdf", headers={"Range": "bytes=0-4"})
    assert r.status_code == 206
    assert r.headers["content-range"] == f"bytes 0-4/{len(SAMPLE)}"
    assert r.content == b"%PDF-"


def test_sample_file_head_has_no_body(client: TestClient) -> None:
    r = client.head("/f/sample.pdf")
    assert r.status_code == 200
    assert r.headers["content-length"] == str(len(SAMPLE))
    assert r.content == b""


def test_missing_sample_says_how_to_fix_it(client: TestClient) -> None:
    r = client.get("/f/nothing.pdf")
    assert r.status_code == 404
    assert "make samples" in r.text


@pytest.mark.parametrize("name", ["..%2Fpyproject.toml", ".hidden", "..", "%2E%2E%2Fx"])
def test_sample_names_cannot_escape_the_folder(client: TestClient, name: str) -> None:
    assert client.get(f"/f/{name}").status_code == 404


# --- /big --------------------------------------------------------------------------------


def test_big_head_reports_full_size_and_range_support(client: TestClient) -> None:
    r = client.head("/big")
    assert r.status_code == 200
    assert r.headers["content-length"] == "300000"
    assert r.headers["accept-ranges"] == "bytes"
    assert r.headers["content-type"] == "video/mp4"


def test_big_range_returns_206_with_mp4_signature(client: TestClient) -> None:
    r = client.get("/big", headers={"Range": "bytes=0-15"})
    assert r.status_code == 206
    assert r.headers["content-range"] == "bytes 0-15/300000"
    assert r.content[4:8] == b"ftyp"  # MP4 signature at offset 4
    assert r.content == MP4_HEADER[:16]


def test_big_range_in_the_middle_matches_the_full_stream(client: TestClient) -> None:
    full = client.get("/big", headers={"Range": "bytes=0-299999"}).content
    part = client.get("/big", headers={"Range": "bytes=70000-70099"}).content
    assert part == full[70000:70100]
    assert len(full) == 300000


def test_big_suffix_range(client: TestClient) -> None:
    r = client.get("/big", headers={"Range": "bytes=-10"})
    assert r.headers["content-range"] == "bytes 299990-299999/300000"
    assert r.content == bytes(big_byte(o) for o in range(299990, 300000))


def test_big_range_past_the_end_is_416(client: TestClient) -> None:
    r = client.get("/big", headers={"Range": "bytes=300000-"})
    assert r.status_code == 416
    assert r.headers["content-range"] == "bytes */300000"


def test_big_with_range_no_ignores_range(client: TestClient) -> None:
    r = client.get("/big?range=no", headers={"Range": "bytes=0-15"})
    assert r.status_code == 200
    assert "accept-ranges" not in r.headers
    assert r.headers["content-length"] == "300000"
    assert len(r.content) == 300000


def test_big_stream_is_generated_lazily() -> None:
    """The real 200 MB stream: taking one chunk must not generate the rest."""
    chunks = big_chunks(0, 200 * 1024 * 1024 - 1)
    first = next(chunks)
    assert len(first) == 64 * 1024 and first[4:8] == b"ftyp"


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, None),
        ("bytes=0-9", (0, 9)),
        ("bytes=5-", (5, 99)),
        ("bytes=-5", (95, 99)),
        ("bytes=90-500", (90, 99)),
        ("bytes=0-1,5-6", None),  # multiple ranges: serve the whole body
        ("items=0-9", None),
        ("bytes=abc", None),
    ],
)
def test_parse_range(header: str | None, expected: tuple[int, int] | None) -> None:
    assert parse_range(header, 100) == expected


# --- slow, reset, chunked, gzip -------------------------------------------------------------


def test_slow_drips_the_declared_bytes(client: TestClient) -> None:
    r = client.get("/slow")
    assert r.headers["content-length"] == "5"
    assert r.content == TINY_PDF[:5]


def test_reset_breaks_off_mid_body(settings: DemoSettings) -> None:
    with TestClient(create_app(settings)) as c, pytest.raises(DeliberateReset):
        c.get("/reset")


def test_chunked_has_no_content_length(client: TestClient) -> None:
    r = client.get("/chunked")
    assert "content-length" not in r.headers
    assert r.content == TINY_PDF


def test_gzip_is_sent_compressed_regardless_of_accept_encoding(client: TestClient) -> None:
    with client.stream("GET", "/gzip/sample.pdf", headers={"Accept-Encoding": "identity"}) as r:
        raw = b"".join(r.iter_raw())
    assert r.headers["content-encoding"] == "gzip"
    assert r.headers["content-type"] == "application/pdf"
    assert gzip.decompress(raw) == SAMPLE


# --- redirects ----------------------------------------------------------------------------


def location(client: TestClient, path: str, base: str = "") -> str:
    r = client.get(base + path, follow_redirects=False)
    assert r.status_code == 302
    target: str = r.headers["location"]
    return target


def test_one_hop_chain_goes_to_the_next_host(client: TestClient) -> None:
    assert location(client, "/redirect/chain?n=1&to=/f/sample.pdf") == (
        "http://b.demo.test:8081/f/sample.pdf"
    )


def test_two_hop_chain_walks_a_b_c(client: TestClient) -> None:
    first = location(client, "/redirect/chain?n=2&to=/f/sample.pdf")
    assert first == "http://b.demo.test:8081/redirect/chain?n=1&to=/f/sample.pdf"
    second = location(client, first)
    assert second == "http://c.demo.test:8081/f/sample.pdf"


@pytest.mark.parametrize(
    "query", ["n=0", "n=11", "n=x", "to=https://evil.example/", "to=//evil.example/x"]
)
def test_chain_refuses_bad_parameters(client: TestClient, query: str) -> None:
    assert client.get(f"/redirect/chain?{query}", follow_redirects=False).status_code == 400


def test_loop_bounces_between_two_paths(client: TestClient) -> None:
    assert location(client, "/redirect/loop") == "/redirect/loop/b"
    assert location(client, "/redirect/loop/b") == "/redirect/loop"


def test_internal_redirect_points_at_localhost(client: TestClient) -> None:
    assert location(client, "/redirect/internal") == "http://127.0.0.1/"


def test_downgrade_goes_from_https_to_http(settings: DemoSettings) -> None:
    with TestClient(create_app(settings), base_url="https://a.demo.test:8443") as c:
        assert location(c, "/redirect/https-to-http?to=/f/sample.pdf") == (
            "http://a.demo.test:8081/f/sample.pdf"
        )


# --- statuses, page, empty ------------------------------------------------------------------


@pytest.mark.parametrize("code", [401, 403, 404, 410, 429, 500])
def test_error_statuses(client: TestClient, code: int) -> None:
    assert client.get(f"/status/{code}").status_code == code


def test_429_has_retry_after(client: TestClient) -> None:
    assert client.get("/status/429").headers["retry-after"] == "1"


def test_unlisted_status_is_refused(client: TestClient) -> None:
    assert client.get("/status/418").status_code == 400


def test_page_is_html(client: TestClient) -> None:
    r = client.get("/page")
    assert r.headers["content-type"].startswith("text/html")
    assert r.text.startswith("<!doctype html>")


def test_empty_has_zero_bytes(client: TestClient) -> None:
    r = client.get("/empty")
    assert r.status_code == 200
    assert r.headers["content-length"] == "0"
    assert r.content == b""
