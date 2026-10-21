"""Redirect handling (task T1.4, spec §5-§6, decisions D6, D8, D38, D45-D50).

Unit tests use a fake hop sender and the fake resolver (no sockets). The integration tests
at the end follow the demo server's real redirect endpoints (D44).
"""

import pytest

from app.contract.models import AddressClass, LinkType
from app.core.config import Settings
from app.engine.fetcher.pinned import build_pinned_request, new_client, tls_context
from app.engine.fetcher.redirects import (
    Finding,
    HopResponse,
    RedirectOutcome,
    follow_redirects,
    unsupported_link_kind,
)
from app.engine.fetcher.resolver import Resolver
from app.engine.fetcher.targets import Target
from tests.demo_server import Demo, RecordingResolver
from tests.ssrf.fakes import FAKE_DNS, FakeResolver

START = "https://files.example/start"
INVALID_TARGET = Finding(
    "REDIR_BAD_TARGET", {"reason": "it is not a valid web address", "detail": "invalid address"}
)


class FakeHops:
    """Answers each contacted URL from a table (default: 200) and records what was sent."""

    def __init__(self, answers: dict[str, HopResponse]) -> None:
        self.answers = answers
        self.sent: list[str] = []

    async def send(self, target: Target) -> HopResponse:
        self.sent.append(target.url)
        return self.answers.get(target.url, HopResponse(200))


def resolver() -> FakeResolver:
    dns = dict(FAKE_DNS)
    dns["cdn.example"] = [["93.184.216.40"]]
    dns["xn--bcher-kva.example"] = [["93.184.216.36"]]
    return FakeResolver(dns)


async def follow(
    answers: dict[str, HopResponse],
    start: str = START,
    settings: Settings | None = None,
    dns: Resolver | None = None,
) -> tuple[RedirectOutcome, FakeHops]:
    hops = FakeHops(answers)
    outcome = await follow_redirects(start, settings or Settings(), dns or resolver(), hops.send)
    return outcome, hops


def chain(count: int) -> dict[str, HopResponse]:
    """START -> /r1 -> /r2 -> ... -> /r<count>, each a 302 on the same host."""
    urls = [START] + [f"https://files.example/r{i}" for i in range(1, count + 1)]
    return {urls[i]: HopResponse(302, (urls[i + 1],)) for i in range(count)}


# --- no redirect, and which responses are redirects ---------------------------------------


@pytest.mark.asyncio
async def test_no_redirect_gives_one_hop_and_the_final_response() -> None:
    outcome, hops = await follow({})
    assert outcome.stop is None
    assert outcome.findings == []
    assert [(h.url, h.status, h.address_class) for h in outcome.hops] == [
        (START, 200, AddressClass.public)
    ]
    assert outcome.final_target is not None and outcome.final_target.url == START
    assert outcome.final_response == HopResponse(200)
    assert outcome.changed_host is False
    assert hops.sent == [START]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
async def test_redirect_statuses_are_followed(status: int) -> None:
    outcome, hops = await follow({START: HopResponse(status, ("/next",))})
    assert hops.sent == [START, "https://files.example/next"]
    assert outcome.final_response == HopResponse(200)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        HopResponse(300, ("/next",)),  # not a redirect status in the Fetch standard
        HopResponse(304, ("/next",)),
        HopResponse(302),  # no Location
        HopResponse(302, ("   ",)),  # empty after trimming
    ],
)
async def test_other_responses_are_final(response: HopResponse) -> None:
    """T2.1 maps these final statuses (never to SAFE)."""
    outcome, hops = await follow({START: response})
    assert hops.sent == [START]
    assert outcome.stop is None
    assert outcome.final_response == response


# --- building the next URL ----------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("location", "expected"),
    [
        ("/next", "https://files.example/next"),
        ("next?x=1", "https://files.example/next?x=1"),
        ("../up", "https://files.example/up"),
        ("//cdn.example/f", "https://cdn.example/f"),  # scheme-relative
        ("  https://cdn.example/f  ", "https://cdn.example/f"),  # surrounding spaces
        ("https://cdn.example/f#part", "https://cdn.example/f"),  # fragment dropped
    ],
)
async def test_location_is_resolved_against_the_current_url(location: str, expected: str) -> None:
    outcome, hops = await follow({START: HopResponse(302, (location,))})
    assert hops.sent == [START, expected]
    assert outcome.hops[1].url == expected


# --- too many redirects, loops --------------------------------------------------------------


@pytest.mark.asyncio
async def test_five_redirects_are_followed() -> None:
    outcome, hops = await follow(chain(5))
    assert outcome.stop is None
    assert len(hops.sent) == 6


@pytest.mark.asyncio
async def test_a_sixth_redirect_is_too_many_and_its_target_is_never_checked() -> None:
    dns = resolver()
    outcome, hops = await follow(chain(6), dns=dns)
    assert outcome.stop == Finding("REDIR_TOO_MANY", {"max_redirects": 5})
    assert len(hops.sent) == 6  # the start and 5 redirect targets
    assert "https://files.example/r6" not in [h.url for h in outcome.hops]
    assert len(dns.calls) == 6
    assert outcome.final_target is None


@pytest.mark.asyncio
async def test_max_redirects_comes_from_config() -> None:
    outcome, _ = await follow(chain(2), settings=Settings(max_redirects=1))
    assert outcome.stop == Finding("REDIR_TOO_MANY", {"max_redirects": 1})


@pytest.mark.asyncio
async def test_loop_between_two_urls() -> None:
    other = "https://files.example/b"
    outcome, hops = await follow(
        {START: HopResponse(302, ("/b",)), other: HopResponse(302, ("/start",))}
    )
    assert outcome.stop == Finding("REDIR_LOOP", {})
    assert hops.sent == [START, other]


@pytest.mark.asyncio
async def test_redirect_to_itself_is_a_loop_even_with_a_fragment() -> None:
    outcome, hops = await follow({START: HopResponse(302, ("/start#again",))})
    assert outcome.stop == Finding("REDIR_LOOP", {})
    assert hops.sent == [START]


# --- targets that are not followed ---------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("location", "scheme"),
    [
        ("javascript:alert(1)", "javascript"),
        ("file:///etc/passwd", "file"),
        ("data:text/plain,hi", "data"),
        ("gopher://x/", "gopher"),
    ],
)
async def test_non_web_target_is_a_bad_target(location: str, scheme: str) -> None:
    dns = resolver()
    outcome, hops = await follow({START: HopResponse(302, (location,))}, dns=dns)
    assert outcome.stop == Finding(
        "REDIR_BAD_TARGET", {"reason": f"it uses the {scheme}: scheme", "detail": scheme}
    )
    assert hops.sent == [START]
    assert dns.calls == ["files.example"]
    assert len(outcome.hops) == 1  # never checked, so not listed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("location", "label"),
    [
        ("magnet:?xt=urn:btih:abc", "Magnet links"),
        ("ftp://files.example/a.zip", "FTP links"),
        ("intent://scan/#Intent;scheme=zxing;end", "App links (intent:)"),
        ("/file.torrent", "Torrent files"),
        ("https://cdn.example/FILE.TORRENT?x=1", "Torrent files"),
    ],
)
async def test_unsupported_target_is_not_followed(location: str, label: str) -> None:
    """D6, plus .torrent (mentor decision): a short link to a torrent must not get a
    different answer than pasting the torrent link itself."""
    outcome, hops = await follow({START: HopResponse(302, (location,))})
    assert outcome.stop == Finding("LINK_TYPE_UNSUPPORTED", {"link_kind": label})
    assert hops.sent == [START]


@pytest.mark.parametrize(
    ("url", "kind"),
    [
        ("magnet:?xt=urn:btih:abc", LinkType.magnet),
        ("FTP://files.example/a", LinkType.ftp),
        ("intent://x", LinkType.other),
        ("https://files.example/a.torrent", LinkType.torrent),
        ("https://files.example/a.torrent/", None),
        ("https://files.example/a.zip", None),
        ("https://files.example/?f=a.torrent", None),  # only the path counts
        ("javascript:alert(1)", None),  # rejected, not unsupported
    ],
)
def test_unsupported_link_kind(url: str, kind: LinkType | None) -> None:
    assert unsupported_link_kind(url) is kind


# --- check_target refusals at a hop (hop >= 1) ----------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("location", "stop"),
    [
        ("https://example.com:6379/", Finding("URL_PORT_BLOCKED", {"port": 6379})),
        ("https://user:pw@example.com/", Finding("URL_USERINFO", {})),
        ("http://256.1.1.1/", INVALID_TARGET),  # D38
        ("https://exa%2Dmple.com/", INVALID_TARGET),
    ],
)
async def test_other_refusals_at_a_hop_keep_the_chain(location: str, stop: Finding) -> None:
    outcome, hops = await follow({START: HopResponse(302, (location,))})
    assert outcome.stop == stop
    assert hops.sent == [START]
    assert outcome.hops[-1].status is None
    assert outcome.hops[-1].address_class == AddressClass.blocked


@pytest.mark.asyncio
async def test_location_longer_than_the_url_limit_is_a_bad_target() -> None:
    """D38: the length limit applies to every hop, not only the pasted URL."""
    settings = Settings(max_url_length=60)
    long_location = "/" + "a" * 60
    outcome, hops = await follow({START: HopResponse(302, (long_location,))}, settings=settings)
    assert outcome.stop == INVALID_TARGET
    assert hops.sent == [START]


@pytest.mark.asyncio
async def test_two_different_location_headers_are_a_bad_target() -> None:
    """Clients disagree on which of two Location headers wins, so a check could approve one
    target while another client follows the other: refuse, never pick one."""
    outcome, hops = await follow(
        {START: HopResponse(302, ("https://cdn.example/f", "http://127.0.0.1/"))}
    )
    assert outcome.stop == Finding(
        "REDIR_BAD_TARGET",
        {"reason": "it is not a valid web address", "detail": "conflicting Location headers"},
    )
    assert hops.sent == [START]


@pytest.mark.asyncio
async def test_repeated_identical_location_headers_are_followed() -> None:
    outcome, hops = await follow({START: HopResponse(302, ("/next", " /next"))})
    assert outcome.stop is None
    assert hops.sent == [START, "https://files.example/next"]


@pytest.mark.asyncio
async def test_dns_failure_at_a_hop_is_unable_to_verify() -> None:
    outcome, hops = await follow({START: HopResponse(302, ("https://no-such-host.example/f",))})
    assert outcome.stop == Finding("FETCH_DNS_ERROR", {"host": "no-such-host.example"})
    assert len(outcome.hops) == 1  # "blocked" would be untrue: nothing was refused
    assert hops.sent == [START]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("start", "stop"),
    [
        ("http://127.0.0.1/", Finding("URL_PRIVATE_ADDRESS", {})),
        ("https://example.com:22/", Finding("URL_PORT_BLOCKED", {"port": 22})),
        ("gopher://x/", Finding("URL_SCHEME_UNSUPPORTED", {"scheme": "gopher"})),
        (
            "https://no-such-host.example/",
            Finding("FETCH_DNS_ERROR", {"host": "no-such-host.example"}),
        ),
    ],
)
async def test_the_pasted_url_keeps_its_own_codes(start: str, stop: Finding) -> None:
    outcome, hops = await follow({}, start=start)
    assert outcome.stop == stop
    assert hops.sent == []


# --- facts about the chain: downgrade, long chain, cross-domain ----------------------------


@pytest.mark.asyncio
async def test_https_to_http_is_a_downgrade_at_that_hop() -> None:
    second = "https://files.example/b"
    outcome, _ = await follow(
        {
            START: HopResponse(302, ("/b",)),
            second: HopResponse(302, ("http://files.example/c",)),
            "http://files.example/c": HopResponse(302, ("https://files.example/d",)),
            "https://files.example/d": HopResponse(302, ("http://files.example/e",)),
        }
    )
    assert Finding("REDIR_DOWNGRADE", {"hop": 2}) in outcome.findings
    assert [f.code for f in outcome.findings].count("REDIR_DOWNGRADE") == 1  # first only


@pytest.mark.asyncio
async def test_more_than_three_redirects_is_a_long_chain() -> None:
    outcome, _ = await follow(chain(4))
    assert Finding("REDIR_LONG_CHAIN", {"hops": 4}) in outcome.findings
    outcome, _ = await follow(chain(3))
    assert all(f.code != "REDIR_LONG_CHAIN" for f in outcome.findings)


@pytest.mark.asyncio
async def test_redirect_to_another_host_is_cross_domain() -> None:
    outcome, _ = await follow({START: HopResponse(302, ("https://cdn.example/f",))})
    assert outcome.changed_host is True
    assert Finding("REDIR_CROSS_DOMAIN", {"final_host": "cdn.example"}) in outcome.findings


@pytest.mark.asyncio
async def test_same_host_in_other_case_is_not_cross_domain() -> None:
    outcome, _ = await follow({START: HopResponse(302, ("https://FILES.example/f",))})
    assert outcome.changed_host is False
    assert outcome.findings == []


@pytest.mark.asyncio
async def test_final_host_is_shown_in_its_display_form() -> None:
    outcome, _ = await follow({START: HopResponse(302, ("https://bücher.example/f",))})
    assert Finding("REDIR_CROSS_DOMAIN", {"final_host": "bücher.example"}) in outcome.findings


@pytest.mark.asyncio
async def test_facts_are_kept_when_the_chain_later_stops() -> None:
    outcome, _ = await follow(
        {
            START: HopResponse(302, ("http://cdn.example/a",)),
            "http://cdn.example/a": HopResponse(302, ("http://10.0.0.5/",)),
        }
    )
    assert outcome.stop == Finding("SSRF_BLOCKED_AT_HOP", {"hop": 2})
    codes = {f.code for f in outcome.findings}
    assert codes == {"REDIR_DOWNGRADE", "REDIR_CROSS_DOMAIN"}


# --- integration: the demo server's redirect endpoints (D44) -------------------------------


async def head_hop(settings: Settings, target: Target) -> HopResponse:
    """A minimal real hop for these tests (T2.1 adds the GET fallback and streaming)."""
    async with new_client(settings, tls_context(settings)) as client:
        response = await client.send(build_pinned_request(client, target, "HEAD", {}))
    return HopResponse(response.status_code, tuple(response.headers.get_list("location")))


async def follow_demo(demo: Demo, url: str) -> tuple[RedirectOutcome, RecordingResolver]:
    settings = demo.settings()
    dns = RecordingResolver(settings)
    outcome = await follow_redirects(url, settings, dns, lambda t: head_hop(settings, t))
    return outcome, dns


@pytest.mark.integration
@pytest.mark.allow_hosts(["127.0.0.1"])
@pytest.mark.asyncio
async def test_demo_chain_across_three_hosts(demo: Demo) -> None:
    """Acceptance row 8: a -> b -> c, then the file; cross-domain, one lookup per hop."""
    outcome, dns = await follow_demo(
        demo, f"http://a.demo.test:{demo.http_port}/redirect/chain?n=2&to=/page"
    )
    assert outcome.stop is None
    assert outcome.final_response is not None and outcome.final_response.status == 200
    assert dns.calls == ["a.demo.test", "b.demo.test", "c.demo.test"]
    assert outcome.changed_host is True
    assert Finding("REDIR_CROSS_DOMAIN", {"final_host": "c.demo.test"}) in outcome.findings


@pytest.mark.integration
@pytest.mark.allow_hosts(["127.0.0.1"])
@pytest.mark.asyncio
async def test_demo_loop(demo: Demo) -> None:
    """Acceptance row 10."""
    outcome, _ = await follow_demo(demo, f"http://a.demo.test:{demo.http_port}/redirect/loop")
    assert outcome.stop == Finding("REDIR_LOOP", {})


@pytest.mark.integration
@pytest.mark.allow_hosts(["127.0.0.1"])
@pytest.mark.asyncio
async def test_demo_redirect_to_localhost_is_blocked_at_hop_1(demo: Demo) -> None:
    """Acceptance row 11: the chain is listed up to the blocked hop."""
    outcome, _ = await follow_demo(demo, f"http://a.demo.test:{demo.http_port}/redirect/internal")
    assert outcome.stop == Finding("SSRF_BLOCKED_AT_HOP", {"hop": 1})
    assert [h.url for h in outcome.hops] == [
        f"http://a.demo.test:{demo.http_port}/redirect/internal",
        "http://127.0.0.1/",
    ]


@pytest.mark.integration
@pytest.mark.allow_hosts(["127.0.0.1"])
@pytest.mark.asyncio
async def test_demo_https_to_http_downgrade(demo: Demo) -> None:
    outcome, _ = await follow_demo(
        demo, f"https://a.demo.test:{demo.https_port}/redirect/https-to-http?to=/page"
    )
    assert outcome.stop is None
    assert Finding("REDIR_DOWNGRADE", {"hop": 1}) in outcome.findings


@pytest.mark.integration
@pytest.mark.allow_hosts(["127.0.0.1"])
@pytest.mark.asyncio
async def test_demo_too_many_redirects(demo: Demo) -> None:
    outcome, _ = await follow_demo(
        demo, f"http://a.demo.test:{demo.http_port}/redirect/chain?n=6&to=/page"
    )
    assert outcome.stop == Finding("REDIR_TOO_MANY", {"max_redirects": 5})
