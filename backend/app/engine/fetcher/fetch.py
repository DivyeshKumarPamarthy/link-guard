"""The streaming fetch (task T2.1, spec §5, decisions D52–D60).

fetch() follows the link (redirects.py: every hop checked, one DNS lookup, pinned
connection) and reads at most LG_HEAD_FETCH_BYTES of the final file. Every way it can end
is mapped to a defined result; nothing is ever "Safe" because something failed.

Per hop, one client (D41):
1. HEAD. A redirect is followed without a GET (D52).
2. Otherwise one GET with `Range: bytes=0-(cap-1)`; that response is the one trusted
   (it is also the fallback for servers that mishandle HEAD).
3. On the final hop: error statuses are mapped (D57); an HTML page stops before the body
   (D53); otherwise the body is streamed, counting bytes actually read (D55), under the
   total deadline and the minimum throughput rule (D58).
"""

import asyncio
import ssl
import time
from dataclasses import dataclass, field
from typing import Literal

import httpx

from app.contract.models import RedirectHop
from app.core.config import Settings
from app.engine.fetcher.pinned import build_pinned_request, new_client, tls_context
from app.engine.fetcher.redirects import (
    Finding,
    HopResponse,
    RedirectOutcome,
    follow_redirects,
    is_redirect,
)
from app.engine.fetcher.resolver import Resolver
from app.engine.fetcher.response_rules import (
    CappedDecoder,
    UnsupportedEncoding,
    content_encoding,
    is_web_page_headers,
    parse_content_range,
    parse_retry_after,
)
from app.engine.fetcher.targets import Target

Ended = Literal["complete", "cap", "timeout", "interrupted", "error"]

# Spec §5: the only response headers kept (keys lowercased, values as received).
KEPT_HEADERS = (
    "content-type",
    "content-length",
    "content-disposition",
    "content-range",
    "content-encoding",
    "etag",
    "last-modified",
    "location",
    "retry-after",
)


@dataclass
class FetchResult:
    """Spec §5 FetchResult, as plain data the executor can serialise."""

    body_head: bytes = b""  # what detection reads (decoded if the server compressed it)
    bytes_read: int = 0  # bytes actually received from the network
    total_size: int | None = None
    range_supported: bool = False
    ended: Ended = "error"
    status_code: int | None = None
    headers: dict[str, str] = field(default_factory=dict)
    hops: list[RedirectHop] = field(default_factory=list)
    timings: dict[str, int] = field(default_factory=dict)
    failure: Finding | None = None  # why the file could not be checked (or was refused)
    findings: list[Finding] = field(default_factory=list)  # facts that do not stop the scan
    metadata_only: bool = False  # decided from headers alone (an HTML page)
    chunked: bool = False  # Transfer-Encoding: chunked (the end of the body is marked)
    final_url: str | None = None
    display_host: str | None = None
    punycode_host: str | None = None
    changed_host: bool = False

    @property
    def failure_code(self) -> str | None:
        return self.failure.code if self.failure else None

    @property
    def whole_file(self) -> bool:
        """Scope `full` (D54): the stream ended before the cap and the bytes read equal a
        known length (Content-Length, the Content-Range total, or a chunked body that ended
        with its terminating chunk). Partial otherwise: a body read until the connection
        closed with no length, the cap, an early end, or decoding."""
        return (
            self.ended == "complete"
            and not self.metadata_only
            and self.total_size is not None
            and self.bytes_read == self.total_size
            and not any(f.code == "FETCH_UNEXPECTED_ENCODING" for f in self.findings)
        )


class ThroughputTooLow(Exception):
    """The server is sending slower than LG_MIN_THROUGHPUT_BPS (a slow-drip server)."""


def kept_headers(headers: httpx.Headers) -> dict[str, str]:
    return {name: headers[name] for name in KEPT_HEADERS if name in headers}


def caused_by_tls(error: BaseException) -> bool:
    """A certificate or other TLS failure anywhere in the exception chain. A plain refused
    connection must not match (it is FETCH_INTERRUPTED)."""
    seen: BaseException | None = error
    while seen is not None:
        if isinstance(seen, ssl.SSLError):
            return True
        seen = seen.__cause__ or seen.__context__
    return False


def status_failure(status: int) -> Finding:
    """D57: what an error status on the final response means."""
    if status in (401, 403):
        return Finding("FETCH_AUTH_REQUIRED", {"status": status})
    if status == 429:
        return Finding("FETCH_RATE_LIMITED")
    return Finding("FETCH_HTTP_ERROR", {"status": status})


class Fetcher:
    """One fetch. Keeps its result outside the deadline, so bytes read before a timeout or
    an interruption are never lost."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.context = tls_context(settings)
        self.result = FetchResult()
        self.body = bytearray()
        self.current: Target | None = None  # the hop being contacted
        self.started = time.monotonic()
        self.deadline = self.started + settings.total_deadline_s
        self.request_headers = {
            "User-Agent": settings.user_agent,
            "Accept-Encoding": "identity",
            "Accept": "*/*",
        }

    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self.started) * 1000)

    async def send_hop(self, target: Target) -> HopResponse:
        """One hop, one client (D41): HEAD, then (unless HEAD redirected) one GET."""
        self.current = target
        self.result.status_code = None  # never a status left over from an earlier hop
        async with new_client(self.settings, self.context) as client:
            # Connection: close: the GET never waits behind (or rides on) the HEAD's
            # connection, which a server may still be busy with (D52).
            head_headers = {**self.request_headers, "Connection": "close"}
            head = await client.send(build_pinned_request(client, target, "HEAD", head_headers))
            await head.aclose()
            answer = HopResponse(head.status_code, tuple(head.headers.get_list("location")))
            if is_redirect(answer):
                self.result.headers = kept_headers(head.headers)
                return answer
            return await self.get(client, target)

    async def get(self, client: httpx.AsyncClient, target: Target) -> HopResponse:
        cap = self.settings.head_fetch_bytes
        headers = {**self.request_headers, "Range": f"bytes=0-{cap - 1}"}
        request = build_pinned_request(client, target, "GET", headers)
        response = await client.send(request, stream=True)
        try:
            if response.status_code == 429 and self.may_retry(response.headers):
                await response.aclose()
                await asyncio.sleep(parse_retry_after(response.headers.get("retry-after")) or 0)
                response = await client.send(request, stream=True)
            answer = HopResponse(response.status_code, tuple(response.headers.get_list("location")))
            self.result.status_code = response.status_code
            self.result.headers = kept_headers(response.headers)
            if not is_redirect(answer):
                await self.read_final(response)
            return answer
        finally:
            await response.aclose()

    def may_retry(self, headers: httpx.Headers) -> bool:
        """D57: one retry, only for a short Retry-After in seconds that fits the deadline."""
        wait = parse_retry_after(headers.get("retry-after"))
        return (
            wait is not None
            and wait <= self.settings.max_retry_after_s
            and time.monotonic() + wait < self.deadline
        )

    async def read_final(self, response: httpx.Response) -> None:
        """The final response: map its status, stop for a web page, or read the body."""
        status = response.status_code
        result = self.result
        if status == 416:
            unsatisfied = parse_content_range(response.headers.get("content-range"))
            if unsatisfied is not None and unsatisfied.start is None and unsatisfied.total == 0:
                result.total_size, result.ended = 0, "complete"
                result.failure = Finding("FETCH_EMPTY")
            else:
                result.failure = status_failure(status)
            return
        if not 200 <= status < 300:
            result.failure = status_failure(status)  # also 300, 304, a 3xx without Location
            return
        if is_web_page_headers(result.headers):
            result.metadata_only, result.ended = True, "complete"
            result.failure = Finding("LINK_IS_WEB_PAGE")
            return
        if not self.check_range(response):
            return
        try:
            encoding = content_encoding(result.headers)
        except UnsupportedEncoding as unsupported:
            result.failure = unsupported_encoding(unsupported.encoding)
            result.ended = "error"
            return
        if encoding is not None:
            result.findings.append(Finding("FETCH_UNEXPECTED_ENCODING", {"encoding": encoding}))
            result.total_size = None  # Content-Length counts compressed bytes
        result.chunked = "chunked" in response.headers.get("transfer-encoding", "").lower()
        await self.stream(response, encoding)
        if result.ended == "complete" and result.chunked and result.total_size is None:
            # httpx raises if a chunked body ends without its terminating chunk, so a
            # complete chunked stream is the whole body: its length is now known (D54).
            if encoding is None:
                result.total_size = result.bytes_read
        if result.ended == "complete" and not self.body:
            result.failure = Finding("FETCH_EMPTY")

    def check_range(self, response: httpx.Response) -> bool:
        """D54: was Range honoured? Returns False when the bytes cannot be used."""
        result = self.result
        cap = self.settings.head_fetch_bytes
        if response.status_code != 206:
            result.range_supported = False
            length = response.headers.get("content-length", "")
            result.total_size = int(length) if length.isascii() and length.isdigit() else None
            return True
        span = parse_content_range(response.headers.get("content-range"))
        content_type = response.headers.get("content-type", "").lower()
        if (
            span is None
            or span.start != 0
            or span.end is None
            or content_type.startswith("multipart/")
        ):
            result.failure = Finding("FETCH_HTTP_ERROR", {"status": 206})
            return False
        result.total_size = span.total
        result.range_supported = span.end <= cap - 1
        return True

    async def stream(self, response: httpx.Response, encoding: str | None) -> None:
        """Read raw bytes (httpx never decodes them) up to the cap, then stop without
        draining the rest (D55). Throughput is checked after the grace period (D58)."""
        cap = self.settings.head_fetch_bytes
        decoder = CappedDecoder(encoding, cap) if encoding else None
        body_started = time.monotonic()
        result = self.result
        try:
            async for chunk in response.aiter_raw():
                if not chunk:
                    continue
                if "first_byte" not in result.timings:
                    result.timings["first_byte"] = self.elapsed_ms()
                chunk = chunk[: cap - result.bytes_read]
                result.bytes_read += len(chunk)
                self.body += decoder.feed(chunk) if decoder else chunk
                if result.bytes_read >= cap or (decoder is not None and decoder.full):
                    result.ended = "cap"
                    return
                self.check_throughput(body_started)
            result.ended = "complete"
        except UnsupportedEncoding as corrupt:
            result.failure = unsupported_encoding(corrupt.encoding)
            result.ended = "error"
        finally:  # also on a timeout or a reset: the bytes read so far are kept
            result.body_head = bytes(self.body)

    def check_throughput(self, body_started: float) -> None:
        elapsed = time.monotonic() - body_started
        if (
            elapsed > self.settings.min_throughput_grace_s
            and self.result.bytes_read / elapsed < self.settings.min_throughput_bps
        ):
            raise ThroughputTooLow


def unsupported_encoding(encoding: str) -> Finding:
    """D61: a body compressed in a way we do not decode (br, zstd, stacked, or corrupt) is
    never guessed at: the file could not be checked (outcome unable)."""
    return Finding("FETCH_UNSUPPORTED_ENCODING", {"encoding": encoding})


def apply_outcome(
    result: FetchResult, outcome: RedirectOutcome, interrupted_hop: Target | None
) -> None:
    """Copy what the redirect logic learned into the result. If the fetch stopped in the
    middle of a hop (deadline, reset), that hop is listed too, as the final one."""
    if interrupted_hop is not None and outcome.final_target is None:
        outcome.hops.append(
            RedirectHop(
                url=interrupted_hop.url,
                status=result.status_code,
                address_class=interrupted_hop.address_class,
            )
        )
        outcome.final_target = interrupted_hop
    result.hops = list(outcome.hops)
    result.findings = [*outcome.findings, *result.findings]
    result.changed_host = outcome.changed_host
    if outcome.stop is not None and result.failure is None:
        result.failure = outcome.stop
    if outcome.final_target is not None:
        target = outcome.final_target
        result.final_url = target.url
        result.display_host = target.display_host
        result.punycode_host = target.punycode_host


async def fetch(url: str, settings: Settings, resolver: Resolver) -> FetchResult:
    """Follow the link and read the start of the file; every failure becomes a defined
    result with a reason code (spec §5, §8). Non-httpx errors propagate (ANALYSIS_ERROR)."""
    fetcher = Fetcher(settings)
    result = fetcher.result
    outcome = RedirectOutcome()
    stopped_mid_hop = True
    try:
        async with asyncio.timeout(settings.total_deadline_s):
            await follow_redirects(url, settings, resolver, fetcher.send_hop, outcome)
        stopped_mid_hop = False
    except (TimeoutError, httpx.TimeoutException, ThroughputTooLow):
        result.ended, result.failure = "timeout", Finding("FETCH_TIMEOUT")
    except httpx.TransportError as error:
        if caused_by_tls(error):
            result.ended, result.failure = "error", Finding("FETCH_TLS_ERROR")
        else:
            result.ended, result.failure = "interrupted", Finding("FETCH_INTERRUPTED")
    apply_outcome(result, outcome, fetcher.current if stopped_mid_hop else None)
    result.timings["fetch"] = fetcher.elapsed_ms()
    return result
