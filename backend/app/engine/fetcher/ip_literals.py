"""Strict parsing of IP addresses written as URL hosts (task T1.2, spec §5).

Browsers and C libraries accept many spellings of one IPv4 address: 2130706433, 0x7f.0.0.1,
0177.0.0.1 and 127.1 all mean 127.0.0.1. If LinkGuard read them as names, a lookup could
still reach loopback. So these follow the WHATWG URL Standard's IPv4 parser: every spelling
it accepts is turned into the real address, and a host that looks numeric but is not a
valid address is refused by the caller (decision D38), never sent to DNS.

Hosts reach these functions already lowercased and IDNA-mapped (full-width digits and
ideographic dots are plain ASCII by then), without brackets and without a trailing dot.
"""

import ipaddress

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

HEX_DIGITS = set("0123456789abcdefABCDEF")


def ends_in_a_number(host: str) -> bool:
    """WHATWG "ends in a number": the last label is all digits, or 0x followed by hex digits.

    Such a host must be a valid IPv4 address; "files.123" or "256.1.1.1" is refused.
    """
    last = host.split(".")[-1]
    if last.isascii() and last.isdigit():
        return True
    return last[:2] in ("0x", "0X") and set(last[2:]) <= HEX_DIGITS


def parse_ipv4_number(part: str) -> int | None:
    """One dotted part: 0x prefix means hex, a leading 0 means octal, otherwise decimal."""
    if part[:2] in ("0x", "0X"):
        digits, base = part[2:], 16
        if digits == "":
            return 0  # "0x" alone is zero in the WHATWG parser
    elif len(part) > 1 and part.startswith("0"):
        digits, base = part[1:], 8
    else:
        digits, base = part, 10
    if not digits.isascii() or not digits.isalnum():
        return None
    try:
        return int(digits, base)
    except ValueError:  # e.g. "08": 8 is not an octal digit
        return None


def parse_ipv4(host: str) -> ipaddress.IPv4Address | None:
    """1 to 4 parts; every part but the last is one byte, the last fills the remaining bytes
    (so "127.1" is 127.0.0.1 and "2130706433" is one 32-bit number)."""
    parts = host.split(".")
    if not 1 <= len(parts) <= 4 or "" in parts:
        return None
    numbers = [parse_ipv4_number(part) for part in parts]
    if any(n is None for n in numbers):
        return None
    *leading, last = [n for n in numbers if n is not None]
    if any(n > 255 for n in leading) or last >= 256 ** (5 - len(parts)):
        return None
    value = last
    for i, n in enumerate(leading):
        value += n << (8 * (3 - i))
    return ipaddress.IPv4Address(value)


def parse_ip_literal(host: str) -> IPAddress | None:
    """The address a host names directly, or None if it is not an IP literal.

    IPv6 hosts (from inside [brackets]) contain ":"; Python's ipaddress parses them,
    including IPv4-mapped forms like ::ffff:169.254.169.254.
    """
    if ":" in host:
        try:
            return ipaddress.IPv6Address(host)
        except ValueError:
            return None
    return parse_ipv4(host)
