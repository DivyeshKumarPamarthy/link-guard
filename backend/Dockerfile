# Backend image for docker-compose (make dev). Dependencies come from uv.lock, like make setup.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Use the image's Python 3.12; never download another one.
ENV UV_PYTHON_DOWNLOADS=never
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

COPY app ./app

# LG_BIND_HOST is set to 0.0.0.0 by docker-compose only (D31); compose publishes on 127.0.0.1.
CMD ["/app/.venv/bin/python", "-m", "app"]
