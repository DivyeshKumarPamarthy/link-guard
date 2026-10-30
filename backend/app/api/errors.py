"""Every error leaves the API as an ErrorBody (spec §2) and never as a stack trace."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.validation import InputError
from app.contract.models import ErrorBody, ErrorCode, ErrorDetail
from app.core.log import safe
from app.orchestrator.scans import ServerBusyError

logger = logging.getLogger("linkguard.api")

INVALID_REQUEST_MESSAGE = 'Send JSON like {"url": "https://..."}.'
SERVER_BUSY_MESSAGE = "LinkGuard is checking other links. Try again in a few seconds."

# Plain HTTP errors raised by FastAPI/Starlette itself, mapped to our codes.
_HTTP_ERRORS = {
    404: (ErrorCode.NOT_FOUND, "Nothing here. The API is at /api/scans."),
    405: (ErrorCode.METHOD_NOT_ALLOWED, "This method is not allowed here."),
    413: (ErrorCode.REQUEST_TOO_LARGE, "The request is too large."),
}


def error_response(
    status_code: int, code: ErrorCode, message: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    body = ErrorBody(error=ErrorDetail(code=code, message=message))
    return JSONResponse(body.model_dump(mode="json"), status_code=status_code, headers=headers)


async def _input_error(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, InputError)
    return error_response(400, exc.code, exc.message)


async def _busy_error(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ServerBusyError)
    return error_response(
        503,
        ErrorCode.SERVER_BUSY,
        SERVER_BUSY_MESSAGE,
        headers={"Retry-After": str(exc.retry_after_s)},
    )


async def _validation_error(_request: Request, _exc: Exception) -> JSONResponse:
    # Malformed JSON or a non-string url. Pydantic's details stay out of the response.
    return error_response(400, ErrorCode.INVALID_REQUEST, INVALID_REQUEST_MESSAGE)


async def _http_error(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code, message = _HTTP_ERRORS.get(
        exc.status_code, (ErrorCode.INVALID_REQUEST, INVALID_REQUEST_MESSAGE)
    )
    headers = dict(exc.headers) if exc.headers else None
    return error_response(exc.status_code, code, message, headers=headers)


async def _unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
    # The exception text can contain remote data (URLs), so it goes through safe().
    logger.error("Unexpected error: %s: %s", type(exc).__name__, safe(exc))
    return error_response(
        500, ErrorCode.INTERNAL_ERROR, "Something went wrong on the LinkGuard server."
    )


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(InputError, _input_error)
    app.add_exception_handler(ServerBusyError, _busy_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unexpected_error)
