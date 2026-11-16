"""The one-command demo (`make demo`, task T4.2) must stay honest and local.

`demo/demo.env` switches on the SSRF exemptions the demo needs, so a typo there could either
break the demo or exempt more than the demo server. These tests load the file the same way
the backend does (as LG_* environment variables) and compare it with spec §11. They also
read `scripts/demo.sh` as text, like test_compose_ports.py reads docker-compose.yml: every
listener must stay on 127.0.0.1 (decision D18).
"""

import re
from pathlib import Path

import pytest

from app.core.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[3]
DEMO_ENV = REPO_ROOT / "demo" / "demo.env"
DEMO_SCRIPT = REPO_ROOT / "scripts" / "demo.sh"

DEMO_HOSTS = ("a.demo.test", "b.demo.test", "c.demo.test")
# Spec §11 and decision D34, written out in full (the spec's own list ends in "…"): HTTP 8081
# and HTTPS 8443 for all three names; the wrong-certificate listener 8444 for a.demo.test only.
SPEC_EXEMPTIONS = {(host, port) for host in DEMO_HOSTS for port in (8081, 8443)} | {
    ("a.demo.test", 8444)
}


def read_env_file(path: Path) -> dict[str, str]:
    """KEY=VALUE lines; blank lines and # comments are skipped (what `. file` does in sh)."""
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            name, _, value = line.partition("=")
            values[name] = value
    return values


@pytest.fixture
def demo_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    for name, value in read_env_file(DEMO_ENV).items():
        monkeypatch.setenv(name, value)
    return Settings()


def test_demo_env_sets_only_lg_variables() -> None:
    assert all(name.startswith("LG_") for name in read_env_file(DEMO_ENV))


def test_demo_env_is_the_spec_demo_profile(demo_settings: Settings) -> None:
    assert demo_settings.profile == "demo"
    assert demo_settings.static_hosts == dict.fromkeys(DEMO_HOSTS, "127.0.0.1")
    assert set(demo_settings.ssrf_exempt) == SPEC_EXEMPTIONS
    assert demo_settings.allowed_ports == (80, 443, 8081, 8443, 8444)
    assert demo_settings.extra_ca_bundle == "../demo/certs/test-ca.pem"


def test_demo_env_keeps_the_api_on_loopback(demo_settings: Settings) -> None:
    """The file must not move the API off 127.0.0.1 or change any other default."""
    assert demo_settings.bind_host == "127.0.0.1"
    assert set(read_env_file(DEMO_ENV)) == {
        "LG_PROFILE",
        "LG_STATIC_HOSTS",
        "LG_SSRF_EXEMPT",
        "LG_ALLOWED_PORTS",
        "LG_EXTRA_CA_BUNDLE",
    }


def test_demo_env_is_refused_outside_the_demo_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """The same exemptions with LG_PROFILE=dev must stop the backend from starting (D2)."""
    for name, value in read_env_file(DEMO_ENV).items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("LG_PROFILE", "dev")
    with pytest.raises(ValueError, match="only allowed in the test and demo profiles"):
        Settings()


def test_demo_script_listens_on_loopback_only() -> None:
    script = DEMO_SCRIPT.read_text(encoding="utf-8")
    assert "0.0.0.0" not in script
    assert re.findall(r"--host (\S+)", script) == ["127.0.0.1"]
    assert "docker compose" not in script  # the demo never starts containers


def test_demo_script_loads_the_demo_env_and_stays_offline() -> None:
    script = DEMO_SCRIPT.read_text(encoding="utf-8")
    assert ". demo/demo.env" in script
    assert "export UV_OFFLINE=1" in script
    assert "npm run dev:demo" in script  # the web app must show the demo links
