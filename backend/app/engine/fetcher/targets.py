"""Decides whether a URL is safe to contact: the SSRF guard (task T1.2, spec §5).

check_target runs the cheap checks on the URL text first (length, parsing, scheme, userinfo,
port, host), so most bad links are refused before any DNS lookup. Then it resolves the name
ONCE and checks every address. The returned Target carries those addresses: the fetcher must
connect to them and never resolve again (pinning, against DNS rebinding). It is called for
the pasted URL and again for every redirect hop (T1.4). It never opens a connection itself.
"""

import ipaddress
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit

import idna

from app.contract.models import AddressClass
from app.core.config import EXEMPTION_PROFILES, Settings
from app.engine.fetcher.ip_literals import IPAddress, ends_in_a_number, parse_ip_literal
from app.engine.fetcher.resolver import ResolveError, Resolver

DEFAULT_PORTS = {"http": 80, "https": 443}
# Characters allowed in an ASCII host name: letters, digits, hyphen, dot, and underscore
# (not allowed by the DNS host-name rules, but used by real sites).
ASCII_HOST_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789-_.")


class TargetRejected(Exception):
    """The URL must not be contacted. `code` is a reason code with outcome `rejected`."""

    def __init__(self, code: str, evidence: dict[str, object] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.evidence = evidence or {}


def check_length(url: str, max_length: int) -> None:
    """A redirect hop can be any length (only the pasted URL passes the API check), and very
    long URLs are a cheap way to make every later step slow."""
    if len(url) > max_length:
        raise TargetRejected("URL_INVALID")


def split_url(url: str) -> SplitResult:
    """urlsplit raises ValueError for broken brackets ("http://[::1/") and for brackets around
    something that is not an IPv6 address; that becomes URL_INVALID instead of a crash."""
    try:
        return urlsplit(url)
    except ValueError:
        raise TargetRejected("URL_INVALID") from None


def check_scheme(parts: SplitResult) -> str:
    """Only http and https are web downloads. file:, gopher:, data: and javascript: would read
    local files or talk to other services. No scheme at all means we cannot tell what it is."""
    if not parts.scheme:
        raise TargetRejected("URL_INVALID")
    if parts.scheme not in DEFAULT_PORTS:
        raise TargetRejected("URL_SCHEME_UNSUPPORTED", {"scheme": parts.scheme})
    return parts.scheme


def check_no_userinfo(parts: SplitResult) -> None:
    """A link like http://google.com@127.0.0.1/ goes to 127.0.0.1: the part before @ is only
    a user name, there to disguise the real host. Any @ in the authority is refused, even ":@"."""
    if "@" in parts.netloc:
        raise TargetRejected("URL_USERINFO")


def check_has_host(parts: SplitResult) -> None:
    """Links like http:///etc/passwd, https:files.example and http://:80/ name no host."""
    if not parts.hostname:
        raise TargetRejected("URL_INVALID")


def check_port(parts: SplitResult, scheme: str, allowed_ports: tuple[int, ...]) -> int:
    """Only web ports are allowed, so a link cannot reach SSH (22), Redis (6379) or a database
    (5432) on a public host. Runs before DNS: no lookup is needed to refuse a port."""
    try:
        port = parts.port
    except ValueError:  # not a number, or outside 0-65535
        raise TargetRejected("URL_INVALID") from None
    if port is None:
        port = DEFAULT_PORTS[scheme]
    if port not in allowed_ports:
        raise TargetRejected("URL_PORT_BLOCKED", {"port": port})
    return port


@dataclass(frozen=True)
class Host:
    display: str  # what the user sees: Unicode for IDNs ("bücher.example")
    punycode: str  # what DNS and TLS see ("xn--bcher-kva.example")
    ip: IPAddress | None  # set when the host is an IP literal


def normalize_host(raw: str) -> Host:
    """Turn the host into the one form every later step uses, or refuse it.

    - Any "%" is refused: an IPv6 zone ID ("fe80::1%25eth0") or a percent-encoded host
      ("%31%32%37.0.0.1" is 127.0.0.1 to a parser that decodes it). We never decode (D38).
    - IDNA (UTS 46) mapping lowercases and turns full-width digits and ideographic dots
      ("１２７。0。0。1") into ASCII, so they cannot hide an IP address.
    - One trailing dot is removed ("localhost." is "localhost").
    - A host whose last label is a number must be a valid IPv4 address (WHATWG, D38).
    """
    if "%" in raw:
        raise TargetRejected("URL_INVALID")
    if ":" in raw:  # IPv6, from inside [brackets]
        ip = parse_ip_literal(raw)
        if ip is None:
            raise TargetRejected("URL_INVALID")
        return Host(raw, raw, ip)
    try:
        mapped = idna.uts46_remap(raw, std3_rules=False, transitional=False)
    except (idna.IDNAError, UnicodeError):
        raise TargetRejected("URL_INVALID") from None
    if mapped.endswith("."):
        mapped = mapped[:-1]
    if "" in mapped.split("."):  # empty host or empty label ("a..b")
        raise TargetRejected("URL_INVALID")
    if ends_in_a_number(mapped):
        ip = parse_ip_literal(mapped)
        if ip is None:
            raise TargetRejected("URL_INVALID")
        return Host(mapped, mapped, ip)
    if mapped.isascii():
        if not set(mapped) <= ASCII_HOST_CHARS:
            raise TargetRejected("URL_INVALID")
        return Host(mapped, mapped, None)
    try:
        punycode = idna.encode(mapped).decode("ascii")
    except (idna.IDNAError, UnicodeError):
        raise TargetRejected("URL_INVALID") from None
    return Host(mapped, punycode, None)


# D40: IPv6 ranges that are never contacted, or that carry an IPv4 address.
IPV4_COMPATIBLE = ipaddress.IPv6Network("::/96")  # deprecated (RFC 4291); includes :: and ::1
NAT64 = ipaddress.IPv6Network("64:ff9b::/96")  # a NAT64 gateway forwards to the last 32 bits


def is_public(address: IPAddress) -> bool:
    """Only globally routable addresses may be contacted (D40).

    Python's ipaddress.is_global is the base rule, but it calls some unsafe addresses
    public, so these are handled first:
    - multicast (IPv4 and IPv6), IPv6 site-local (fec0::/10) and the deprecated
      IPv4-compatible form (::/96) are never contacted;
    - IPv4-mapped (::ffff:a.b.c.d) and NAT64 (64:ff9b::a.b.c.d) addresses reach their IPv4
      part, so that part is judged. A NAT64 address of a public site (how IPv6-only
      networks reach IPv4-only sites) is therefore allowed.
    """
    if address.is_multicast:
        return False
    if isinstance(address, ipaddress.IPv6Address):
        if address.is_site_local or address in IPV4_COMPATIBLE:
            return False
        if address.ipv4_mapped is not None:
            return address.ipv4_mapped.is_global
        if address in NAT64:
            return ipaddress.IPv4Address(int(address) & 0xFFFFFFFF).is_global
    return address.is_global


def is_exempt(host: Host, port: int, settings: Settings) -> bool:
    """The demo exemption (D2): an exact (name, port) pair, in the test or demo profile only.
    An IP literal is never exempt, so the demo server's own address stays blocked."""
    return (
        settings.profile in EXEMPTION_PROFILES
        and host.ip is None
        and (host.punycode, port) in settings.ssrf_exempt
    )


def resolve_once(host: Host, resolver: Resolver) -> tuple[IPAddress, ...]:
    """Exactly one lookup per hop. An IP literal needs none. No answer means "cannot
    check" (FETCH_DNS_ERROR), which is not the same as "unsafe"."""
    if host.ip is not None:
        return (host.ip,)
    try:
        addresses = resolver.resolve(host.punycode)
    except LookupError:
        raise ResolveError(host.punycode) from None
    if not addresses:
        raise ResolveError(host.punycode)
    return tuple(addresses)


@dataclass(frozen=True)
class Target:
    """A URL that passed every check, with the addresses the fetcher must connect to."""

    url: str
    scheme: str
    port: int
    display_host: str
    punycode_host: str
    addresses: tuple[IPAddress, ...]  # all validated; the fetcher uses these, never DNS
    exempt: bool  # True only for a demo (name, port) exemption

    @property
    def ip(self) -> IPAddress:
        """The pinned address: the first one the resolver returned."""
        return self.addresses[0]

    @property
    def address_class(self) -> AddressClass:
        return AddressClass.public if not self.exempt else AddressClass.private


def check_target(url: str, settings: Settings, resolver: Resolver) -> Target:
    """Refuse the URL (TargetRejected, or ResolveError for "cannot check"), or return it
    with its validated addresses. Checks run cheapest first; DNS comes last."""
    check_length(url, settings.max_url_length)
    parts = split_url(url)
    scheme = check_scheme(parts)
    check_no_userinfo(parts)
    check_has_host(parts)
    port = check_port(parts, scheme, settings.allowed_ports)
    host = normalize_host(parts.hostname or "")
    addresses = resolve_once(host, resolver)
    exempt = is_exempt(host, port, settings)
    # ANY non-public address rejects: a name with one public and one private record could
    # otherwise be fetched from the private one.
    if not all(is_public(a) for a in addresses) and not exempt:
        raise TargetRejected("URL_PRIVATE_ADDRESS")
    return Target(url, scheme, port, host.display, host.punycode, addresses, exempt)
