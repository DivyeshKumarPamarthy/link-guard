"""The SSRF test table from docs/phase1-spec.md §5 (task T1.2).

Every row must be rejected with the stated code and with zero network activity
(socket guard in conftest.py). Rows that need a redirect or a real fetch belong to later
tasks and are listed at the bottom of this file.
"""

import pytest

from app.core.config import Settings
from app.engine.fetcher.resolver import Resolver, StaticHostsResolver
from app.engine.fetcher.targets import TargetRejected, check_target
from tests.ssrf.fakes import FakeResolver

FULLWIDTH_127 = "".join(chr(0xFF10 + int(d)) for d in "127")  # "127" in full-width digits
IDEOGRAPHIC_DOT = chr(0x3002)  # "。", which IDNA maps to "."


def rejected_code(url: str, settings: Settings, resolver: Resolver) -> str:
    with pytest.raises(TargetRejected) as caught:
        check_target(url, settings, resolver)
    return caught.value.code


# (url, expected code, may the resolver be asked?)  False = must be decided before DNS.
TABLE: list[tuple[str, str, bool]] = [
    ("http://127.0.0.1/", "URL_PRIVATE_ADDRESS", False),
    ("http://localhost:8000/", "URL_PORT_BLOCKED", False),  # port check runs first
    ("http://localhost./", "URL_PRIVATE_ADDRESS", True),
    ("http://[::1]/", "URL_PRIVATE_ADDRESS", False),
    ("http://0.0.0.0/", "URL_PRIVATE_ADDRESS", False),
    ("http://2130706433/", "URL_PRIVATE_ADDRESS", False),
    ("http://0x7f.0.0.1/", "URL_PRIVATE_ADDRESS", False),
    ("http://0177.0.0.1/", "URL_PRIVATE_ADDRESS", False),
    ("http://127.1/", "URL_PRIVATE_ADDRESS", False),
    (f"http://{FULLWIDTH_127}.0.0.1/", "URL_PRIVATE_ADDRESS", False),
    ("http://169.254.169.254/latest/meta-data/", "URL_PRIVATE_ADDRESS", False),
    ("http://[::ffff:169.254.169.254]/", "URL_PRIVATE_ADDRESS", False),
    ("http://metadata.google.internal/", "URL_PRIVATE_ADDRESS", True),
    ("http://10.0.0.5/", "URL_PRIVATE_ADDRESS", False),
    ("http://172.16.0.1/", "URL_PRIVATE_ADDRESS", False),
    ("http://192.168.1.1/", "URL_PRIVATE_ADDRESS", False),
    ("http://100.64.0.1/", "URL_PRIVATE_ADDRESS", False),
    ("http://[fe80::1]/", "URL_PRIVATE_ADDRESS", False),
    ("http://localtest.me/", "URL_PRIVATE_ADDRESS", True),
    ("http://127.0.0.1.nip.io/", "URL_PRIVATE_ADDRESS", True),
    ("http://google.com@127.0.0.1/", "URL_USERINFO", False),
    ("https://example.com:22/", "URL_PORT_BLOCKED", False),
    ("https://example.com:6379/", "URL_PORT_BLOCKED", False),
    ("https://example.com:5432/", "URL_PORT_BLOCKED", False),
    ("file:///etc/passwd", "URL_SCHEME_UNSUPPORTED", False),
    ("gopher://x/", "URL_SCHEME_UNSUPPORTED", False),
    ("data:text/plain,hi", "URL_SCHEME_UNSUPPORTED", False),
    ("javascript:alert(1)", "URL_SCHEME_UNSUPPORTED", False),
    ("http://mixed.example/", "URL_PRIVATE_ADDRESS", True),  # one public + one private record
    # Bypasses added after the spec table (decision D38 and the T1.2 review):
    (
        f"http://127{IDEOGRAPHIC_DOT}0{IDEOGRAPHIC_DOT}0{IDEOGRAPHIC_DOT}1/",
        "URL_PRIVATE_ADDRESS",
        False,
    ),
    ("http://0X7F.0.0.1/", "URL_PRIVATE_ADDRESS", False),  # uppercase hex prefix
    ("http://[fe80::1%25eth0]/", "URL_INVALID", False),  # IPv6 zone ID: any % in the host
    # Addresses Python's ipaddress.is_global wrongly calls public (decision D40):
    ("http://[::7f00:1]/", "URL_PRIVATE_ADDRESS", False),  # IPv4-compatible form of 127.0.0.1
    ("http://[::5db8:d822]/", "URL_PRIVATE_ADDRESS", False),  # ::/96 refused even for a public IPv4
    ("http://[64:ff9b::7f00:1]/", "URL_PRIVATE_ADDRESS", False),  # NAT64 form of 127.0.0.1
    ("http://[64:ff9b::a00:1]/", "URL_PRIVATE_ADDRESS", False),  # NAT64 form of 10.0.0.1
    ("http://nat64.example/", "URL_PRIVATE_ADDRESS", True),  # DNS64 answer for 127.0.0.1
    ("http://[fec0::1]/", "URL_PRIVATE_ADDRESS", False),  # IPv6 site-local (deprecated)
    ("http://224.0.0.1/", "URL_PRIVATE_ADDRESS", False),  # IPv4 multicast
    ("http://[ff02::1]/", "URL_PRIVATE_ADDRESS", False),  # IPv6 multicast
    ("http://239.255.255.250/", "URL_PRIVATE_ADDRESS", False),  # IPv4 multicast (SSDP)
    # Other IPv6 forms that carry an IPv4 address (is_global already refuses these; kept so
    # a Python upgrade cannot silently open them):
    ("http://[64:ff9b:1::7f00:1]/", "URL_PRIVATE_ADDRESS", False),  # local-use NAT64
    ("http://[2002:7f00:1::]/", "URL_PRIVATE_ADDRESS", False),  # 6to4 form of 127.0.0.1
    ("http://[2001:0:4136:e378:8000:63bf:3fff:fdd2]/", "URL_PRIVATE_ADDRESS", False),  # Teredo
]


@pytest.mark.parametrize(("url", "code", "dns_allowed"), TABLE, ids=[row[0] for row in TABLE])
def test_spec_table_row_is_rejected(
    url: str, code: str, dns_allowed: bool, resolver: FakeResolver
) -> None:
    assert rejected_code(url, Settings(), resolver) == code
    if not dns_allowed:
        assert resolver.calls == [], "this row must be decided without any DNS lookup"


# --- demo exemption rows (test profile with the demo server's settings) ---------------------


def demo_settings() -> Settings:
    return Settings(
        profile="test",
        static_hosts={"a.demo.test": "127.0.0.1"},
        ssrf_exempt=(("a.demo.test", 8081),),
        allowed_ports=(80, 443, 8081, 8082),  # 8082 allowed, so only the exemption decides
    )


def test_exempt_host_on_another_port_is_rejected(resolver: FakeResolver) -> None:
    """The exemption is exact host:port: a.demo.test:8081 does not cover :8082."""
    settings = demo_settings()
    static = StaticHostsResolver(settings.static_hosts, fallback=resolver)
    assert rejected_code("http://a.demo.test:8082/", settings, static) == "URL_PRIVATE_ADDRESS"


def test_demo_server_ip_is_not_exempt(resolver: FakeResolver) -> None:
    """Only the exempt *name* is allowed; the same IP written directly is still private."""
    assert rejected_code("http://127.0.0.1:8081/", demo_settings(), resolver) == (
        "URL_PRIVATE_ADDRESS"
    )


# --- rebinding (the part that can be tested without a fetch) ---------------------------------


def test_rebinding_resolves_once_and_pins_the_first_answer(resolver: FakeResolver) -> None:
    """Spec row: resolver answers public then private. One check = exactly one lookup, and
    the returned target carries the address that was validated. Connecting to that pinned
    address (never resolving again) is tested with the fetcher in T1.3/T2.1."""
    target = check_target("http://rebind.example/", Settings(), resolver)
    assert resolver.calls == ["rebind.example"]
    assert str(target.ip) == "93.184.216.34"


# Rows from spec §5 that belong to later tasks (not testable without a redirect or a fetch):
# - public demo URL that 302s to http://127.0.0.1/ -> SSRF_BLOCKED_AT_HOP   (T1.4 redirects)
# - rebinding: "fetched from the FIRST validated IP only"                   (T1.3 / T2.1)
# - HTTP_PROXY set in the environment is ignored (trust_env=False)          (T1.3 / T2.1)
