"""What was actually read, and how sure that lets us be (spec §3: scope and confidence).

Every result must say how much of the file was checked (honesty rule), and a verdict about
part of a file must never look like a verdict about all of it. These are pure functions over
plain facts reported by the fetcher.
"""

from dataclasses import dataclass
from typing import Literal

from app.contract.models import Confidence, Scope, ScopeMode, Status, Verdict

# FetchResult.ended (spec §5): why the body stream stopped.
Ended = Literal["complete", "cap", "timeout", "interrupted", "error"]


@dataclass(frozen=True)
class ReadFacts:
    """The fetcher's facts about the body. `headers_only` means the decision was made from
    the headers and the body was deliberately not read (e.g. a `text/html` page)."""

    bytes_read: int = 0
    total_size: int | None = None
    range_supported: bool = False
    ended: Ended = "error"
    headers_only: bool = False


def scope_mode(status: Status, read: ReadFacts, unexpected_encoding: bool) -> ScopeMode:
    """Spec §3 and D54. `full` needs a stream that ended on its own with every byte of a
    KNOWN length (Content-Length, the Content-Range total, or a chunked body that ended with
    its terminating chunk: the fetcher then sets total_size). A body read until the
    connection closed has no known length, so it is partial. An unexpected encoding forces
    `partial` because the bytes were not the file itself."""
    if status != Status.completed:
        return ScopeMode.none
    if read.headers_only:
        return ScopeMode.metadata_only
    if read.bytes_read == 0:
        return ScopeMode.none
    if unexpected_encoding:
        return ScopeMode.partial
    if read.ended == "complete" and read.total_size == read.bytes_read:
        return ScopeMode.full
    return ScopeMode.partial


def format_size(n: int) -> str:
    """Human size with 1024-based units: 512 bytes, 47 KB, 5 MB, 1.5 GB."""
    if n < 1024:
        return "1 byte" if n == 1 else f"{n} bytes"
    if n < 1024**2:
        return f"{round(n / 1024)} KB"
    if n < 1024**3:
        return f"{round(n / 1024**2, 1):g} MB"
    return f"{round(n / 1024**3, 1):g} GB"


def scope_label(mode: ScopeMode, read: ReadFacts, unexpected_encoding: bool) -> str:
    """The one-line "What was read" text shown in the report and in NO_ISSUES headlines."""
    if mode == ScopeMode.full:
        return f"Whole file checked ({format_size(read.bytes_read)})"
    if mode == ScopeMode.metadata_only:
        return "Only the server's headers were read"
    if mode == ScopeMode.none:
        return "Nothing was read"
    if unexpected_encoding:
        return f"{format_size(read.bytes_read)} read, but sent compressed"
    if read.total_size is not None:
        return f"First {format_size(read.bytes_read)} of {format_size(read.total_size)}"
    return f"First {format_size(read.bytes_read)} (total size unknown)"


def build_scope(status: Status, read: ReadFacts, unexpected_encoding: bool) -> Scope:
    mode = scope_mode(status, read, unexpected_encoding)
    return Scope(
        mode=mode,
        bytes_analyzed=read.bytes_read if mode != ScopeMode.none else 0,
        total_bytes=read.total_size,
        range_supported=read.range_supported,
        label=scope_label(mode, read, unexpected_encoding),
    )


def confidence_for(
    status: Status, verdict: Verdict | None, scope: Scope, unexpected_encoding: bool
) -> Confidence | None:
    """Spec §3: high only for a whole-file read; medium only when the part we read is a
    confirmed byte range of a known-size file; low for everything else, including any
    UNABLE_TO_VERIFY (we could not check, so we cannot be sure)."""
    if status != Status.completed:
        return None
    if verdict == Verdict.UNABLE_TO_VERIFY or unexpected_encoding:
        return Confidence.low
    if scope.mode == ScopeMode.full:
        return Confidence.high
    if scope.mode == ScopeMode.partial and scope.range_supported and scope.total_bytes:
        return Confidence.medium
    return Confidence.low
