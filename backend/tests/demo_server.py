"""The real demo server for integration tests (decision D44).

Tests that request the `demo` fixture (tests/conftest.py) get the demo server started once
per test session as a subprocess on free loopback ports with a fresh test CA. Those tests
must be marked `integration` and `allow_hosts(["127.0.0.1"])`: sockets to anything else stay
blocked.
"""

import os
import socket
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings
from app.engine.fetcher.ip_literals import IPAddress
from app.engine.fetcher.resolver import StaticHostsResolver
from tests.ssrf.fakes import FakeResolver

DEMO_DIR = Path(__file__).resolve().parents[2] / "demo"
DEMO_NAMES = ("a.demo.test", "b.demo.test", "c.demo.test", "other.demo.test")
# other.demo.test maps to the demo server but is NOT in its certificate (T1.3 reuse test).


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


DEMO_START_TIMEOUT_S = 30  # generous for a cold `uv run` on a slow laptop


def wait_for_port(port: int, process: subprocess.Popen[bytes], log: Path) -> None:
    """Readiness check: the port accepts connections, or fail with the server's log."""
    deadline = time.monotonic() + DEMO_START_TIMEOUT_S
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"demo server exited early:\n{log.read_text()}")
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"demo server did not open port {port}:\n{log.read_text()}")


@dataclass(frozen=True)
class Demo:
    http_port: int
    https_port: int
    wrong_cert_port: int
    ca: Path

    def settings(self) -> Settings:
        """Test profile with the demo exemption (D2) for every demo name on every port."""
        ports = (self.http_port, self.https_port, self.wrong_cert_port)
        return Settings(
            profile="test",
            static_hosts={name: "127.0.0.1" for name in DEMO_NAMES},
            ssrf_exempt=tuple((name, port) for name in DEMO_NAMES for port in ports),
            allowed_ports=(80, 443, *ports),
            extra_ca_bundle=str(self.ca),
        )


def run_demo_server(root: Path) -> Iterator[Demo]:
    """Start the real demo server (demo/) as a subprocess on free loopback ports, with a
    fresh test CA in `root`, wait until every port answers, and stop it afterwards.
    Used by the session-scoped `demo` fixture in tests/conftest.py."""
    ports = {"HTTP": free_port(), "HTTPS": free_port(), "WRONG_CERT": free_port()}
    env = {
        **os.environ,
        **{f"DEMO_{name}_PORT": str(port) for name, port in ports.items()},
        "DEMO_CERTS_DIR": str(root / "certs"),
        "DEMO_SAMPLES_DIR": str(root),
    }
    log = root / "demo-server.log"
    with log.open("wb") as out:
        process = subprocess.Popen(
            ["uv", "run", "--locked", "--directory", str(DEMO_DIR), "python", "-m", "demo_server"],
            env=env,
            stdout=out,
            stderr=subprocess.STDOUT,
        )
    try:
        for port in ports.values():
            wait_for_port(port, process, log)
        yield Demo(
            ports["HTTP"], ports["HTTPS"], ports["WRONG_CERT"], root / "certs" / "test-ca.pem"
        )
    finally:
        process.terminate()
        process.wait(timeout=10)


class RecordingResolver(StaticHostsResolver):
    """The static demo names, recording every lookup (to prove: exactly one per hop)."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings.static_hosts, fallback=FakeResolver({}))
        self.calls: list[str] = []

    def resolve(self, host: str) -> list[IPAddress]:
        self.calls.append(host)
        return super().resolve(host)
