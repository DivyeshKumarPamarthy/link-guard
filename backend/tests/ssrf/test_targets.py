"""Behaviour of check_target beyond the spec table (task T1.2): what an accepted target
looks like, host normalization, the order of checks, exemptions and the resolvers."""

import ipaddress

import pytest

from app.core.config import Settings
from app.engine.fetcher.ip_literals import ends_in_a_number, parse_ip_literal
from app.engine.fetcher.resolver import ResolveError, StaticHostsResolver
from app.engine.fetcher.targets import TargetRejected, check_target
from tests.ssrf.fakes import FakeResolver

# --- accepted targets --------------------------------------------------------------------


def test_public_https_target(resolver: FakeResolver) -> None:
    target = check_target("https://files.example/movie.mp4?x=1", Settings(), resolver)
    assert target.scheme == "https"
    assert target.port == 443  # default port filled in
    assert target.display_host == "files.example"
    assert target.punycode_host == "files.example"
    assert str(target.ip) == "93.184.216.34"
    assert target.address_class == "public"
    assert target.url == "https://files.example/movie.mp4?x=1"


def test_default_http_port_is_80(resolver: FakeResolver) -> None:
    assert check_target("http://files.example/", Settings(), resolver).port == 80


def test_all_addresses_are_kept_and_the_first_is_pinned(resolver: FakeResolver) -> None:
    target = check_target("https://example.com/", Settings(), resolver)
    assert [str(a) for a in target.addresses] == [
        "93.184.216.34",
        "2606:2800:220:1:248:1893:25c8:1946",
    ]
    assert target.ip == target.addresses[0]


def test_public_ip_literal_needs_no_dns(resolver: FakeResolver) -> None:
    target = check_target("http://93.184.216.34/file.pdf", Settings(), resolver)
    assert str(target.ip) == "93.184.216.34"
    assert resolver.calls == []


def test_nat64_address_of_a_public_ipv4_is_allowed(resolver: FakeResolver) -> None:
    """On an IPv6-only network, DNS64 answers 64:ff9b::<IPv4> for IPv4-only sites. The
    embedded IPv4 address is what gets judged, so ordinary sites still work there."""
    target = check_target("https://v4only.example/", Settings(), resolver)
    assert str(target.ip) == "64:ff9b::5db8:d822"


# --- normalization ---------------------------------------------------------------------------


def test_scheme_and_host_are_lowercased_and_trailing_dot_removed(resolver: FakeResolver) -> None:
    target = check_target("HTTPS://Files.Example./a", Settings(), resolver)
    assert (target.scheme, target.display_host) == ("https", "files.example")
    assert resolver.calls == ["files.example"]


def test_idn_host_keeps_both_forms_and_resolves_punycode(resolver: FakeResolver) -> None:
    target = check_target("https://bücher.example/", Settings(), resolver)
    assert target.display_host == "bücher.example"
    assert target.punycode_host == "xn--bcher-kva.example"
    assert resolver.calls == ["xn--bcher-kva.example"]


def test_at_sign_in_the_fragment_is_not_userinfo(resolver: FakeResolver) -> None:
    """Plan M2: http://evil.example#@google.com is a link to evil.example, not google.com."""
    target = check_target("http://evil.example#@google.com", Settings(), resolver)
    assert target.display_host == "evil.example"


@pytest.mark.parametrize(
    "url",
    [
        "http://user:pass@files.example/",
        "http://user@files.example/",
        "http://:@files.example/",
    ],
)
def test_any_userinfo_is_rejected(url: str, resolver: FakeResolver) -> None:
    with pytest.raises(TargetRejected) as caught:
        check_target(url, Settings(), resolver)
    assert caught.value.code == "URL_USERINFO"
    assert resolver.calls == []


def test_ftp_is_rejected_here_the_router_reports_it_as_unsupported(
    resolver: FakeResolver,
) -> None:
    """The router (T3.1) turns ftp: into 'unsupported' before the fetcher; if one ever reaches
    the fetcher, it is refused like any other non-HTTP scheme."""
    with pytest.raises(TargetRejected) as caught:
        check_target("ftp://files.example/a.zip", Settings(), resolver)
    assert caught.value.code == "URL_SCHEME_UNSUPPORTED"


def test_rejection_names_the_port(resolver: FakeResolver) -> None:
    with pytest.raises(TargetRejected) as caught:
        check_target("https://example.com:6379/", Settings(), resolver)
    assert caught.value.evidence == {"port": 6379}


@pytest.mark.parametrize(
    "url", ["http://[::ffff:127.0.0.1]/", "http://[::]/", "http://[fc00::1]/", "http://0/"]
)
def test_more_non_public_literals(url: str, resolver: FakeResolver) -> None:
    with pytest.raises(TargetRejected) as caught:
        check_target(url, Settings(), resolver)
    assert caught.value.code == "URL_PRIVATE_ADDRESS"


def test_unknown_host_is_a_dns_error_not_a_rejection(resolver: FakeResolver) -> None:
    """NXDOMAIN means 'cannot check' (FETCH_DNS_ERROR, Unable to verify), not 'unsafe target'."""
    with pytest.raises(ResolveError) as caught:
        check_target("https://no-such-host.example/", Settings(), resolver)
    assert caught.value.code == "FETCH_DNS_ERROR"


# --- URL_INVALID (decision D38): refused before any DNS lookup -------------------------------


def invalid(url: str, resolver: FakeResolver, settings: Settings | None = None) -> None:
    with pytest.raises(TargetRejected) as caught:
        check_target(url, settings or Settings(), resolver)
    assert caught.value.code == "URL_INVALID"
    assert resolver.calls == [], "an invalid URL must never reach DNS"


@pytest.mark.parametrize(
    "url",
    [
        "http://",  # no host
        "http:///etc/passwd",  # no host
        "http://:80/",  # a port but no host
        "https:files.example/a.zip",  # no "//", so no host
        "files.example/a.zip",  # no scheme
        "http://[::1/",  # bracket never closed
        "http://[not-an-ip]/",  # brackets around something that is not IPv6
        "http://files.example:99999/",  # port out of range
        "http://files.example:abc/",  # port is not a number
    ],
)
def test_unparseable_urls_are_invalid(url: str, resolver: FakeResolver) -> None:
    invalid(url, resolver)


@pytest.mark.parametrize(
    "url",
    [
        "http://256.1.1.1/",  # octet too big
        "http://08.0.0.1/",  # leading 0 means octal, and 8 is not an octal digit
        "http://1.2.3.4.5/",  # five parts
        "http://4294967296/",  # one number, but bigger than 32 bits
        "http://files.123/",  # a name whose last label is a number
        "http://files.0x1f/",  # same, in hex
    ],
)
def test_host_ending_in_a_number_must_be_a_valid_ipv4_address(
    url: str, resolver: FakeResolver
) -> None:
    """WHATWG rule: such a host is parsed as IPv4 or refused, never looked up as a name."""
    invalid(url, resolver)


@pytest.mark.parametrize(
    "url",
    [
        "http://[fe80::1%25eth0]/",  # IPv6 zone ID
        "http://%31%32%37.0.0.1/",  # "127.0.0.1" percent-encoded
    ],
)
def test_percent_in_the_host_is_invalid(url: str, resolver: FakeResolver) -> None:
    """Hosts are never percent-decoded: a parser that decodes would see 127.0.0.1."""
    invalid(url, resolver)


def test_url_longer_than_the_limit_is_invalid(resolver: FakeResolver) -> None:
    """Checked inside check_target, so it also covers every redirect hop (T1.4)."""
    url = "https://files.example/" + "a" * 19
    assert len(url) == 41
    invalid(url, resolver, Settings(max_url_length=40))


def test_url_exactly_at_the_limit_is_checked_normally(resolver: FakeResolver) -> None:
    url = "https://files.example/" + "a" * 18
    assert len(url) == 40
    assert check_target(url, Settings(max_url_length=40), resolver).display_host == "files.example"


# --- exemptions --------------------------------------------------------------------------


def demo_settings() -> Settings:
    return Settings(
        profile="test",
        static_hosts={"a.demo.test": "127.0.0.1"},
        ssrf_exempt=(("a.demo.test", 8081),),
        allowed_ports=(80, 443, 8081),
    )


def test_exempt_demo_host_and_port_is_allowed(resolver: FakeResolver) -> None:
    settings = demo_settings()
    static = StaticHostsResolver(settings.static_hosts, fallback=resolver)
    target = check_target("http://a.demo.test:8081/f/sample.pdf", settings, static)
    assert str(target.ip) == "127.0.0.1"
    assert target.address_class == "private"
    assert target.exempt is True
    assert resolver.calls == []  # answered by the static table, not DNS


def test_exemption_needs_the_test_or_demo_profile(resolver: FakeResolver) -> None:
    """Settings already refuse exemptions in dev/prod (T0.2); check_target must not rely on
    a stale object either: a dev-profile Settings has no exemptions at all."""
    static = StaticHostsResolver({"a.demo.test": "127.0.0.1"}, fallback=resolver)
    with pytest.raises(TargetRejected) as caught:
        check_target("http://a.demo.test/", Settings(), static)
    assert caught.value.code == "URL_PRIVATE_ADDRESS"


# --- resolvers ----------------------------------------------------------------------------


def test_static_hosts_answer_first_then_fall_back(resolver: FakeResolver) -> None:
    static = StaticHostsResolver({"a.demo.test": "127.0.0.1"}, fallback=resolver)
    assert static.resolve("a.demo.test") == [ipaddress.ip_address("127.0.0.1")]
    assert static.resolve("files.example") == [ipaddress.ip_address("93.184.216.34")]
    assert resolver.calls == ["files.example"]


# --- strict IP literal parsing ------------------------------------------------------------


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", "127.0.0.1"),
        ("2130706433", "127.0.0.1"),  # one 32-bit decimal number
        ("0x7f.0.0.1", "127.0.0.1"),  # hex part
        ("0x7f.1", "127.0.0.1"),  # hex + short form
        ("0X7F.0.0.1", "127.0.0.1"),  # uppercase hex prefix
        ("0177.0.0.1", "127.0.0.1"),  # octal part
        ("127.1", "127.0.0.1"),  # short form: last part fills the remaining bytes
        ("10.1.2", "10.1.0.2"),
        ("0", "0.0.0.0"),
        ("::1", "::1"),
        ("::ffff:169.254.169.254", "::ffff:a9fe:a9fe"),
    ],
)
def test_ip_literal_forms(host: str, expected: str) -> None:
    assert parse_ip_literal(host) == ipaddress.ip_address(expected)


@pytest.mark.parametrize(
    "host",
    [
        "example.com",
        "files.example",
        "a.demo.test",
        "xn--bcher-kva.example",
        "256.1.1.1",  # numeric but invalid: check_target refuses these (D38)
        "08.0.0.1",
        "1.2.3.4.5",
        "4294967296",
    ],
)
def test_names_are_not_ip_literals(host: str) -> None:
    assert parse_ip_literal(host) is None


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", True),
        ("256.1.1.1", True),
        ("1.2.3.4.5", True),
        ("files.123", True),
        ("files.0x1f", True),
        ("files.0X1F", True),
        ("example.com", False),
        ("123.example", False),  # only the LAST label counts
        ("files.0xzz", False),  # "0x" followed by non-hex is a name
        ("files.12a", False),
    ],
)
def test_ends_in_a_number(host: str, expected: bool) -> None:
    assert ends_in_a_number(host) is expected
