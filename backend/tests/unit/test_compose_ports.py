"""docker-compose may publish ports on 127.0.0.1 only (D18, D31, task T2.5).

The backend is anonymous, has open CORS and no rate limits (D17). A bare `8000:8000` in
docker-compose publishes on every interface of the host, so anyone on the same Wi-Fi could
use the backend to make requests. This test reads the compose file and fails on any port
that is not published as `127.0.0.1:<host port>:<container port>`.
"""

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
COMPOSE_FILE = REPO / "docker-compose.yml"
LOOPBACK_PREFIX = "127.0.0.1:"
# Ports each service must publish (CLAUDE.md "make dev")
EXPECTED_PORTS = {
    "api": ["127.0.0.1:8000:8000"],
    "web": ["127.0.0.1:5173:5173"],
    "demo": ["127.0.0.1:8081:8081", "127.0.0.1:8443:8443", "127.0.0.1:8444:8444"],
}


def unsafe_ports(compose: dict[str, Any]) -> list[str]:
    """Every published port in a compose file that is not bound to 127.0.0.1.

    Handles the three forms compose accepts: a string (`"127.0.0.1:8000:8000"`), a bare number
    (`8000`, which means all interfaces) and the long form (`{published: 8000, host_ip: ...}`).
    `network_mode: host` is refused too: it skips port publishing and exposes every listener.
    """
    problems = []
    for name, service in (compose.get("services") or {}).items():
        if service.get("network_mode") == "host":
            problems.append(f"{name}: network_mode host")
        for port in service.get("ports") or []:
            if isinstance(port, dict):
                if port.get("host_ip") != "127.0.0.1":
                    problems.append(f"{name}: {port}")
            elif not str(port).startswith(LOOPBACK_PREFIX):
                problems.append(f"{name}: {port}")
    return problems


def load_compose() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
    return loaded


def test_compose_publishes_ports_on_loopback_only() -> None:
    assert unsafe_ports(load_compose()) == []


def test_compose_publishes_the_expected_ports() -> None:
    services = load_compose()["services"]
    assert {name: services[name].get("ports") for name in services} == EXPECTED_PORTS


def test_containers_listen_on_all_interfaces_inside_docker() -> None:
    """D31: a published port only reaches a process listening on the container's own
    interface, so inside Docker the servers bind 0.0.0.0. The host side stays loopback."""
    services = load_compose()["services"]
    assert services["api"]["environment"]["LG_BIND_HOST"] == "0.0.0.0"
    assert services["demo"]["environment"]["DEMO_BIND_HOST"] == "0.0.0.0"
    assert "0.0.0.0" in services["web"]["command"]


@pytest.mark.parametrize(
    "ports",
    [
        ["8000:8000"],  # all interfaces
        ["0.0.0.0:8000:8000"],
        ["8000"],  # random host port on all interfaces
        [8000],  # YAML number, not a string
        ["127.0.0.10:8000:8000"],  # another loopback-looking address
        ["[::]:8000:8000"],
        [{"target": 8000, "published": 8000}],  # long form, no host_ip = all interfaces
        [{"target": 8000, "published": 8000, "host_ip": "0.0.0.0"}],
        ["127.0.0.1:8000:8000", "8443:8443"],  # one bad port among good ones
    ],
)
def test_checker_rejects_ports_not_on_loopback(ports: list[object]) -> None:
    assert unsafe_ports({"services": {"api": {"ports": ports}}}) != []


@pytest.mark.parametrize(
    "ports",
    [
        ["127.0.0.1:8000:8000"],
        ["127.0.0.1:8081:8081", "127.0.0.1:8443:8443"],
        [{"target": 8000, "published": 8000, "host_ip": "127.0.0.1"}],
    ],
)
def test_checker_accepts_loopback_ports(ports: list[object]) -> None:
    assert unsafe_ports({"services": {"api": {"ports": ports}}}) == []


def test_checker_rejects_host_networking() -> None:
    assert unsafe_ports({"services": {"api": {"network_mode": "host"}}}) != []


def test_checker_checks_every_service() -> None:
    compose = {"services": {"api": {"ports": ["127.0.0.1:8000:8000"]}, "web": {"ports": ["80:80"]}}}
    assert unsafe_ports(compose) == ["web: 80:80"]
