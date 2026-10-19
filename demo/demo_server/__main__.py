"""Run the demo server: `uv run python -m demo_server` (from demo/).

Starts three listeners on 127.0.0.1 serving the same endpoints:
  HTTP   :8081  plain
  HTTPS  :8443  certificate valid for a/b/c.demo.test (signed by the local test CA)
  HTTPS  :8444  certificate for another host, so clients must refuse it (row 22)
Certificates are generated into demo/certs/ on first start.
"""

import asyncio
import logging

import uvicorn

from demo_server.app import create_app
from demo_server.certs import cert_paths, generate_certs
from demo_server.config import DemoSettings, load_settings

logger = logging.getLogger("demo_server")


def build_servers(settings: DemoSettings) -> list[uvicorn.Server]:
    paths = cert_paths(settings.certs_dir)
    if not paths.all_exist():
        logger.warning("Generating a local test CA and certificates in %s", settings.certs_dir)
        paths = generate_certs(settings.certs_dir, settings.chain_hosts, settings.wrong_cert_host)

    app = create_app(settings)
    configs = [
        uvicorn.Config(app, host=settings.bind_host, port=settings.http_port, log_level="info"),
        uvicorn.Config(
            app,
            host=settings.bind_host,
            port=settings.https_port,
            log_level="info",
            ssl_certfile=str(paths.server_cert),
            ssl_keyfile=str(paths.server_key),
        ),
        uvicorn.Config(
            app,
            host=settings.bind_host,
            port=settings.wrong_cert_port,
            log_level="info",
            ssl_certfile=str(paths.wrong_host_cert),
            ssl_keyfile=str(paths.wrong_host_key),
        ),
    ]
    return [uvicorn.Server(config) for config in configs]


async def serve_all(servers: list[uvicorn.Server]) -> None:
    await asyncio.gather(*(server.serve() for server in servers))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = load_settings()
    asyncio.run(serve_all(build_servers(settings)))


if __name__ == "__main__":
    main()
