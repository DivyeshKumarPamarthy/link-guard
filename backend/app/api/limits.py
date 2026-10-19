"""Request body size limit: anything over LG_MAX_REQUEST_BYTES gets 413 (spec §2).

A real URL is at most 2 KB, so a large body is either a mistake or an attempt to make the
server buffer junk. Two checks: the declared Content-Length (cheap, before reading), and
the bytes actually received (for chunked bodies that declare no length).
"""

from fastapi import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.errors import error_response
from app.contract.models import ErrorCode

TOO_LARGE_MESSAGE = "The request is too large."


class BodySizeLimit:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_bytes:
            response = error_response(413, ErrorCode.REQUEST_TOO_LARGE, TOO_LARGE_MESSAGE)
            await response(scope, receive, send)
            return

        received = 0

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    # FastAPI re-raises HTTPException from body reading; our handler formats it.
                    raise HTTPException(status_code=413)
            return message

        await self.app(scope, counting_receive, send)
