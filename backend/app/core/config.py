"""Configuration from LG_* environment variables (spec §4).

Every tunable number lives here, so no cap, timeout or port is hard-coded elsewhere.
The profile guard exists because the demo needs to reach loopback addresses: those
exemptions must be impossible to switch on in dev or prod (decision D2).
"""

import ipaddress
import logging
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

logger = logging.getLogger("linkguard.config")

Profile = Literal["dev", "test", "demo", "prod"]
ExecutorKind = Literal["inprocess", "mock"]
EXEMPTION_PROFILES = ("test", "demo")


def _split_list(value: object) -> object:
    """Turn "a, b,c" into ["a", "b", "c"]; an empty string means an empty list."""
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LG_", frozen=True)

    profile: Profile = "dev"
    executor: ExecutorKind = "inprocess"

    # Fetcher limits
    head_fetch_bytes: int = Field(5_242_880, gt=0)
    connect_timeout_s: float = Field(5, gt=0)
    total_deadline_s: float = Field(20, gt=0)
    min_throughput_bps: int = Field(1024, ge=0)
    min_throughput_grace_s: float = Field(5, ge=0)  # C1: throughput checked after this
    max_retry_after_s: int = Field(5, ge=0)  # a 429 is retried once only if it asks <= this
    max_redirects: int = Field(5, ge=0)
    long_chain_hops: int = Field(3, ge=0)
    allowed_ports: Annotated[tuple[int, ...], NoDecode] = (80, 443)
    max_url_length: int = Field(2048, gt=0)
    user_agent: str = "LinkGuard/1.0 (link safety checker)"

    # Scan capacity (decision D17: semaphore + busy guard instead of rate limits)
    max_concurrent_scans: int = Field(4, gt=0)
    max_waiting_scans: int = Field(20, ge=0)
    busy_retry_after_s: int = Field(5, gt=0)  # Retry-After header on 503 SERVER_BUSY (D23)

    # API and storage
    bind_host: str = "127.0.0.1"
    cors_origins: Annotated[tuple[str, ...], NoDecode] = ("*",)
    database_url: str = "sqlite:///./linkguard.db"

    # Added by decision D23 (not in spec §4, but tunable numbers must come from config)
    api_port: int = Field(8000, gt=0, le=65535)
    max_request_bytes: int = Field(8192, gt=0)
    poll_after_ms: int = Field(500, gt=0)
    mock_delay_ms: int = Field(300, ge=0)

    # File-type detection (T1.5; spec §7 names the rules but not these numbers)
    zip_max_entries: int = Field(10_000, gt=0)
    text_sample_bytes: int = Field(4096, gt=0)
    text_min_printable_ratio: float = Field(0.95, gt=0, le=1)

    # Verdict thresholds (spec §9: 30 is SUSPICIOUS, 60 is UNSAFE; both inclusive)
    suspicious_score: int = Field(30, gt=0, le=100)
    unsafe_score: int = Field(60, gt=0, le=100)

    # test / demo profiles only (decision D2)
    static_hosts: Annotated[dict[str, str], NoDecode] = {}
    ssrf_exempt: Annotated[tuple[tuple[str, int], ...], NoDecode] = ()
    extra_ca_bundle: str | None = None

    @field_validator("allowed_ports", "cors_origins", mode="before")
    @classmethod
    def _parse_comma_list(cls, value: object) -> object:
        return _split_list(value)

    @field_validator("allowed_ports")
    @classmethod
    def _check_ports(cls, ports: tuple[int, ...]) -> tuple[int, ...]:
        for port in ports:
            if not 1 <= port <= 65535:
                raise ValueError(f"port {port} is outside 1-65535")
        return ports

    @field_validator("static_hosts", mode="before")
    @classmethod
    def _parse_static_hosts(cls, value: object) -> object:
        """Parse "name=ip,name=ip". Each IP must be a real IP address, not another name."""
        items = _split_list(value)
        if not isinstance(items, list):
            return value
        hosts: dict[str, str] = {}
        for item in items:
            name, sep, ip = item.partition("=")
            if not sep or not name.strip():
                raise ValueError(f"static host {item!r} must look like name=ip")
            ipaddress.ip_address(ip.strip())  # raises ValueError if not an IP
            hosts[name.strip().lower()] = ip.strip()
        return hosts

    @field_validator("ssrf_exempt", mode="before")
    @classmethod
    def _parse_exemptions(cls, value: object) -> object:
        """Parse "host:port,host:port". The exemption is exact: one hostname on one port."""
        items = _split_list(value)
        if not isinstance(items, list):
            return value
        pairs: list[tuple[str, int]] = []
        for item in items:
            host, sep, port_text = item.rpartition(":")
            if not sep or not host or not port_text.isdigit():
                raise ValueError(f"exemption {item!r} must look like host:port")
            port = int(port_text)
            if not 1 <= port <= 65535:
                raise ValueError(f"exemption {item!r} has an invalid port")
            pairs.append((host.lower(), port))
        return tuple(pairs)

    @field_validator("extra_ca_bundle", mode="before")
    @classmethod
    def _empty_means_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def _guard_profile(self) -> "Settings":
        """Refuse demo-only exemptions outside test/demo, so they can never weaken SSRF checks."""
        if self.profile in EXEMPTION_PROFILES:
            return self
        present = [
            name
            for name, value in (
                ("LG_STATIC_HOSTS", self.static_hosts),
                ("LG_SSRF_EXEMPT", self.ssrf_exempt),
                ("LG_EXTRA_CA_BUNDLE", self.extra_ca_bundle),
            )
            if value
        ]
        if present:
            raise ValueError(
                f"{', '.join(present)} only allowed in the test and demo profiles "
                f"(current profile: {self.profile})"
            )
        return self

    @model_validator(mode="after")
    def _check_thresholds(self) -> "Settings":
        """SUSPICIOUS must start below UNSAFE, or a score could skip a verdict (D62)."""
        if self.suspicious_score >= self.unsafe_score:
            raise ValueError("LG_SUSPICIOUS_SCORE must be below LG_UNSAFE_SCORE")
        return self


def log_active_thresholds(settings: Settings) -> None:
    """Log the verdict thresholds at startup, so a changed value is visible in every run
    (the values are fixed by spec §9; D62)."""
    logger.info(
        "Verdict thresholds: SUSPICIOUS at score >= %d, UNSAFE at score >= %d",
        settings.suspicious_score,
        settings.unsafe_score,
    )


def log_active_exemptions(settings: Settings) -> None:
    """Log every active exemption at WARNING so nobody runs with one by accident."""
    for name, ip in settings.static_hosts.items():
        logger.warning("Static host active: %s=%s (profile %s)", name, ip, settings.profile)
    for host, port in settings.ssrf_exempt:
        logger.warning("SSRF exemption active: %s:%d (profile %s)", host, port, settings.profile)
    if settings.extra_ca_bundle:
        logger.warning(
            "Extra CA bundle trusted: %s (profile %s)", settings.extra_ca_bundle, settings.profile
        )


@lru_cache
def get_settings() -> Settings:
    """The settings for this process, read once from the environment."""
    return Settings()
