"""Real-socket tests for the three listeners (task T1.1).

Some behaviour only exists on a real connection: a dropped connection, chunked transfer
encoding, a slow drip in real time, and TLS certificates. These tests start the demo server
on free loopback ports in a background thread.
"""

import socket
import ssl
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
import uvicorn

from demo_server.__main__ import build_servers
from demo_server.certs import CertPaths, cert_paths
from demo_server.config import DemoSettings


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


@dataclass
class RunningDemo:
    settings: DemoSettings
    certs: CertPaths
    servers: list[uvicorn.Server]


@pytest.fixture(scope="module")
def demo(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RunningDemo]:
    root = tmp_path_factory.mktemp("demo")
    (root / "samples").mkdir()
    settings = DemoSettings(
        http_port=free_port(),
        https_port=free_port(),
        wrong_cert_port=free_port(),
        samples_dir=root / "samples",
        certs_dir=root / "certs",
        slow_interval_s=0.2,
        slow_total_bytes=3,
    )
    servers = build_servers(settings)  # also generates the certificates
    for server in servers:
        server.config.log_level = "warning"
    threads = [threading.Thread(target=s.run, daemon=True) for s in servers]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + 10
    while not all(s.started for s in servers):
        if time.monotonic() > deadline:
            raise RuntimeError("demo listeners did not start")
        time.sleep(0.05)
    yield RunningDemo(settings, cert_paths(settings.certs_dir), servers)
    for server in servers:
        server.should_exit = True
    for thread in threads:
        thread.join(timeout=5)


def http(demo: RunningDemo) -> httpx.Client:
    return httpx.Client(base_url=f"http://127.0.0.1:{demo.settings.http_port}", trust_env=False)


def test_listeners_bind_to_loopback_only(demo: RunningDemo) -> None:
    """The demo server must never be reachable from other machines."""
    addresses = {
        sock.getsockname()[0]
        for server in demo.servers
        for listener in server.servers
        for sock in listener.sockets
    }
    assert addresses == {"127.0.0.1"}


def test_reset_drops_the_connection_after_4_kb(demo: RunningDemo) -> None:
    received = 0
    with http(demo) as client, pytest.raises(httpx.RemoteProtocolError):
        with client.stream("GET", "/reset") as r:
            assert r.headers["content-length"] == str(1024 * 1024)
            for chunk in r.iter_bytes():
                received += len(chunk)
    assert received == 4096


def test_chunked_uses_transfer_encoding(demo: RunningDemo) -> None:
    with http(demo) as client:
        r = client.get("/chunked")
    assert r.headers["transfer-encoding"] == "chunked"
    assert "content-length" not in r.headers


def test_slow_really_drips(demo: RunningDemo) -> None:
    start = time.monotonic()
    with http(demo) as client:
        r = client.get("/slow")
    assert len(r.content) == 3
    assert time.monotonic() - start >= 0.5  # 3 bytes x 0.2 s


def test_big_streams_200_mb_without_reading_it_all(demo: RunningDemo) -> None:
    with http(demo) as client, client.stream("GET", "/big?range=no") as r:
        assert r.headers["content-length"] == str(200 * 1024 * 1024)
        first = next(r.iter_bytes())
    assert first[4:8] == b"ftyp"


def tls_get(port: int, server_hostname: str, cafile: Path | None) -> str:
    """Open TLS to 127.0.0.1:port claiming `server_hostname`; return the HTTP status line."""
    context = ssl.create_default_context(cafile=str(cafile) if cafile else None)
    with socket.create_connection(("127.0.0.1", port), timeout=5) as raw:
        with context.wrap_socket(raw, server_hostname=server_hostname) as tls:
            request = f"GET /page HTTP/1.1\r\nHost: {server_hostname}\r\nConnection: close\r\n\r\n"
            tls.sendall(request.encode())
            return tls.recv(64).split(b"\r\n")[0].decode()


@pytest.mark.parametrize("host", ["a.demo.test", "b.demo.test", "c.demo.test"])
def test_https_listener_is_valid_for_demo_hosts(demo: RunningDemo, host: str) -> None:
    assert tls_get(demo.settings.https_port, host, demo.certs.ca) == "HTTP/1.1 200 OK"


def test_https_listener_is_refused_for_another_hostname(demo: RunningDemo) -> None:
    with pytest.raises(ssl.SSLCertVerificationError, match="Hostname mismatch"):
        tls_get(demo.settings.https_port, "evil.example", demo.certs.ca)


def test_wrong_cert_listener_is_refused_for_demo_host(demo: RunningDemo) -> None:
    """Row 22: a certificate for another host must fail hostname verification."""
    with pytest.raises(ssl.SSLCertVerificationError, match="Hostname mismatch"):
        tls_get(demo.settings.wrong_cert_port, "a.demo.test", demo.certs.ca)


def test_test_ca_is_not_trusted_by_default(demo: RunningDemo) -> None:
    """Without LG_EXTRA_CA_BUNDLE the system trust store must reject the demo certificate."""
    with pytest.raises(ssl.SSLCertVerificationError):
        tls_get(demo.settings.https_port, "a.demo.test", None)


def test_ca_private_key_is_never_written(demo: RunningDemo) -> None:
    names = sorted(p.name for p in demo.settings.certs_dir.iterdir())
    assert names == ["server.key", "server.pem", "test-ca.pem", "wrong-host.key", "wrong-host.pem"]
    assert (demo.settings.certs_dir / "server.key").stat().st_mode & 0o077 == 0
