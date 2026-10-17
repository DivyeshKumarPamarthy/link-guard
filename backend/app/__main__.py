"""Run the API: `uv run python -m app` (from backend/).

The host comes from LG_BIND_HOST, which defaults to 127.0.0.1: the backend is anonymous and
must never listen on a public interface (decision D18).
"""

import uvicorn

from app.core.config import Settings, get_settings
from app.core.log import setup_logging
from app.main import create_app


def server_options(settings: Settings) -> dict[str, str | int]:
    return {"host": settings.bind_host, "port": settings.api_port}


def main() -> None:
    setup_logging()
    settings = get_settings()
    uvicorn.run(create_app(settings), **server_options(settings))  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
