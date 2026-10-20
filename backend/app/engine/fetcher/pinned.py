"""Pinned connections: connect to the checked address, verify TLS for the original name
(task T1.3, spec §5 "Pinned TLS", decisions D41–D43).

check_target resolved the name once and validated the addresses. Connecting by name would
make httpx resolve it again, and a DNS server could then answer with a private address
(DNS rebinding). So the request goes to the validated IP, while:
- the Host header carries the original name, so the server serves the right site;
- TLS sends the original name as SNI (`sni_hostname`) and checks the certificate against
  it, so a certificate for any other name is refused.

One client per hop (D41): httpx pools connections by (scheme, IP, port), not by SNI name.
On a shared client, a request for another name on the same IP would reuse a connection that
was verified for the first name, and no certificate check would happen for the second.
Every request of one hop (HEAD, Range GET fallback, the single retry) goes to the same
Target, so sharing the client within a hop is safe; never share it across hops or scans.
"""

import ssl
from urllib.parse import urlsplit

import certifi
import httpx

from app.core.config import EXEMPTION_PROFILES, Settings
from app.engine.fetcher.ip_literals import parse_ip_literal
from app.engine.fetcher.targets import DEFAULT_PORTS, Target


def tls_context(settings: Settings) -> ssl.SSLContext:
    """Certificates are always verified, against certifi's CA list (D43): the same on every
    machine, because uv's standalone Python may not find the operating system's store.
    The local test CA (LG_EXTRA_CA_BUNDLE) is added only in the test and demo profiles."""
    context = ssl.create_default_context(cafile=certifi.where())
    if settings.extra_ca_bundle and settings.profile in EXEMPTION_PROFILES:
        context.load_verify_locations(cafile=settings.extra_ca_bundle)
    return context


def new_client(settings: Settings, context: ssl.SSLContext) -> httpx.AsyncClient:
    """A client for ONE hop (D41). trust_env=False: proxy variables, .netrc and the
    environment's CA settings are ignored. Redirects are handled by the fetcher (T1.4),
    which checks every hop again, so httpx must never follow them itself."""
    return httpx.AsyncClient(
        verify=context,
        trust_env=False,
        follow_redirects=False,
        timeout=httpx.Timeout(settings.connect_timeout_s),
    )


def host_header(target: Target) -> str:
    """The original name, bracketed if it is an IPv6 literal, with the port if it is not
    the scheme's default (as a browser would send it)."""
    host = target.punycode_host
    if ":" in host:
        host = f"[{host}]"
    if target.port != DEFAULT_PORTS[target.scheme]:
        host = f"{host}:{target.port}"
    return host


def build_pinned_request(
    client: httpx.AsyncClient, target: Target, method: str, headers: dict[str, str]
) -> httpx.Request:
    """The request for this hop, addressed to the first validated IP. No network I/O:
    the caller sends it (T2.1 with stream=True, to count bytes against the cap)."""
    parts = urlsplit(target.url)
    ip = str(target.ip)
    address = f"[{ip}]" if ":" in ip else ip
    if target.port != DEFAULT_PORTS[target.scheme]:
        address = f"{address}:{target.port}"
    query = f"?{parts.query}" if parts.query else ""
    # The fragment is never sent; httpx percent-encodes anything not ASCII.
    url = f"{target.scheme}://{address}{parts.path or '/'}{query}"
    extensions: dict[str, str] = {}
    # SNI may not carry an IP address (RFC 6066): for an IP-literal URL the certificate is
    # checked against the IP itself.
    if parse_ip_literal(target.punycode_host) is None:
        extensions["sni_hostname"] = target.punycode_host
    return client.build_request(
        method,
        url,
        headers={**headers, "Host": host_header(target)},
        extensions=extensions,
    )
