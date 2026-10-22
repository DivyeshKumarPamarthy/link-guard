"""The fetcher's pure rules (task T2.1): no network, no demo server."""

import gzip
import ssl
import zlib

import httpx
import pytest

from app.core.config import Settings
from app.engine.fetcher.fetch import Fetcher, FetchResult, caused_by_tls, status_failure
from app.engine.fetcher.pinned import new_client, tls_context
from app.engine.fetcher.redirects import Finding
from app.engine.fetcher.response_rules import (
    CappedDecoder,
    ContentRange,
    UnsupportedEncoding,
    content_encoding,
    is_web_page_headers,
    parse_content_range,
    parse_retry_after,
)

# --- Content-Range ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("bytes 0-99/1000", ContentRange(0, 99, 1000)),
        ("bytes 0-99/*", ContentRange(0, 99, None)),
        ("BYTES 0-0/1", ContentRange(0, 0, 1)),
        ("bytes */0", ContentRange(None, None, 0)),
        ("bytes 10-99/1000", ContentRange(10, 99, 1000)),  # parsed; the fetcher refuses start != 0
        (None, None),
        ("", None),
        ("bytes 0-99", None),  # no total
        ("bytes 0-99/50", None),  # end beyond total
        ("bytes 99-0/1000", None),  # end before start
        ("bytes -5/1000", None),
        ("items 0-99/1000", None),
        ("bytes 0-99/1e3", None),
        ("bytes */*", None),
    ],
)
def test_parse_content_range(value: str | None, expected: ContentRange | None) -> None:
    assert parse_content_range(value) == expected


# --- Retry-After --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1", 1),
        (" 5 ", 5),
        ("0", 0),
        ("-1", None),
        ("1.5", None),
        ("Wed, 21 Oct 2026 07:28:00 GMT", None),  # the date form is never waited for
        ("", None),
        (None, None),
    ],
)
def test_parse_retry_after(value: str | None, expected: int | None) -> None:
    assert parse_retry_after(value) == expected


# --- web page predicate (D53) -------------------------------------------------------------


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"content-type": "text/html"}, True),
        ({"content-type": "Text/HTML; charset=utf-8"}, True),
        ({"content-type": "application/xhtml+xml"}, True),
        ({"content-type": "text/html", "content-disposition": "inline"}, True),
        (
            {"content-type": "text/html", "content-disposition": 'attachment; filename="a.html"'},
            False,
        ),
        ({"content-type": "text/html", "content-disposition": "ATTACHMENT"}, False),
        ({"content-type": "application/pdf"}, False),
        ({"content-type": "text/plain"}, False),
        ({}, False),
    ],
)
def test_is_web_page_headers(headers: dict[str, str], expected: bool) -> None:
    assert is_web_page_headers(headers) is expected


# --- content encoding ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", None),
        ("identity", None),
        ("GZIP", "gzip"),
        ("x-gzip", "x-gzip"),
        ("deflate", "deflate"),
    ],
)
def test_decodable_encodings(value: str, expected: str | None) -> None:
    assert content_encoding({"content-encoding": value}) == expected


@pytest.mark.parametrize("value", ["br", "zstd", "compress", "gzip, gzip", "made-up"])
def test_other_encodings_are_not_decoded(value: str) -> None:
    with pytest.raises(UnsupportedEncoding) as caught:
        content_encoding({"content-encoding": value})
    assert caught.value.encoding == value


def test_gzip_is_decoded_piece_by_piece() -> None:
    original = b"%PDF-1.4 " + bytes(range(256)) * 40
    packed = gzip.compress(original, mtime=0)
    decoder = CappedDecoder("gzip", limit=1_000_000)
    out = b"".join(decoder.feed(packed[i : i + 7]) for i in range(0, len(packed), 7))
    assert out == original
    assert decoder.full is False


def test_decompression_bomb_stops_at_the_cap() -> None:
    """50 MB of zeros compresses to about 50 KB; the decoder must stop at the cap."""
    bomb = gzip.compress(b"\0" * 50_000_000, mtime=0)
    decoder = CappedDecoder("gzip", limit=1000)
    out = decoder.feed(bomb)
    assert len(out) == 1000
    assert decoder.full is True
    assert decoder.feed(b"more") == b""  # nothing more once full


@pytest.mark.parametrize("wrapped", [True, False])
def test_deflate_zlib_wrapped_or_raw(wrapped: bool) -> None:
    original = b"deflate body " * 50
    compressor = zlib.compressobj(wbits=zlib.MAX_WBITS if wrapped else -zlib.MAX_WBITS)
    packed = compressor.compress(original) + compressor.flush()
    assert CappedDecoder("deflate", limit=10_000).feed(packed) == original


def test_corrupt_gzip_is_refused() -> None:
    with pytest.raises(UnsupportedEncoding):
        CappedDecoder("gzip", limit=1000).feed(b"this is not gzip at all")


# --- error statuses (D57) and TLS errors ---------------------------------------------------


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, Finding("FETCH_AUTH_REQUIRED", {"status": 401})),
        (403, Finding("FETCH_AUTH_REQUIRED", {"status": 403})),
        (429, Finding("FETCH_RATE_LIMITED")),
        (404, Finding("FETCH_HTTP_ERROR", {"status": 404})),
        (410, Finding("FETCH_HTTP_ERROR", {"status": 410})),
        (500, Finding("FETCH_HTTP_ERROR", {"status": 500})),
        (503, Finding("FETCH_HTTP_ERROR", {"status": 503})),
        (300, Finding("FETCH_HTTP_ERROR", {"status": 300})),
        (304, Finding("FETCH_HTTP_ERROR", {"status": 304})),
    ],
)
def test_status_failure(status: int, expected: Finding) -> None:
    assert status_failure(status) == expected


def test_tls_error_is_found_in_the_exception_chain() -> None:
    try:
        try:
            raise ssl.SSLCertVerificationError("certificate verify failed")
        except ssl.SSLError as inner:
            raise httpx.ConnectError("handshake failed") from inner
    except httpx.ConnectError as outer:
        assert caused_by_tls(outer) is True
    assert caused_by_tls(httpx.ConnectError("Connection refused")) is False


# --- the client refuses cookies (spec §5: no cookies) --------------------------------------


@pytest.mark.asyncio
async def test_client_keeps_no_cookies() -> None:
    """A Set-Cookie on the HEAD must never be sent back on the GET of the same hop."""
    async with new_client(Settings(), tls_context(Settings())) as client:
        request = httpx.Request("HEAD", "https://93.184.216.34/f")
        response = httpx.Response(
            200, headers={"set-cookie": "session=abc; Path=/"}, request=request
        )
        client.cookies.extract_cookies(response)
        assert len(client.cookies.jar) == 0
        follow_up = client.build_request("GET", "https://93.184.216.34/f")
        assert "cookie" not in follow_up.headers


# --- scope: whole file or not (D54) ---------------------------------------------------------


@pytest.mark.parametrize(
    ("result", "whole"),
    [
        (FetchResult(ended="complete", bytes_read=10, total_size=10), True),
        (FetchResult(ended="complete", bytes_read=10, total_size=None), False),  # read to close
        (FetchResult(ended="cap", bytes_read=10, total_size=10), False),
        (FetchResult(ended="complete", bytes_read=9, total_size=10), False),
        (
            FetchResult(
                ended="complete",
                bytes_read=10,
                total_size=10,
                findings=[Finding("FETCH_UNEXPECTED_ENCODING", {"encoding": "gzip"})],
            ),
            False,
        ),
        (FetchResult(ended="complete", metadata_only=True, total_size=0), False),
    ],
)
def test_whole_file(result: FetchResult, whole: bool) -> None:
    assert result.whole_file is whole


# --- encodings LinkGuard does not decode (D61), on a response built in memory -----------------


def raw_response(headers: dict[str, str], body: bytes) -> httpx.Response:
    """A response whose body is still a raw stream, as on the network (content= would make
    httpx decode it at once)."""
    return httpx.Response(200, headers=headers, stream=httpx.ByteStream(body))


@pytest.mark.asyncio
@pytest.mark.parametrize("encoding", ["br", "zstd", "gzip, gzip"])
async def test_undecodable_encoding_is_unable_to_verify(encoding: str) -> None:
    fetcher = Fetcher(Settings())
    response = raw_response({"content-encoding": encoding}, b"\x8b\x00")
    fetcher.result.headers = {"content-encoding": encoding}
    await fetcher.read_final(response)
    assert fetcher.result.failure == Finding("FETCH_UNSUPPORTED_ENCODING", {"encoding": encoding})
    assert (fetcher.result.ended, fetcher.result.bytes_read) == ("error", 0)  # never guessed at


@pytest.mark.asyncio
async def test_corrupt_gzip_body_is_unable_to_verify() -> None:
    fetcher = Fetcher(Settings())
    response = raw_response({"content-encoding": "gzip"}, b"not gzip")
    fetcher.result.headers = {"content-encoding": "gzip"}
    await fetcher.read_final(response)
    assert fetcher.result.failure == Finding("FETCH_UNSUPPORTED_ENCODING", {"encoding": "gzip"})
    assert fetcher.result.ended == "error"
