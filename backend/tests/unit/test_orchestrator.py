"""Unit tests for Orchestrator and InProcessExecutor (task T2.4, spec §2, §3, §9, §13)."""

import asyncio
import io
import logging
import zipfile
from pathlib import Path
from typing import Any

import pytest

from app.contract.models import (
    AddressClass,
    Confidence,
    DisplayVerdict,
    RedirectHop,
    ScopeMode,
    State,
    Status,
    Verdict,
)
from app.core.config import Settings
from app.db.models import make_engine, make_session_factory
from app.engine.fetcher.fetch import FetchResult
from app.engine.fetcher.redirects import Finding
from app.main import build_executor
from app.orchestrator.executor import (
    FindingRecord,
    InProcessExecutor,
    RawScanReport,
    ReadFactsRecord,
)
from app.orchestrator.mock_executor import ExecutorOutput, MockExecutor
from app.orchestrator.scans import Orchestrator, ScanStore, ServerBusyError
from app.registry.loader import get_registry
from tests.ssrf.fakes import FakeResolver

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
PE_BYTES = b"MZ" + b"\x00" * (0x3C - 2) + b"\x40\x00\x00\x00" + b"PE\x00\x00" + b"\x00" * 64


def make_store(tmp_path: Path) -> ScanStore:
    registry = get_registry()
    engine = make_engine(f"sqlite:///{tmp_path / 'orch.db'}")
    return ScanStore(make_session_factory(engine), registry.rules_version)


def make_orchestrator(tmp_path: Path, executor: Any, **setting_overrides: Any) -> Orchestrator:
    settings = Settings(**setting_overrides)
    return Orchestrator(make_store(tmp_path), executor, get_registry(), settings)


# --- concurrency semaphore and 503 SERVER_BUSY guard -------------------------------------


class GateExecutor:
    """Blocks each scan on an Event while tracking concurrent execution."""

    def __init__(self) -> None:
        self.gate = asyncio.Event()
        self.started = asyncio.Event()
        self.current = 0
        self.peak = 0

    async def run(self, url: str) -> ExecutorOutput:
        self.current += 1
        self.peak = max(self.peak, self.current)
        self.started.set()
        try:
            await self.gate.wait()
            return RawScanReport(
                normalized_url=url,
                final_url=url,
                display_host="files.example",
                punycode_host="files.example",
                read=ReadFactsRecord(
                    bytes_read=len(PDF_BYTES),
                    total_size=len(PDF_BYTES),
                    range_supported=True,
                    ended="complete",
                ),
            ).model_dump(mode="json")
        finally:
            self.current -= 1


@pytest.mark.asyncio
async def test_semaphore_caps_concurrent_scans_and_rejects_above_max_waiting(
    tmp_path: Path,
) -> None:
    executor = GateExecutor()
    orch = make_orchestrator(
        tmp_path, executor, max_concurrent_scans=2, max_waiting_scans=2, busy_retry_after_s=7
    )

    # 2 running + 2 waiting = 4 accepted scans
    accepted = [orch.submit(f"https://files.example/{i}.pdf") for i in range(4)]
    assert orch.waiting_count == 2

    # 5th submission exceeds max_waiting_scans (2) -> ServerBusyError (503 SERVER_BUSY)
    with pytest.raises(ServerBusyError) as exc_info:
        orch.submit("https://files.example/overflow.pdf")
    assert exc_info.value.retry_after_s == 7

    # Let the first two enter the semaphore; the other two remain queued in the store
    await executor.started.wait()
    await asyncio.sleep(0.01)
    assert executor.peak == 2
    states = [orch.store.get(str(s.scan_id)).state for s in accepted]  # type: ignore[union-attr]
    assert states.count(State.running) == 2
    assert states.count(State.queued) == 2

    # Release the gate so all 4 finish; capacity recovers for new scans
    executor.gate.set()
    await orch.wait_for_running_scans()
    assert orch.waiting_count == 0
    assert executor.peak == 2
    for scan in accepted:
        done = orch.store.get(str(scan.scan_id))
        assert done is not None and done.state == State.done
        assert done.display_verdict == DisplayVerdict.SAFE

    # Submitting again now succeeds
    extra = orch.submit("https://files.example/after.pdf")
    await orch.wait_for_running_scans()
    assert orch.store.get(str(extra.scan_id)).state == State.done  # type: ignore[union-attr]


# --- overall timeout, exceptions, and validation before scoring -------------------------


class SlowExecutor:
    async def run(self, url: str) -> ExecutorOutput:
        await asyncio.sleep(5)
        return {}


@pytest.mark.asyncio
async def test_overall_timeout_produces_analysis_error_and_never_safe(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    orch = make_orchestrator(tmp_path, SlowExecutor(), total_deadline_s=0.04)
    with caplog.at_level(logging.ERROR):
        queued = orch.submit("https://slow.example/file.pdf?secret=topsecret")
        await orch.wait_for_running_scans()

    result = orch.store.get(str(queued.scan_id))
    assert result is not None
    assert result.state == State.done
    assert result.status == Status.completed
    assert result.verdict == Verdict.UNABLE_TO_VERIFY
    assert result.display_verdict == DisplayVerdict.UNABLE_TO_VERIFY
    assert [r.code for r in result.reasons or []] == ["ANALYSIS_ERROR"]
    assert "topsecret" not in caplog.text
    assert "REDACTED" in caplog.text


class CrashingExecutor:
    async def run(self, url: str) -> ExecutorOutput:
        raise ValueError(f"boom while reading {url}")


@pytest.mark.asyncio
async def test_executor_exception_is_redacted_and_produces_analysis_error(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    orch = make_orchestrator(tmp_path, CrashingExecutor())
    with caplog.at_level(logging.ERROR):
        queued = orch.submit("https://files.example/a.pdf?token=secret123")
        await orch.wait_for_running_scans()

    result = orch.store.get(str(queued.scan_id))
    assert result is not None
    assert result.verdict == Verdict.UNABLE_TO_VERIFY
    assert [r.code for r in result.reasons or []] == ["ANALYSIS_ERROR"]
    assert "secret123" not in caplog.text
    assert "REDACTED" in caplog.text


class MalformedRawExecutor:
    async def run(self, url: str) -> ExecutorOutput:
        # Unknown extra field and negative bytes_read: RawScanReport validation must reject it.
        return {
            "normalized_url": url,
            "findings": [],
            "read": {"bytes_read": -5},
            "unexpected_field": True,
        }


@pytest.mark.asyncio
async def test_malformed_raw_executor_output_is_rejected_before_scoring(
    tmp_path: Path,
) -> None:
    orch = make_orchestrator(tmp_path, MalformedRawExecutor())
    queued = orch.submit("https://files.example/a.pdf")
    await orch.wait_for_running_scans()

    result = orch.store.get(str(queued.scan_id))
    assert result is not None
    assert result.verdict == Verdict.UNABLE_TO_VERIFY
    assert [r.code for r in result.reasons or []] == ["ANALYSIS_ERROR"]


class UnknownCodeExecutor:
    async def run(self, url: str) -> ExecutorOutput:
        return RawScanReport(
            normalized_url=url,
            final_url=url,
            findings=[FindingRecord(code="TYPE_UNREGISTERED_CODE")],
            read=ReadFactsRecord(
                bytes_read=100, total_size=100, range_supported=True, ended="complete"
            ),
        ).model_dump(mode="json")


@pytest.mark.asyncio
async def test_orchestrator_logs_unknown_reason_code_and_never_marks_safe(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    orch = make_orchestrator(tmp_path, UnknownCodeExecutor())
    with caplog.at_level(logging.ERROR):
        queued = orch.submit("https://files.example/a.pdf")
        await orch.wait_for_running_scans()

    result = orch.store.get(str(queued.scan_id))
    assert result is not None
    assert result.verdict == Verdict.UNABLE_TO_VERIFY
    assert "TYPE_UNREGISTERED_CODE" in caplog.text


# --- InProcessExecutor pipeline (router -> fetcher -> detectors -> scorer) ---------------


def test_swapping_mock_and_real_executor_is_config_only() -> None:
    assert isinstance(build_executor(Settings()), InProcessExecutor)
    assert isinstance(build_executor(Settings(executor="mock")), MockExecutor)


@pytest.mark.asyncio
async def test_in_process_executor_handles_unsupported_and_rejected_without_network(
    tmp_path: Path,
) -> None:
    resolver = FakeResolver({})
    executor = InProcessExecutor(Settings(), resolver=resolver)
    orch = make_orchestrator(tmp_path, executor)

    q_magnet = orch.submit("magnet:?xt=urn:btih:abc")
    q_private = orch.submit("http://127.0.0.1/admin")
    q_scheme = orch.submit("file:///etc/passwd")
    await orch.wait_for_running_scans()

    magnet = orch.store.get(str(q_magnet.scan_id))
    assert magnet is not None
    assert magnet.status == Status.unsupported
    assert magnet.display_verdict == DisplayVerdict.UNSUPPORTED
    assert [r.code for r in magnet.reasons or []] == ["LINK_TYPE_UNSUPPORTED"]
    assert magnet.redirects == []

    private = orch.store.get(str(q_private.scan_id))
    assert private is not None
    assert private.status == Status.rejected
    assert private.display_verdict == DisplayVerdict.REJECTED
    assert [r.code for r in private.reasons or []] == ["URL_PRIVATE_ADDRESS"]
    assert private.redirects == []
    assert private.display_host == "127.0.0.1"

    scheme = orch.store.get(str(q_scheme.scan_id))
    assert scheme is not None
    assert scheme.status == Status.rejected
    assert [r.code for r in scheme.reasons or []] == ["URL_SCHEME_UNSUPPORTED"]
    assert resolver.calls == []


@pytest.mark.asyncio
async def test_in_process_executor_scores_disguised_executable_as_unsafe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_fetch(url: str, settings: Settings, resolver: Any) -> FetchResult:
        return FetchResult(
            body_head=PE_BYTES,
            bytes_read=len(PE_BYTES),
            total_size=len(PE_BYTES),
            range_supported=True,
            ended="complete",
            status_code=200,
            headers={
                "content-type": "video/mp4",
                "content-disposition": 'attachment; filename="movie.mp4"',
            },
            hops=[
                RedirectHop(
                    url="https://short.example/abc",
                    status=302,
                    address_class=AddressClass.public,
                ),
                RedirectHop(
                    url="https://files.example/movie.mp4",
                    status=200,
                    address_class=AddressClass.public,
                ),
            ],
            timings={"fetch": 25, "first_byte": 10},
            findings=[Finding("REDIR_CROSS_DOMAIN", {"final_host": "files.example"})],
            final_url="https://files.example/movie.mp4",
            display_host="files.example",
            punycode_host="files.example",
            changed_host=True,
        )

    monkeypatch.setattr("app.orchestrator.executor.fetch", fake_fetch)
    executor = InProcessExecutor(Settings(), resolver=FakeResolver({}))
    orch = make_orchestrator(tmp_path, executor)

    queued = orch.submit("https://short.example/abc")
    await orch.wait_for_running_scans()

    result = orch.store.get(str(queued.scan_id))
    assert result is not None
    assert result.status == Status.completed
    assert result.verdict == Verdict.UNSAFE
    assert result.display_verdict == DisplayVerdict.UNSAFE
    assert result.confidence == Confidence.high
    assert result.scope is not None and result.scope.mode == ScopeMode.full
    assert result.link_type == "shortened"
    assert result.file is not None
    assert result.file.claimed_name == "movie.mp4"
    assert result.file.detected_type == "pe-executable"
    codes = [r.code for r in result.reasons or []]
    assert "TYPE_MISMATCH_EXEC" in codes
    assert "TYPE_CONTENT_TYPE_MISMATCH" in codes
    assert "REDIR_CROSS_DOMAIN" in codes


@pytest.mark.asyncio
async def test_interrupted_fetch_drops_code_when_type_is_identified_but_keeps_when_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D59 and spec §8: FETCH_INTERRUPTED is dropped only when enough bytes arrived to
    identify a type (giving partial / NO_ISSUES_IN_CHECKED_PART at best)."""
    body_holder = {"data": PDF_BYTES}

    async def fake_fetch(url: str, settings: Settings, resolver: Any) -> FetchResult:
        data = body_holder["data"]
        return FetchResult(
            body_head=data,
            bytes_read=len(data),
            total_size=10_000,
            range_supported=True,
            ended="interrupted",
            status_code=200,
            headers={"content-type": "application/pdf"},
            hops=[RedirectHop(url=url, status=200, address_class=AddressClass.public)],
            failure=Finding("FETCH_INTERRUPTED"),
            final_url=url,
            display_host="files.example",
            punycode_host="files.example",
        )

    monkeypatch.setattr("app.orchestrator.executor.fetch", fake_fetch)
    executor = InProcessExecutor(Settings(), resolver=FakeResolver({}))
    orch = make_orchestrator(tmp_path, executor)

    # 1. Identified PDF bytes -> FETCH_INTERRUPTED dropped, SCAN_PARTIAL added -> NO_ISSUES
    q1 = orch.submit("https://files.example/doc.pdf")
    await orch.wait_for_running_scans()
    r1 = orch.store.get(str(q1.scan_id))
    assert r1 is not None
    assert r1.display_verdict == DisplayVerdict.NO_ISSUES_IN_CHECKED_PART
    assert [r.code for r in r1.reasons or []] == ["SCAN_PARTIAL"]

    # 2. Unidentified bytes -> FETCH_INTERRUPTED kept -> UNABLE_TO_VERIFY
    body_holder["data"] = b"\x00\x01\x02\x03"
    q2 = orch.submit("https://files.example/doc.pdf")
    await orch.wait_for_running_scans()
    r2 = orch.store.get(str(q2.scan_id))
    assert r2 is not None
    assert r2.verdict == Verdict.UNABLE_TO_VERIFY
    assert "FETCH_INTERRUPTED" in [r.code for r in r2.reasons or []]


@pytest.mark.asyncio
async def test_full_scope_plain_zip_named_docx_refines_subtype_and_flags_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D75 and row 6: a full-scope plain ZIP named .docx is refined to 'zip' (CERTAIN) and
    flagged with TYPE_MISMATCH_OTHER (weight 15 -> SAFE)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", b"hello")
    zip_data = buf.getvalue()

    async def fake_fetch(url: str, settings: Settings, resolver: Any) -> FetchResult:
        return FetchResult(
            body_head=zip_data,
            bytes_read=len(zip_data),
            total_size=len(zip_data),
            range_supported=True,
            ended="complete",
            status_code=200,
            headers={
                "content-type": (
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
            },
            hops=[RedirectHop(url=url, status=200, address_class=AddressClass.public)],
            final_url=url,
            display_host="files.example",
            punycode_host="files.example",
        )

    monkeypatch.setattr("app.orchestrator.executor.fetch", fake_fetch)
    executor = InProcessExecutor(Settings(), resolver=FakeResolver({}))
    orch = make_orchestrator(tmp_path, executor)

    queued = orch.submit("https://files.example/report.docx")
    await orch.wait_for_running_scans()
    result = orch.store.get(str(queued.scan_id))
    assert result is not None
    assert result.verdict == Verdict.SAFE
    assert result.display_verdict == DisplayVerdict.SAFE
    assert result.file is not None and result.file.detected_type == "zip"
    assert "TYPE_MISMATCH_OTHER" in [r.code for r in result.reasons or []]
