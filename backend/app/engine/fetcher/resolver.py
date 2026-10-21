"""Name resolution for the fetcher (task T1.2, spec §5).

The checks need the addresses a name resolves to, and the connection must later use exactly
those addresses (pinning), so resolution is a separate, injectable step:

- SystemResolver asks the operating system (getaddrinfo), for real scans.
- StaticHostsResolver answers the demo's fixed names first (test/demo profile only, D2),
  then falls back to another resolver.
- Tests use a fake resolver, so no test ever touches real DNS.
"""

import ipaddress
import socket
from collections.abc import Mapping
from typing import Protocol

from app.engine.fetcher.ip_literals import IPAddress


class ResolveError(LookupError):
    """The name has no addresses (NXDOMAIN, no answer, resolver failure).

    That means "cannot check", not "unsafe": the scan ends as UNABLE_TO_VERIFY.
    """

    def __init__(self, host: str, code: str = "FETCH_DNS_ERROR") -> None:
        super().__init__(f"no addresses for {host}")
        self.host = host
        self.code = code


class Resolver(Protocol):
    """Anything that turns a punycode host name into its addresses, or raises LookupError."""

    def resolve(self, host: str) -> list[IPAddress]: ...


class SystemResolver:
    """getaddrinfo, A and AAAA records, in the order the system returns them. Blocking: the
    async fetcher calls check_target in a worker thread (T2.1)."""

    def resolve(self, host: str) -> list[IPAddress]:
        try:
            infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except (socket.gaierror, UnicodeError):
            raise ResolveError(host) from None
        addresses: list[IPAddress] = []
        for info in infos:
            address = ipaddress.ip_address(info[4][0])
            if address not in addresses:
                addresses.append(address)
        return addresses


class StaticHostsResolver:
    """Fixed name → address pairs (LG_STATIC_HOSTS) first, then the fallback resolver."""

    def __init__(self, static: Mapping[str, str], fallback: Resolver) -> None:
        self.static = {name: ipaddress.ip_address(ip) for name, ip in static.items()}
        self.fallback = fallback

    def resolve(self, host: str) -> list[IPAddress]:
        if host in self.static:
            return [self.static[host]]
        return self.fallback.resolve(host)
