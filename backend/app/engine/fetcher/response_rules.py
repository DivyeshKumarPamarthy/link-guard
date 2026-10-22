"""Small, pure rules for reading a response (task T2.1, decisions D52–D60).

Each rule is a separate function with no network, so it is tested on its own and the
streaming code in fetch.py stays readable.
"""

import zlib
from collections.abc import Mapping
from dataclasses import dataclass

WEB_PAGE_TYPES = ("text/html", "application/xhtml+xml")
DECODABLE_ENCODINGS = ("gzip", "x-gzip", "deflate")


class UnsupportedEncoding(Exception):
    """The body is compressed in a way LinkGuard cannot (or will not) decode."""

    def __init__(self, encoding: str) -> None:
        super().__init__(encoding)
        self.encoding = encoding


@dataclass(frozen=True)
class ContentRange:
    """A parsed `Content-Range: bytes START-END/TOTAL` (TOTAL may be `*`, unknown), or the
    "unsatisfied" form `bytes */TOTAL` (start and end are None)."""

    start: int | None
    end: int | None
    total: int | None


def parse_content_range(value: str | None) -> ContentRange | None:
    """None when the header is missing or malformed (the caller treats that as unusable)."""
    if value is None:
        return None
    unit, _, rest = value.strip().partition(" ")
    span, slash, total_text = rest.strip().partition("/")
    if unit.lower() != "bytes" or not slash:
        return None
    total = None if total_text == "*" else _number(total_text)
    if total is None and total_text != "*":
        return None
    if span == "*":
        return ContentRange(None, None, total) if total is not None else None
    first, dash, last = span.partition("-")
    start, end = _number(first), _number(last)
    if not dash or start is None or end is None or end < start:
        return None
    if total is not None and end >= total:
        return None
    return ContentRange(start, end, total)


def _number(text: str) -> int | None:
    text = text.strip()
    return int(text) if text.isascii() and text.isdigit() else None


def parse_retry_after(value: str | None) -> int | None:
    """Only the "seconds" form is honoured; an HTTP date (or anything else) gives None,
    which means "do not retry" (D57)."""
    return _number(value) if value is not None else None


def is_web_page_headers(headers: Mapping[str, str]) -> bool:
    """An HTML page rather than a download: Content-Type text/html or application/xhtml+xml
    without `Content-Disposition: attachment` (spec §6, D9, D53). Parameters and case are
    ignored; `inline` still counts as a page. The router (T3.1) reuses this rule."""
    media = headers.get("content-type", "").split(";")[0].strip().lower()
    disposition = headers.get("content-disposition", "").split(";")[0].strip().lower()
    return media in WEB_PAGE_TYPES and disposition != "attachment"


def content_encoding(headers: Mapping[str, str]) -> str | None:
    """The encoding to undo, or None for none/identity. Anything we do not decode raises
    UnsupportedEncoding, including stacked encodings like "gzip, gzip"."""
    value = headers.get("content-encoding", "").strip().lower()
    if value in ("", "identity"):
        return None
    if value in DECODABLE_ENCODINGS:
        return value
    raise UnsupportedEncoding(value)


class CappedDecoder:
    """Undoes gzip or deflate a piece at a time and never produces more than `limit` bytes,
    so a small compressed body that expands to gigabytes (a decompression bomb) stops at the
    cap (CLAUDE.md: never decode beyond the cap). A corrupt stream raises
    UnsupportedEncoding."""

    def __init__(self, encoding: str, limit: int) -> None:
        self.encoding = encoding
        self.limit = limit
        self.produced = 0
        self._started = False
        self._decoder = self._new(zlib.MAX_WBITS | 16 if encoding != "deflate" else zlib.MAX_WBITS)

    @staticmethod
    def _new(wbits: int) -> "zlib._Decompress":
        return zlib.decompressobj(wbits)

    @property
    def full(self) -> bool:
        return self.produced >= self.limit

    def feed(self, data: bytes) -> bytes:
        try:
            return self._feed(data)
        except zlib.error:
            # "deflate" is meant to be zlib-wrapped, but some servers send it raw.
            if self.encoding == "deflate" and not self._started:
                self._decoder = self._new(-zlib.MAX_WBITS)
                try:
                    return self._feed(data)
                except zlib.error:
                    pass
            raise UnsupportedEncoding(self.encoding) from None

    def _feed(self, data: bytes) -> bytes:
        out = bytearray()
        while data and not self.full:
            piece = self._decoder.decompress(data, self.limit - self.produced)
            self._started = self._started or bool(piece)
            out += piece
            self.produced += len(piece)
            data = self._decoder.unconsumed_tail
        return bytes(out)
