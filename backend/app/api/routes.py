"""The two endpoints of contract v1 (spec §2). There is no list or history endpoint (D17)."""

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.api.validation import check_submission
from app.contract.models import ErrorBody, ScanAccepted, ScanRequest, ScanResult
from app.core.config import Settings
from app.orchestrator.scans import Orchestrator

router = APIRouter(prefix="/api")

_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {
        "model": ErrorBody,
        "description": "URL_EMPTY, URL_TOO_LONG, URL_MULTIPLE or INVALID_REQUEST",
    },
    413: {"model": ErrorBody, "description": "Request body over the size limit"},
    500: {"model": ErrorBody, "description": "INTERNAL_ERROR (never a stack trace)"},
}


@router.post(
    "/scans",
    status_code=202,
    response_model=ScanAccepted,
    responses={**_ERRORS, 503: {"model": ErrorBody, "description": "SERVER_BUSY (T2.4)"}},
)
async def create_scan(payload: ScanRequest, request: Request) -> JSONResponse:
    """Submit a link. Returns at once with a scan_id; poll GET /api/scans/{scan_id}."""
    settings: Settings = request.app.state.settings
    orchestrator: Orchestrator = request.app.state.orchestrator
    url = check_submission(payload.url, settings.max_url_length)
    queued = orchestrator.submit(url)
    accepted = ScanAccepted(
        scan_id=queued.scan_id, state=queued.state, poll_after_ms=settings.poll_after_ms
    )
    return JSONResponse(accepted.model_dump(mode="json"), status_code=202)


@router.get(
    "/scans/{scan_id}",
    response_model=ScanResult,
    responses={404: {"model": ErrorBody, "description": "Unknown scan_id"}, 500: _ERRORS[500]},
)
def get_scan(scan_id: str, request: Request) -> ScanResult:
    """Poll one scan. Outcome fields stay null until state is "done"."""
    try:
        canonical_id = str(uuid.UUID(scan_id))
    except ValueError:
        raise HTTPException(status_code=404) from None
    result = request.app.state.orchestrator.store.get(canonical_id)
    if result is None:
        raise HTTPException(status_code=404)
    return result  # type: ignore[no-any-return]
