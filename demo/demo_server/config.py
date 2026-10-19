"""Demo server settings from DEMO_* environment variables.

Timings and sizes are configurable so tests can run fast and slow laptops can use
generous values (plan M7: "timeout tests are flaky on slow laptops").
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def _path(name: str, default: Path) -> Path:
    return Path(os.environ.get(name, str(default)))


@dataclass(frozen=True)
class DemoSettings:
    bind_host: str = "127.0.0.1"  # loopback only, like the backend (D18)
    http_port: int = 8081
    https_port: int = 8443
    wrong_cert_port: int = 8444  # HTTPS with a certificate for another host (row 22, D34)
    samples_dir: Path = REPO_ROOT / "samples"
    certs_dir: Path = REPO_ROOT / "demo" / "certs"
    # Hostnames the backend maps to 127.0.0.1 with LG_STATIC_HOSTS; redirect chains walk them.
    chain_hosts: tuple[str, ...] = ("a.demo.test", "b.demo.test", "c.demo.test")
    wrong_cert_host: str = "wrong-host.example"
    big_size_bytes: int = 200 * 1024 * 1024
    slow_interval_s: float = 2.0
    slow_total_bytes: int = 64
    reset_after_bytes: int = 4096
    reset_declared_bytes: int = 1024 * 1024
    retry_after_s: int = 1
    max_chain_hops: int = field(default=10)


def load_settings() -> DemoSettings:
    """Read DEMO_* variables; anything unset keeps its default."""
    defaults = DemoSettings()
    return DemoSettings(
        bind_host=os.environ.get("DEMO_BIND_HOST", defaults.bind_host),
        http_port=_int("DEMO_HTTP_PORT", defaults.http_port),
        https_port=_int("DEMO_HTTPS_PORT", defaults.https_port),
        wrong_cert_port=_int("DEMO_WRONG_CERT_PORT", defaults.wrong_cert_port),
        samples_dir=_path("DEMO_SAMPLES_DIR", defaults.samples_dir),
        certs_dir=_path("DEMO_CERTS_DIR", defaults.certs_dir),
        big_size_bytes=_int("DEMO_BIG_SIZE_BYTES", defaults.big_size_bytes),
        slow_interval_s=_float("DEMO_SLOW_INTERVAL_S", defaults.slow_interval_s),
        slow_total_bytes=_int("DEMO_SLOW_TOTAL_BYTES", defaults.slow_total_bytes),
        reset_after_bytes=_int("DEMO_RESET_AFTER_BYTES", defaults.reset_after_bytes),
        reset_declared_bytes=_int("DEMO_RESET_DECLARED_BYTES", defaults.reset_declared_bytes),
        retry_after_s=_int("DEMO_RETRY_AFTER_S", defaults.retry_after_s),
    )
