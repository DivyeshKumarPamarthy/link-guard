"""A fake resolver for the SSRF tests (task T1.2).

It answers from a fixed table and records every lookup, so a test can prove that a URL was
rejected *before* any DNS lookup, or that a name was resolved exactly once (pinning).
"""

import ipaddress

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


class FakeResolver:
    """Answers lookups from `answers`; each entry is a list of address lists, one per call.

    A host with one answer list returns it every time. A host with several returns them in
    order (used for the DNS-rebinding row). Unknown hosts raise LookupError.
    """

    def __init__(self, answers: dict[str, list[list[str]]]) -> None:
        self.answers = answers
        self.calls: list[str] = []

    def resolve(self, host: str) -> list[IPAddress]:
        self.calls.append(host)
        if host not in self.answers:
            raise LookupError(f"fake DNS: no such host {host}")
        sequence = self.answers[host]
        index = min(self.calls.count(host), len(sequence)) - 1
        return [ipaddress.ip_address(a) for a in sequence[index]]


# Names used by the spec §5 table and the extra cases. Anything else is NXDOMAIN.
FAKE_DNS: dict[str, list[list[str]]] = {
    "localhost": [["127.0.0.1", "::1"]],
    "metadata.google.internal": [["169.254.169.254"]],
    "localtest.me": [["127.0.0.1"]],
    "127.0.0.1.nip.io": [["127.0.0.1"]],
    "example.com": [["93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"]],
    "files.example": [["93.184.216.34"]],
    "evil.example": [["93.184.216.35"]],
    "xn--bcher-kva.example": [["93.184.216.36"]],  # bücher.example
    "mixed.example": [["93.184.216.34", "10.0.0.7"]],  # one public, one private A record
    "rebind.example": [["93.184.216.34"], ["127.0.0.1"]],  # public first, private second
    "nat64.example": [["64:ff9b::7f00:1"]],  # DNS64-synthesized AAAA for 127.0.0.1
    "v4only.example": [["64:ff9b::5db8:d822"]],  # DNS64-synthesized AAAA for 93.184.216.34
}
