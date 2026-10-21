"""Following redirects safely (task T1.4, spec §5-§6, decisions D6, D38, D45-D50).

httpx never follows redirects itself (follow_redirects=False): this module does it by hand,
so every redirect target gets the same full check as the pasted URL (check_target), one DNS
lookup per hop, before anything is sent to it. The chain is recorded hop by hop, and when it
stops early the reason says where.

The function that contacts one hop is passed in (`send_hop`), so this logic is tested with
fakes and T2.1 plugs in the real HEAD/GET request (pinned.py).
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from urllib.parse import urldefrag, urljoin, urlsplit

from app.contract.models import AddressClass, LinkType, RedirectHop
from app.core.config import Settings
from app.engine.fetcher.resolver import ResolveError, Resolver
from app.engine.fetcher.targets import Target, TargetRejected, check_target

# D45: the redirect statuses of the Fetch standard.
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
WEB_SCHEMES = ("http", "https")
# D6 and D50: link kinds that are "not supported yet" rather than refused.
UNSUPPORTED_SCHEMES = {"magnet": LinkType.magnet, "ftp": LinkType.ftp, "intent": LinkType.other}
LINK_KIND_LABELS = {
    LinkType.torrent: "Torrent files",
    LinkType.magnet: "Magnet links",
    LinkType.ftp: "FTP links",
    LinkType.other: "App links (intent:)",
}


@dataclass(frozen=True)
class Finding:
    """A reason code with its evidence, before scoring (codes live in the registry)."""

    code: str
    evidence: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class HopResponse:
    """What the redirect logic needs from one response: its status and every Location."""

    status: int
    locations: tuple[str, ...] = ()


@dataclass
class RedirectOutcome:
    """Plain data (D48): the hops as recorded, facts about the chain, and either the final
    target and response, or the reason the chain stopped."""

    hops: list[RedirectHop] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    stop: Finding | None = None
    final_target: Target | None = None
    final_response: HopResponse | None = None
    changed_host: bool = False  # link_type = shortened (spec §6)


SendHop = Callable[[Target], Awaitable[HopResponse]]


def unsupported_link_kind(url: str) -> LinkType | None:
    """magnet:, ftp: and intent: links, and http(s) links to a .torrent file, are "not
    supported yet" (D6, D50). The router (T3.1) uses the same rule for pasted links."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    if parts.scheme in UNSUPPORTED_SCHEMES:
        return UNSUPPORTED_SCHEMES[parts.scheme]
    if parts.scheme in WEB_SCHEMES and parts.path.lower().endswith(".torrent"):
        return LinkType.torrent
    return None


def is_redirect(response: HopResponse) -> bool:
    """D45: a redirect status with a Location that is not blank."""
    return response.status in REDIRECT_STATUSES and any(v.strip() for v in response.locations)


def single_location(response: HopResponse) -> str | None:
    """The Location value, or None if the response gives two different ones. Clients
    disagree on which one wins, so a check could approve one target while another client
    follows the other: we refuse instead of picking one."""
    values = {v.strip() for v in response.locations if v.strip()}
    return values.pop() if len(values) == 1 else None


def bad_target(detail: str, scheme: str | None = None) -> Finding:
    """REDIR_BAD_TARGET: the message says why in plain words, the evidence keeps the detail."""
    reason = f"it uses the {scheme}: scheme" if scheme else "it is not a valid web address"
    return Finding("REDIR_BAD_TARGET", {"reason": reason, "detail": detail})


def refusal(rejected: TargetRejected, hop: int) -> Finding:
    """check_target refused a URL. The pasted URL (hop 0) keeps its own code; at a redirect
    hop the codes are mapped as decided in D47."""
    if hop == 0:
        return Finding(rejected.code, dict(rejected.evidence))
    if rejected.code == "URL_PRIVATE_ADDRESS":
        return Finding("SSRF_BLOCKED_AT_HOP", {"hop": hop})
    if rejected.code in ("URL_INVALID", "URL_SCHEME_UNSUPPORTED"):
        return bad_target("invalid address")
    return Finding(rejected.code, dict(rejected.evidence))


def next_url(current: Target, location: str) -> str:
    """Location may be relative ("/b", "../c", "//host/x"): resolve it against the current
    URL, and drop the fragment, which is never sent and must not defeat loop detection."""
    return urldefrag(urljoin(current.url, location)).url


async def follow_redirects(
    url: str, settings: Settings, resolver: Resolver, send_hop: SendHop
) -> RedirectOutcome:
    """Check and contact the URL, then each redirect target in turn (D46 order):
    too many → unsupported or non-web scheme → loop → full check_target → send."""
    outcome = RedirectOutcome()
    visited = {urldefrag(url).url}
    current = url
    followed = 0  # redirects followed so far
    contacted: list[Target] = []

    while True:
        # (d) the full check, in a worker thread because DNS lookups block
        try:
            target = await asyncio.to_thread(check_target, current, settings, resolver)
        except TargetRejected as rejected:
            outcome.hops.append(
                RedirectHop(url=current, status=None, address_class=AddressClass.blocked)
            )
            outcome.stop = refusal(rejected, followed)
            break
        except ResolveError as error:
            outcome.stop = Finding("FETCH_DNS_ERROR", {"host": error.host})
            break

        response = await send_hop(target)
        contacted.append(target)
        outcome.hops.append(
            RedirectHop(url=target.url, status=response.status, address_class=target.address_class)
        )
        if not is_redirect(response):
            outcome.final_target, outcome.final_response = target, response
            break

        location = single_location(response)
        if location is None:
            outcome.stop = bad_target("conflicting Location headers")
            break
        try:
            candidate = next_url(target, location)
            scheme = urlsplit(candidate).scheme
        except ValueError:
            outcome.stop = bad_target("invalid address")
            break

        # (a) too many: the next target is never resolved or contacted
        if followed == settings.max_redirects:
            outcome.stop = Finding("REDIR_TOO_MANY", {"max_redirects": settings.max_redirects})
            break
        # (b) not a web link we follow
        kind = unsupported_link_kind(candidate)
        if kind is not None:
            outcome.stop = Finding("LINK_TYPE_UNSUPPORTED", {"link_kind": LINK_KIND_LABELS[kind]})
            break
        if scheme not in WEB_SCHEMES:
            outcome.stop = bad_target(scheme, scheme)
            break
        # (c) loop
        if candidate in visited:
            outcome.stop = Finding("REDIR_LOOP")
            break

        followed += 1
        downgrade = target.scheme == "https" and scheme == "http"
        if downgrade and not has_code(outcome, "REDIR_DOWNGRADE"):  # the first one only
            outcome.findings.append(Finding("REDIR_DOWNGRADE", {"hop": followed}))
        visited.add(candidate)
        current = candidate

    add_chain_facts(outcome, contacted, followed, settings)
    return outcome


def has_code(outcome: RedirectOutcome, code: str) -> bool:
    return any(f.code == code for f in outcome.findings)


def add_chain_facts(
    outcome: RedirectOutcome, contacted: list[Target], followed: int, settings: Settings
) -> None:
    """D49: long chain and cross-domain, reported even if the chain stopped. Hosts are
    compared in their punycode (ASCII) form; the Unicode form is only shown in messages."""
    if followed > settings.long_chain_hops:
        outcome.findings.append(Finding("REDIR_LONG_CHAIN", {"hops": followed}))
    hosts = [t.punycode_host.lower() for t in contacted]
    outcome.changed_host = any(a != b for a, b in zip(hosts, hosts[1:], strict=False))
    if outcome.changed_host:
        outcome.findings.append(
            Finding("REDIR_CROSS_DOMAIN", {"final_host": contacted[-1].display_host})
        )
