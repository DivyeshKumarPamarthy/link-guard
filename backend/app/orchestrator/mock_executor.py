"""MockExecutor: a fake scanner that always answers UNSAFE (task T0.7).

It lets the web app and the API be built and tested before the real engine exists.
It never touches the network. It returns plain JSON-compatible data, the same seam the
real in-process executor (T2.4) and the Phase 2 container runner will use.
"""

import asyncio
from typing import Protocol

from pydantic import JsonValue

ExecutorOutput = dict[str, JsonValue]


class Executor(Protocol):
    """Runs one scan and returns the outcome fields of a ScanResult as plain JSON data."""

    async def run(self, url: str) -> ExecutorOutput: ...


# The spec §2 example outcome: a .mp4 that is really a Windows executable.
MOCK_OUTCOME: ExecutorOutput = {
    "status": "completed",
    "final_url": "https://files.example/movie.mp4",
    "display_host": "files.example",
    "punycode_host": "files.example",
    "link_type": "shortened",
    "verdict": "UNSAFE",
    "display_verdict": "UNSAFE",
    "score": 70,
    "confidence": "high",
    "scope": {
        "mode": "full",
        "bytes_analyzed": 48213,
        "total_bytes": 48213,
        "range_supported": True,
        "label": "Whole file checked (47 KB)",
    },
    "headline": "Blocked: file named .mp4 is actually a Windows executable",
    "file": {
        "claimed_name": "movie.mp4",
        "name_source": "content-disposition",
        "content_type": "video/mp4",
        "detected_type": "pe-executable",
        "detected_label": "Windows executable",
        "family": "executable",
        "detection_confidence": "certain",
        "first_bytes_hex": "4d5a90000300000004000000ffff0000",
        "signature": {"offset": 0, "length": 2, "name": "MZ (Windows executable)"},
    },
    "redirects": [
        {"url": "https://short.example/abc", "status": 302, "address_class": "public"},
        {"url": "https://files.example/movie.mp4", "status": 200, "address_class": "public"},
    ],
    "reasons": [
        {
            "code": "TYPE_MISMATCH_EXEC",
            "severity": "high",
            "weight": 70,
            "group": "type",
            "message": "The file is named .mp4 but its content is a Windows executable.",
            "evidence": {
                "claimed_ext": "mp4",
                "detected": "pe-executable",
                "detected_label": "Windows executable",
            },
        },
        {
            "code": "REDIR_CROSS_DOMAIN",
            "severity": "info",
            "weight": 0,
            "group": "redirect",
            "message": "The link ended on a different site: files.example.",
            "evidence": {"final_host": "files.example"},
        },
    ],
    "unavailable_signals": [],
}


class MockExecutor:
    def __init__(self, delay_ms: int) -> None:
        self.delay_ms = delay_ms

    async def run(self, url: str) -> ExecutorOutput:
        """Wait `delay_ms` (so clients really have to poll), then return the fixed outcome."""
        await asyncio.sleep(self.delay_ms / 1000)
        return {**MOCK_OUTCOME, "normalized_url": url, "timings_ms": {"total": self.delay_ms}}
