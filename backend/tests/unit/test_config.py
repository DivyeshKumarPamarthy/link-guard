"""Tests for configuration profiles (task T0.2, spec §4 and §11)."""

import logging

import pytest
from pydantic import ValidationError

from app.core.config import Settings, log_active_exemptions

DEMO_ENV = {
    "LG_STATIC_HOSTS": "a.demo.test=127.0.0.1,b.demo.test=127.0.0.1,c.demo.test=127.0.0.1",
    "LG_SSRF_EXEMPT": "a.demo.test:8081,b.demo.test:8081,a.demo.test:8443",
    "LG_EXTRA_CA_BUNDLE": "demo/certs/test-ca.pem",
}


def test_defaults_match_spec() -> None:
    s = Settings()
    assert s.profile == "dev"
    assert s.head_fetch_bytes == 5_242_880
    assert s.connect_timeout_s == 5
    assert s.total_deadline_s == 20
    assert s.min_throughput_bps == 1024
    assert s.max_redirects == 5
    assert s.long_chain_hops == 3
    assert s.allowed_ports == (80, 443)
    assert s.max_url_length == 2048
    assert s.max_concurrent_scans == 4
    assert s.max_waiting_scans == 20
    assert s.bind_host == "127.0.0.1"
    assert s.cors_origins == ("*",)
    assert s.database_url == "sqlite:///./linkguard.db"
    assert s.user_agent == "LinkGuard/1.0 (link safety checker)"
    assert s.static_hosts == {}
    assert s.ssrf_exempt == ()
    assert s.extra_ca_bundle is None


def test_defaults_added_by_decision_d23() -> None:
    s = Settings()
    assert s.api_port == 8000
    assert s.max_request_bytes == 8192
    assert s.poll_after_ms == 500
    assert s.mock_delay_ms == 300


def test_env_overrides_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LG_HEAD_FETCH_BYTES", "1000")
    monkeypatch.setenv("LG_ALLOWED_PORTS", "80, 443 ,8081")
    monkeypatch.setenv("LG_CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173")
    monkeypatch.setenv("LG_PROFILE", "prod")
    s = Settings()
    assert s.head_fetch_bytes == 1000
    assert s.allowed_ports == (80, 443, 8081)
    assert s.cors_origins == ("http://127.0.0.1:5173", "http://localhost:5173")
    assert s.profile == "prod"


def test_unknown_profile_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LG_PROFILE", "staging")
    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize("value", ["0", "70000", "http"])
def test_invalid_port_is_refused(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("LG_ALLOWED_PORTS", f"80,{value}")
    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize("value", ["0", "-1"])
def test_non_positive_cap_is_refused(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("LG_HEAD_FETCH_BYTES", value)
    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize("profile", ["test", "demo"])
def test_exemptions_parse_in_test_and_demo(monkeypatch: pytest.MonkeyPatch, profile: str) -> None:
    monkeypatch.setenv("LG_PROFILE", profile)
    for name, value in DEMO_ENV.items():
        monkeypatch.setenv(name, value)
    s = Settings()
    assert s.static_hosts == {
        "a.demo.test": "127.0.0.1",
        "b.demo.test": "127.0.0.1",
        "c.demo.test": "127.0.0.1",
    }
    assert s.ssrf_exempt == (("a.demo.test", 8081), ("b.demo.test", 8081), ("a.demo.test", 8443))
    assert s.extra_ca_bundle == "demo/certs/test-ca.pem"


@pytest.mark.parametrize("profile", ["dev", "prod"])
@pytest.mark.parametrize("name", sorted(DEMO_ENV))
def test_profile_guard_refuses_exemptions_in_dev_and_prod(
    monkeypatch: pytest.MonkeyPatch, profile: str, name: str
) -> None:
    """Spec §4: startup MUST fail if any test/demo-only setting is present in dev or prod."""
    monkeypatch.setenv("LG_PROFILE", profile)
    monkeypatch.setenv(name, DEMO_ENV[name])
    with pytest.raises(ValidationError, match="only allowed in the test and demo profiles"):
        Settings()


def test_prod_refuses_the_full_demo_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Spec §11: a test asserts the prod profile rejects all of the demo settings together."""
    monkeypatch.setenv("LG_PROFILE", "prod")
    for name, value in DEMO_ENV.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        Settings()


def test_empty_exemption_variables_count_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LG_PROFILE", "prod")
    for name in DEMO_ENV:
        monkeypatch.setenv(name, "")
    s = Settings()
    assert s.static_hosts == {}
    assert s.ssrf_exempt == ()
    assert s.extra_ca_bundle is None


@pytest.mark.parametrize("value", ["a.demo.test", "a.demo.test=not-an-ip", "=127.0.0.1"])
def test_malformed_static_hosts_are_refused(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("LG_PROFILE", "test")
    monkeypatch.setenv("LG_STATIC_HOSTS", value)
    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize("value", ["a.demo.test", "a.demo.test:abc", ":8081", "a.demo.test:0"])
def test_malformed_exemptions_are_refused(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("LG_PROFILE", "test")
    monkeypatch.setenv("LG_SSRF_EXEMPT", value)
    with pytest.raises(ValidationError):
        Settings()


def test_exemption_hosts_are_lowercased(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LG_PROFILE", "test")
    monkeypatch.setenv("LG_STATIC_HOSTS", "A.Demo.Test=127.0.0.1")
    monkeypatch.setenv("LG_SSRF_EXEMPT", "A.Demo.Test:8081")
    s = Settings()
    assert s.static_hosts == {"a.demo.test": "127.0.0.1"}
    assert s.ssrf_exempt == (("a.demo.test", 8081),)


def test_active_exemptions_are_logged_as_warnings(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("LG_PROFILE", "test")
    for name, value in DEMO_ENV.items():
        monkeypatch.setenv(name, value)
    with caplog.at_level(logging.WARNING):
        log_active_exemptions(Settings())
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("a.demo.test=127.0.0.1" in m for m in warnings)
    assert any("a.demo.test:8443" in m for m in warnings)
    assert any("demo/certs/test-ca.pem" in m for m in warnings)
    # one line per exemption: 3 static hosts + 3 exempt host:port pairs + 1 CA bundle
    assert len(warnings) == 7


def test_no_warnings_without_exemptions(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        log_active_exemptions(Settings())
    assert caplog.records == []
