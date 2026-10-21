"""Pinned TLS (task T1.3, spec §5 "Pinned TLS").

The fetcher connects to the address check_target validated (never resolving again) while
TLS checks the certificate against the ORIGINAL host name. These tests use the real demo
server, started as a subprocess on free loopback ports with a fresh test CA:
- the HTTPS listener has a certificate for a/b/c.demo.test (signed by the test CA);
- the wrong-cert listener has a certificate for wrong-host.example (same CA), so a client
  connecting as a.demo.test must refuse it.

Sockets are allowed for 127.0.0.1 only; everything else stays blocked (last test).
"""

import ipaddress
import socket
import ssl

import httpx
import pytest
from pytest_socket import SocketConnectBlockedError

from app.core.config import Settings
from app.engine.fetcher.pinned import build_pinned_request, new_client, tls_context
from app.engine.fetcher.targets import Target, check_target
from tests.demo_server import Demo, RecordingResolver, free_port

pytestmark = [pytest.mark.integration, pytest.mark.allow_hosts(["127.0.0.1"])]


def caused_by_certificate_check(error: BaseException) -> bool:
    """True if a certificate verification failure is anywhere in the exception chain.
    ("Connection refused" is also an httpx.ConnectError; it must not pass these tests.)"""
    seen: BaseException | None = error
    while seen is not None:
        if isinstance(seen, ssl.SSLCertVerificationError):
            return True
        seen = seen.__cause__ or seen.__context__
    return False


async def get(settings: Settings, target: Target) -> httpx.Response:
    """One hop: a fresh client (D41), one pinned GET, client closed."""
    async with new_client(settings, tls_context(settings)) as client:
        return await client.send(build_pinned_request(client, target, "GET", {}))


# --- the T1.3 acceptance: valid cert, wrong-host cert, one resolver call ------------------


@pytest.mark.asyncio
async def test_valid_certificate_for_the_original_host(demo: Demo) -> None:
    settings = demo.settings()
    target = check_target(
        f"https://a.demo.test:{demo.https_port}/page", settings, RecordingResolver(settings)
    )
    response = await get(settings, target)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_wrong_host_certificate_is_a_tls_error(demo: Demo) -> None:
    settings = demo.settings()
    target = check_target(
        f"https://a.demo.test:{demo.wrong_cert_port}/page", settings, RecordingResolver(settings)
    )
    with pytest.raises(httpx.ConnectError) as caught:
        await get(settings, target)
    assert caused_by_certificate_check(caught.value)


@pytest.mark.asyncio
async def test_resolver_called_once_and_the_name_never_reaches_system_dns(
    demo: Demo, monkeypatch: pytest.MonkeyPatch
) -> None:
    looked_up: list[object] = []
    real_getaddrinfo = socket.getaddrinfo

    def recording_getaddrinfo(host: object, *args: object, **kwargs: object) -> object:
        looked_up.append(host)
        return real_getaddrinfo(host, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(socket, "getaddrinfo", recording_getaddrinfo)
    settings = demo.settings()
    resolver = RecordingResolver(settings)
    target = check_target(f"https://a.demo.test:{demo.https_port}/page", settings, resolver)
    assert (await get(settings, target)).status_code == 200
    assert resolver.calls == ["a.demo.test"]
    assert all(host in (None, "127.0.0.1", b"127.0.0.1") for host in looked_up), looked_up


# --- connection reuse (D41: one client per hop) -----------------------------------------


@pytest.mark.asyncio
async def test_a_second_host_on_the_same_ip_gets_its_own_certificate_check(demo: Demo) -> None:
    """Spec §5 row: a connection verified for one host is never reused for another host on
    the same IP. other.demo.test is not in the demo certificate, so its hop must fail even
    right after a successful hop to a.demo.test on the same address and port."""
    settings = demo.settings()
    resolver = RecordingResolver(settings)
    first = check_target(f"https://a.demo.test:{demo.https_port}/page", settings, resolver)
    second = check_target(f"https://other.demo.test:{demo.https_port}/page", settings, resolver)
    assert (await get(settings, first)).status_code == 200
    with pytest.raises(httpx.ConnectError) as caught:
        await get(settings, second)
    assert caused_by_certificate_check(caught.value)


@pytest.mark.asyncio
async def test_httpx_pools_by_address_not_by_name_which_is_why_each_hop_gets_a_client(
    demo: Demo,
) -> None:
    """Canary documenting httpx's pooling behaviour, the reason for D41. It asserts the
    UNSAFE result on purpose: on ONE shared client the second request reuses the connection
    verified for a.demo.test, so it is never checked as other.demo.test. LinkGuard never
    shares a client across hops. If a future httpx keys its pool by SNI, this canary fails:
    then revisit D41 (it would still be correct, just no longer necessary)."""
    settings = demo.settings()
    resolver = RecordingResolver(settings)
    first = check_target(f"https://a.demo.test:{demo.https_port}/page", settings, resolver)
    second = check_target(f"https://other.demo.test:{demo.https_port}/page", settings, resolver)
    async with new_client(settings, tls_context(settings)) as shared:
        assert (
            await shared.send(build_pinned_request(shared, first, "GET", {}))
        ).status_code == 200
        reused = await shared.send(build_pinned_request(shared, second, "GET", {}))
    assert reused.status_code == 200  # unsafe on a shared client; never do this


# --- plain HTTP and the environment ---------------------------------------------------------


@pytest.mark.asyncio
async def test_plain_http_is_pinned_too(demo: Demo) -> None:
    settings = demo.settings()
    target = check_target(
        f"http://a.demo.test:{demo.http_port}/page", settings, RecordingResolver(settings)
    )
    assert (await get(settings, target)).status_code == 200


@pytest.mark.asyncio
async def test_proxy_variables_are_ignored(demo: Demo, monkeypatch: pytest.MonkeyPatch) -> None:
    """Spec §5 row: HTTP_PROXY in the environment is ignored (trust_env=False). Every proxy
    variable points at a closed port; the request must still reach the demo server."""
    closed = f"http://127.0.0.1:{free_port()}"
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        monkeypatch.setenv(name, closed)
        monkeypatch.setenv(name.lower(), closed)
    settings = demo.settings()
    for url in (
        f"http://a.demo.test:{demo.http_port}/page",
        f"https://a.demo.test:{demo.https_port}/page",
    ):
        target = check_target(url, settings, RecordingResolver(settings))
        assert (await get(settings, target)).status_code == 200


# --- building the request (no network) ------------------------------------------------------


def target(url: str, addresses: tuple[str, ...], port: int, host: str) -> Target:
    scheme = url.split(":", 1)[0]
    ips = tuple(ipaddress.ip_address(a) for a in addresses)
    return Target(url, scheme, port, host, host, ips, exempt=False)


async def build(t: Target) -> httpx.Request:
    async with new_client(Settings(), tls_context(Settings())) as client:
        return build_pinned_request(client, t, "HEAD", {"Accept-Encoding": "identity"})


@pytest.mark.asyncio
async def test_request_goes_to_the_first_validated_address_with_the_original_name() -> None:
    """Spec §5 row: fetched from the FIRST validated IP only."""
    request = await build(
        target(
            "https://files.example/a.zip?x=1",
            ("93.184.216.34", "93.184.216.35"),
            443,
            "files.example",
        )
    )
    assert str(request.url) == "https://93.184.216.34/a.zip?x=1"
    assert request.headers["Host"] == "files.example"
    assert request.extensions["sni_hostname"] == "files.example"
    assert request.headers["Accept-Encoding"] == "identity"
    assert request.method == "HEAD"


@pytest.mark.asyncio
async def test_non_default_port_is_in_the_host_header() -> None:
    request = await build(
        target("http://files.example:8081/f", ("93.184.216.34",), 8081, "files.example")
    )
    assert str(request.url) == "http://93.184.216.34:8081/f"
    assert request.headers["Host"] == "files.example:8081"


@pytest.mark.asyncio
async def test_ipv6_address_is_bracketed() -> None:
    request = await build(
        target("https://v6.example/f", ("2606:2800:220:1:248:1893:25c8:1946",), 443, "v6.example")
    )
    assert str(request.url) == "https://[2606:2800:220:1:248:1893:25c8:1946]/f"
    assert request.headers["Host"] == "v6.example"


@pytest.mark.asyncio
async def test_ip_literal_target_sends_no_sni() -> None:
    """SNI may not carry an IP address (RFC 6066); the certificate is checked against the IP."""
    request = await build(
        target("https://93.184.216.34/f", ("93.184.216.34",), 443, "93.184.216.34")
    )
    assert "sni_hostname" not in request.extensions
    assert request.headers["Host"] == "93.184.216.34"


@pytest.mark.asyncio
async def test_ipv6_literal_host_header_is_bracketed() -> None:
    request = await build(
        target("https://[2606:2800::1]/f", ("2606:2800::1",), 443, "2606:2800::1")
    )
    assert request.headers["Host"] == "[2606:2800::1]"


@pytest.mark.asyncio
async def test_empty_path_becomes_slash_and_the_fragment_is_dropped() -> None:
    request = await build(
        target("https://files.example#top", ("93.184.216.34",), 443, "files.example")
    )
    assert str(request.url) == "https://93.184.216.34/"


# --- configuration of the TLS context and the client ---------------------------------------


def test_tls_context_always_verifies() -> None:
    context = tls_context(Settings())
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True


@pytest.mark.asyncio
async def test_client_ignores_environment_and_never_follows_redirects() -> None:
    async with new_client(Settings(), tls_context(Settings())) as client:
        assert client.trust_env is False
        assert client.follow_redirects is False


@pytest.mark.filterwarnings("ignore:A test tried to use socket")
def test_other_addresses_stay_blocked() -> None:
    """allow_hosts opens 127.0.0.1 only: these tests still cannot reach anything else."""
    with pytest.raises(SocketConnectBlockedError):
        socket.create_connection(("10.255.255.1", 80), timeout=0.1)
