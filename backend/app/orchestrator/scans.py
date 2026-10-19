"""Scan lifecycle: store a queued scan, run it in the background, store the result.

T0.7 version: one background asyncio task per scan, no concurrency limit yet.
T2.4 adds the semaphore, the busy guard (503), the overall timeout and the scorer.
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from app.contract.models import SCHEMA_VERSION, ScanResult, State
from app.core.log import safe
from app.db.models import ScanRow
from app.engine import ENGINE_VERSION
from app.orchestrator.mock_executor import Executor, ExecutorOutput
from app.registry.loader import Registry

logger = logging.getLogger("linkguard.orchestrator")


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
    def __init__(self, store: ScanStore, executor: Executor, registry: Registry) -> None:
        self.store = store
        self.executor = executor
        self.registry = registry
        # Keep a reference to each task: asyncio only keeps weak references to tasks.
        self._tasks: set[asyncio.Task[None]] = set()

    def submit(self, url: str) -> ScanResult:
        """Store the scan as queued and start it in the background. Returns immediately."""
        queued = self.store.create_queued(url)
        task = asyncio.create_task(self._run(queued))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return queued

    async def _run(self, queued: ScanResult) -> None:
        scan_id = str(queued.scan_id)
        self.store.mark_running(scan_id)
        try:
            output = await self.executor.run(queued.input_url)
            result = self._finish(queued, output)
        except Exception as exc:
            # Never leak details and never leave a scan stuck in "running". The exception
            # text may contain a URL with secrets, so it goes through safe() like any remote data.
            logger.error(
                "Scan %s failed for %s: %s: %s",
                scan_id,
                safe(queued.input_url),
                type(exc).__name__,
                safe(exc),
            )
            result = self._finish(queued, self._analysis_error_output())
        self.store.save_done(result)

    def _finish(self, queued: ScanResult, output: ExecutorOutput) -> ScanResult:
        """Merge executor output into the queued scan; validation enforces the contract."""
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
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
