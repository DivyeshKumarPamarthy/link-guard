# Demo server image for docker-compose (make dev). Dependencies come from uv.lock.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Use the image's Python 3.12; never download another one.
ENV UV_PYTHON_DOWNLOADS=never
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

COPY demo_server ./demo_server

# DEMO_BIND_HOST is set to 0.0.0.0 by docker-compose only (D31); compose publishes on 127.0.0.1.
# The test CA and certificates are generated into DEMO_CERTS_DIR on first start.
CMD ["/app/.venv/bin/python", "-m", "demo_server"]
