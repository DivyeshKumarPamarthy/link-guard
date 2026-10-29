"""Scan lifecycle: store a queued scan, run it in the background, score and store the result.

Task T2.4 (spec §2, §3, §9, §13, decisions D17, D29, D62–D66):
- Concurrency gated by `asyncio.Semaphore(LG_MAX_CONCURRENT_SCANS)`.
- When more than `LG_MAX_WAITING_SCANS` are already waiting for a slot, `submit()` raises
  `ServerBusyError`, which the API returns as `503 SERVER_BUSY` with `Retry-After`.
- State transitions (`queued` -> `running` -> `done`) are persisted to SQLite.
- Raw executor output (`RawScanReport`) is validated before scoring, then scored by the pure
  `score_scan()` function, and validated again against `ScanResult`.
- Any timeout, exception or invalid executor output becomes `UNABLE_TO_VERIFY` with
  `ANALYSIS_ERROR` (never `SAFE`, and no internal details leak).
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from app.contract.models import SCHEMA_VERSION, ScanResult, State
from app.core.config import Settings, get_settings
from app.core.log import safe
from app.db.models import ScanRow
from app.engine import ENGINE_VERSION
from app.engine.scoring.scorer import Thresholds, log_unknown_codes, score_scan
from app.orchestrator.executor import RawScanReport
from app.orchestrator.mock_executor import Executor, ExecutorOutput
from app.registry.loader import Registry

logger = logging.getLogger("linkguard.orchestrator")


class ServerBusyError(Exception):
    """More than `LG_MAX_WAITING_SCANS` are already waiting for a concurrency slot."""

    def __init__(self, retry_after_s: int = 5) -> None:
        super().__init__("LinkGuard is checking other links. Try again in a few seconds.")
        self.retry_after_s = retry_after_s


def _now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; every time we store is UTC."""
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


class ScanStore:
    """Reads and writes scan rows. Each call is one short transaction."""

    def __init__(self, session_factory: sessionmaker[Session], rules_version: str) -> None:
        self.session_factory = session_factory
        self.rules_version = rules_version

    def create_queued(self, input_url: str) -> ScanResult:
        row = ScanRow(
            id=str(uuid.uuid4()),
            state=State.queued.value,
            input_url=input_url,
            schema_version=SCHEMA_VERSION,
            engine_version=ENGINE_VERSION,
            rules_version=self.rules_version,
            created_at=_now(),
        )
        with self.session_factory() as session:
            session.add(row)
            session.commit()
        return self._to_result(row)

    def mark_running(self, scan_id: str) -> None:
        with self.session_factory() as session:
            row = session.get(ScanRow, scan_id)
            if row is not None:
                row.state = State.running.value
                session.commit()

    def save_done(self, result: ScanResult) -> None:
        with self.session_factory() as session:
            row = session.get(ScanRow, str(result.scan_id))
            if row is None:
                return
            row.state = State.done.value
            row.status = result.status.value if result.status else None
            row.verdict = result.verdict.value if result.verdict else None
            row.display_verdict = result.display_verdict.value if result.display_verdict else None
            row.final_url = result.final_url
            row.completed_at = result.completed_at
            row.result_json = result.model_dump_json()
            session.commit()

    def get(self, scan_id: str) -> ScanResult | None:
        with self.session_factory() as session:
            row = session.get(ScanRow, scan_id)
            return None if row is None else self._to_result(row)

    def _to_result(self, row: ScanRow) -> ScanResult:
        if row.result_json is not None:
            return ScanResult.model_validate_json(row.result_json)
        return ScanResult(
            scan_id=uuid.UUID(row.id),
            state=State(row.state),
            input_url=row.input_url,
            engine_version=row.engine_version,
            rules_version=row.rules_version,
            created_at=_as_utc(row.created_at) or _now(),
        )


class Orchestrator:
    def __init__(
        self,
        store: ScanStore,
        executor: Executor,
        registry: Registry,
        settings: Settings | None = None,
    ) -> None:
        self.store = store
        self.executor = executor
        self.registry = registry
        self.settings = settings or get_settings()
        self.thresholds = Thresholds.from_settings(self.settings)
        self.max_concurrent_scans = self.settings.max_concurrent_scans
        self.max_waiting_scans = self.settings.max_waiting_scans
        self.retry_after_s = self.settings.busy_retry_after_s
        # Spec §13: every scan terminates within LG_TOTAL_DEADLINE_S + 2 s.
        # Give the fetcher's inner deadline a small grace window so FETCH_TIMEOUT wins over
        # cancelling the whole executor, while still cutting off a wedged executor quickly.
        self.timeout_s = self.settings.total_deadline_s + min(
            2.0, self.settings.total_deadline_s * 0.5
        )
        self._semaphore = asyncio.Semaphore(self.max_concurrent_scans)
        self._in_flight = 0
        # Keep a reference to each task: asyncio only keeps weak references to tasks.
        self._tasks: set[asyncio.Task[None]] = set()

    @property
    def waiting_count(self) -> int:
        """How many accepted scans are waiting to acquire the concurrency semaphore."""
        return max(0, self._in_flight - self.max_concurrent_scans)

    def submit(self, url: str) -> ScanResult:
        """Store the scan as queued and start it in the background, or raise ServerBusyError."""
        if self.waiting_count >= self.max_waiting_scans:
            raise ServerBusyError(self.retry_after_s)
        queued = self.store.create_queued(url)
        self._in_flight += 1
        task = asyncio.create_task(self._run(queued))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return queued

    async def _run(self, queued: ScanResult) -> None:
        scan_id = str(queued.scan_id)
        try:
            async with self._semaphore:
                self.store.mark_running(scan_id)
                try:
                    async with asyncio.timeout(self.timeout_s):
                        output = await self.executor.run(queued.input_url)
                    result = self._finish(queued, output)
                except Exception as exc:
                    # Never leak details and never leave a scan stuck in "running". The
                    # exception text may contain a URL with secrets, so it goes through safe().
                    logger.error(
                        "Scan %s failed for %s: %s: %s",
                        scan_id,
                        safe(queued.input_url),
                        type(exc).__name__,
                        safe(exc),
                    )
                    result = self._finish_scored(queued, self._analysis_error_output())
                self.store.save_done(result)
                logger.info(
                    "Scan %s finished (%s) for %s",
                    scan_id,
                    safe(result.display_verdict.value if result.display_verdict else "unknown"),
                    safe(queued.input_url),
                )
        finally:
            self._in_flight -= 1

    def _finish(self, queued: ScanResult, output: ExecutorOutput) -> ScanResult:
        """Validate executor output, run the pure scorer if raw findings were returned, and
        enforce the ScanResult contract."""
        if "findings" in output or "read" in output:
            raw = RawScanReport.model_validate(output)
            findings = [item.to_finding() for item in raw.findings]
            read_facts = raw.read.to_read_facts()
            outcome = score_scan(findings, read_facts, self.registry, self.thresholds)
            log_unknown_codes(outcome, logger)
            scored: ExecutorOutput = {
                "status": outcome.status.value,
                "normalized_url": raw.normalized_url,
                "final_url": raw.final_url,
                "display_host": raw.display_host,
                "punycode_host": raw.punycode_host,
                "link_type": raw.link_type.value,
                "verdict": outcome.verdict.value if outcome.verdict else None,
                "display_verdict": outcome.display_verdict.value,
                "score": outcome.score,
                "confidence": outcome.confidence.value if outcome.confidence else None,
                "scope": outcome.scope.model_dump(mode="json"),
                "headline": outcome.headline,
                "file": raw.file.model_dump(mode="json") if raw.file else None,
                "redirects": [hop.model_dump(mode="json") for hop in raw.redirects],
                "reasons": [reason.model_dump(mode="json") for reason in outcome.reasons],
                "unavailable_signals": list(raw.unavailable_signals),
                "timings_ms": dict(raw.timings_ms),
            }
            return self._finish_scored(queued, scored)
        return self._finish_scored(queued, output)

    def _finish_scored(self, queued: ScanResult, output: ExecutorOutput) -> ScanResult:
        """Merge scored output into the queued scan; validation enforces the contract."""
        data = queued.model_dump(mode="json")
        data.update(output)
        data.update(state=State.done.value, completed_at=_now().isoformat())
        return ScanResult.model_validate(data)

    def _analysis_error_output(self) -> ExecutorOutput:
        entry = self.registry.codes["ANALYSIS_ERROR"]
        return {
            "status": "completed",
            "verdict": "UNABLE_TO_VERIFY",
            "display_verdict": "UNABLE_TO_VERIFY",
            "score": 0,
            "confidence": "low",
            "scope": {
                "mode": "none",
                "bytes_analyzed": 0,
                "total_bytes": None,
                "range_supported": False,
                "label": "Nothing was read",
            },
            "headline": entry.headline,
            "reasons": [
                {
                    "code": "ANALYSIS_ERROR",
                    "severity": entry.severity.value,
                    "weight": entry.weight,
                    "group": entry.group,
                    "message": entry.message,
                    "evidence": {},
                }
            ],
        }

    async def wait_for_running_scans(self) -> None:
        """Used at shutdown and in tests: let in-flight scans finish."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)
