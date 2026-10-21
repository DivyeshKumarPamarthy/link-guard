"""SSRF rows that need a redirect (spec §5, task T1.4).

Every redirect target gets the full check_target, like the pasted URL. A public link that
redirects to an internal address stops at that hop with SSRF_BLOCKED_AT_HOP, the chain so
far is kept, and the blocked target is never contacted. No sockets: hops are answered by a
fake sender and names by the fake resolver (socket guard in conftest.py).
"""

import pytest

from app.contract.models import AddressClass
from app.core.config import Settings
from app.engine.fetcher.redirects import Finding, HopResponse, follow_redirects
from app.engine.fetcher.resolver import StaticHostsResolver
from app.engine.fetcher.targets import Target
from tests.ssrf.fakes import FakeResolver

START = "https://files.example/start"


class FakeHops:
    """Answers each contacted URL from a table (default: 200) and records what was sent."""

    def __init__(self, answers: dict[str, HopResponse]) -> None:
        self.answers = answers
        self.sent: list[str] = []

    async def send(self, target: Target) -> HopResponse:
        self.sent.append(target.url)
        return self.answers.get(target.url, HopResponse(200))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "location",
    [
        "http://127.0.0.1/",  # spec row: public URL that 302s to loopback
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
        "http://[::1]/",
        "http://0x7f.1/",  # disguised loopback, parsed strictly at the hop too
        "http://localtest.me/",  # public name that resolves to 127.0.0.1
        "http://mixed.example/",  # one public and one private record
        "//127.0.0.1/",  # scheme-relative: same scheme as the current hop
    ],
)
async def test_redirect_to_an_internal_address_is_blocked_at_the_hop(
    location: str, resolver: FakeResolver
) -> None:
    hops = FakeHops({START: HopResponse(302, (location,))})
    outcome = await follow_redirects(START, Settings(), resolver, hops.send)
    assert outcome.stop == Finding("SSRF_BLOCKED_AT_HOP", {"hop": 1})
    assert hops.sent == [START]  # the internal target was never contacted
    blocked_url = "https:" + location if location.startswith("//") else location
    assert [(h.url, h.status, h.address_class) for h in outcome.hops] == [
        (START, 302, AddressClass.public),
        (blocked_url, None, AddressClass.blocked),  # chain shown up to that hop
    ]
    assert outcome.final_target is None


@pytest.mark.asyncio
async def test_blocked_at_a_later_hop_keeps_the_whole_chain(resolver: FakeResolver) -> None:
    hops = FakeHops(
        {
            START: HopResponse(302, ("https://example.com/next",)),
            "https://example.com/next": HopResponse(301, ("http://10.0.0.5/",)),
        }
    )
    outcome = await follow_redirects(START, Settings(), resolver, hops.send)
    assert outcome.stop == Finding("SSRF_BLOCKED_AT_HOP", {"hop": 2})
    assert [h.url for h in outcome.hops] == [START, "https://example.com/next", "http://10.0.0.5/"]
    assert hops.sent == [START, "https://example.com/next"]


@pytest.mark.asyncio
async def test_every_hop_is_resolved_exactly_once(resolver: FakeResolver) -> None:
    """Rebinding at a hop: rebind.example answers public first, private on a second lookup.
    One lookup per hop means the hop is checked and contacted with the same answer."""
    hops = FakeHops({START: HopResponse(302, ("http://rebind.example/f",))})
    outcome = await follow_redirects(START, Settings(), resolver, hops.send)
    assert resolver.calls == ["files.example", "rebind.example"]
    assert outcome.stop is None
    assert outcome.final_target is not None
    assert str(outcome.final_target.ip) == "93.184.216.34"


@pytest.mark.asyncio
async def test_exempt_demo_name_cannot_redirect_to_the_demo_ip(resolver: FakeResolver) -> None:
    """The demo exemption covers the exact (name, port) only: a redirect from the exempt
    name to the same server's IP is still blocked."""
    settings = Settings(
        profile="test",
        static_hosts={"a.demo.test": "127.0.0.1"},
        ssrf_exempt=(("a.demo.test", 8081),),
        allowed_ports=(80, 443, 8081),
    )
    static = StaticHostsResolver(settings.static_hosts, fallback=resolver)
    start = "http://a.demo.test:8081/redirect/internal"
    hops = FakeHops({start: HopResponse(302, ("http://127.0.0.1:8081/f/sample.pdf",))})
    outcome = await follow_redirects(start, settings, static, hops.send)
    assert outcome.stop == Finding("SSRF_BLOCKED_AT_HOP", {"hop": 1})
    assert outcome.hops[0].address_class == AddressClass.private  # exempt, so contacted
    assert hops.sent == [start]
