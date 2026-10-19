"""Generated bodies: the 200 MB MP4-shaped stream, the Range header parser, a tiny PDF.

Nothing here touches the disk: the big stream is computed on the fly, chunk by chunk,
so the demo can never fill the disk or memory (plan M7 edge case).
"""

from collections.abc import Iterator

CHUNK_SIZE = 64 * 1024

# An MP4 "ftyp" box: 4-byte size (24), "ftyp", brand "isom", minor version, compatible brands.
# A detector finds "ftyp" at offset 4 and calls the file MP4.
MP4_HEADER = (24).to_bytes(4, "big") + b"ftyp" + b"isom" + (0x200).to_bytes(4, "big") + b"isomiso2"

# Repeating filler after the header: bytes 0..255 over and over, so any offset has a known value.
_PATTERN = bytes(range(256)) * (CHUNK_SIZE // 256)

# Starts like a PDF (%PDF-) so detectors identify it; it is not a complete document.
TINY_PDF = (
    b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    b"1 0 obj << /Type /Catalog >> endobj\n"
    b"% LinkGuard demo body: PDF-shaped bytes for tests, not a full document.\n"
    b"%%EOF\n"
)


def big_byte(offset: int) -> int:
    """The byte the big stream has at `offset` (used by tests to check any range)."""
    if offset < len(MP4_HEADER):
        return MP4_HEADER[offset]
    return _PATTERN[offset % CHUNK_SIZE]


def big_chunks(start: int, end: int) -> Iterator[bytes]:
    """Yield the big stream's bytes from `start` up to and including `end`, 64 KB at a time."""
    position = start
    while position <= end:
        size = min(CHUNK_SIZE - position % CHUNK_SIZE, end - position + 1)
        chunk = bytearray(_PATTERN[position % CHUNK_SIZE : position % CHUNK_SIZE + size])
        # Overlay the MP4 header on the first bytes of the stream.
        for i in range(len(chunk)):
            if position + i < len(MP4_HEADER):
                chunk[i] = MP4_HEADER[position + i]
            else:
                break
        yield bytes(chunk)
        position += size


class RangeNotSatisfiable(Exception):
    """The Range header asks for bytes beyond the end of the body (HTTP 416)."""


def parse_range(header: str | None, total: int) -> tuple[int, int] | None:
    """Parse a single "bytes=" range into (start, end) inclusive.

    Returns None when there is no usable Range header (serve the whole body).
    Supports "a-b", "a-" and the suffix form "-n". Multiple ranges are not supported
    and are treated as no Range at all, which HTTP allows.
    """
    if not header or not header.startswith("bytes=") or "," in header:
        return None
    first, sep, last = header[len("bytes=") :].strip().partition("-")
    if not sep or (not first and not last):
        return None
    if not (first.isdigit() or first == "") or not (last.isdigit() or last == ""):
        return None
    if first == "":  # suffix range: the last n bytes
        length = int(last)
        if length == 0:
            raise RangeNotSatisfiable
        return max(total - length, 0), total - 1
    start = int(first)
    end = int(last) if last else total - 1
    if start >= total or end < start:
        raise RangeNotSatisfiable
    return start, min(end, total - 1)
