"""Build the FastAPI app: settings, registry, database, orchestrator, middleware, routes.

Everything is created inside create_app() rather than at import time, so tests can build an
app with their own settings and a temporary database.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.api.errors import install_error_handlers
from app.api.limits import BodySizeLimit
from app.api.routes import router
from app.core.config import (
    Settings,
    get_settings,
    log_active_exemptions,
    log_active_thresholds,
)
from app.db.models import make_engine, make_session_factory
from app.engine import ENGINE_VERSION
from app.orchestrator.executor import InProcessExecutor
from app.orchestrator.mock_executor import Executor, MockExecutor
from app.orchestrator.scans import Orchestrator, ScanStore
from app.registry.loader import get_registry


def _openapi_without_422(app: FastAPI) -> dict[str, Any]:
    """FastAPI documents a 422 response by default, but this API turns every validation
    error into a 400 ErrorBody (spec §2). Remove 422 so the web types match reality."""
    if app.openapi_schema is None:
        document = get_openapi(
            title=app.title, version=app.version, summary=app.summary, routes=app.routes
        )
        for operations in document["paths"].values():
            for operation in operations.values():
                operation["responses"].pop("422", None)
        for unused in ("HTTPValidationError", "ValidationError"):
            document["components"]["schemas"].pop(unused, None)
        app.openapi_schema = document
    return app.openapi_schema


def build_executor(settings: Settings) -> Executor:
    """Select the real in-process executor or the mock one from config alone (T2.4)."""
    if settings.executor == "mock":
        return MockExecutor(settings.mock_delay_ms)
    return InProcessExecutor(settings)


def create_app(settings: Settings | None = None, executor: Executor | None = None) -> FastAPI:
    settings = settings or get_settings()
    registry = get_registry()  # fails startup if the registry is invalid
    log_active_exemptions(settings)
    log_active_thresholds(settings)

    store = ScanStore(
        make_session_factory(make_engine(settings.database_url)), registry.rules_version
    )
    active_executor = executor or build_executor(settings)
    orchestrator = Orchestrator(store, active_executor, registry, settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        await orchestrator.wait_for_running_scans()

    app = FastAPI(
        title="LinkGuard API",
        version=ENGINE_VERSION,
        summary="Checks a download link before you download it.",
        lifespan=lifespan,
    )
    app.openapi = lambda: _openapi_without_422(app)  # type: ignore[method-assign]
    app.state.settings = settings
    app.state.orchestrator = orchestrator

    install_error_handlers(app)
    app.include_router(router)
    # Added last = outermost, so even 413 responses carry CORS headers the browser can read.
    app.add_middleware(BodySizeLimit, max_bytes=settings.max_request_bytes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,  # always: the API is anonymous (D17)
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        expose_headers=["Retry-After"],
    )
    return app
