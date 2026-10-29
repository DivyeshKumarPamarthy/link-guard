"""Table-driven unit tests for the link router (task T3.1, spec §6, M3 edge cases)."""

from pathlib import Path
from typing import Any

import pytest

from app.api.validation import InputError
from app.contract.models import (
    AddressClass,
    DisplayVerdict,
    ErrorCode,
    LinkType,
    RedirectHop,
    ScopeMode,
    Status,
    Verdict,
)
from app.core.config import Settings
from app.db.models import make_engine, make_session_factory
from app.engine.fetcher.fetch import FetchResult
from app.engine.fetcher.redirects import Finding
from app.engine.router import (
    Classification,
    classify,
    clean_url,
    cloud_share_service,
    is_homograph_host,
    is_html_body,
    is_web_page_headers,
    redirect_chain_view,
)
from app.orchestrator.executor import InProcessExecutor
from app.orchestrator.scans import Orchestrator, ScanStore
from app.registry.loader import get_registry
from tests.ssrf.fakes import FakeResolver

# --- 1. Input cleaning (M3 edge cases 1, 2, 3, 4, 17) -----------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  https://example.com/file.pdf  ", "https://example.com/file.pdf"),
        ('"https://example.com/file.pdf"', "https://example.com/file.pdf"),
        ("'https://example.com/file.pdf'", "https://example.com/file.pdf"),
        ("\u201chttps://example.com/file.pdf\u201d", "https://example.com/file.pdf"),
        ("<https://example.com/file.pdf>", "https://example.com/file.pdf"),
        ("(https://example.com/file.pdf)", "https://example.com/file.pdf"),
        ("https://example.com/file.pdf.", "https://example.com/file.pdf"),
        ("https://example.com/file.pdf,", "https://example.com/file.pdf"),
        ("https://example.com/file.pdf)", "https://example.com/file.pdf"),
        ("https://example.com/file.pdf).", "https://example.com/file.pdf"),
        # Balanced parentheses in a real path (e.g. Wikipedia/archive style) are preserved:
        ("https://example.com/file_(1).pdf", "https://example.com/file_(1).pdf"),
        ("https://example.com/file_(1).pdf)", "https://example.com/file_(1).pdf"),
        # Trailing dot on hostname before slash (SSRF row) stays intact:
        ("http://localhost./", "http://localhost./"),
        # Missing scheme assumes https://
        ("example.com/a.exe", "https://example.com/a.exe"),
        ("www.example.com/a.exe", "https://www.example.com/a.exe"),
        ("example.com:8080/a.exe", "https://example.com:8080/a.exe"),
        ("//cdn.example.com/a.exe", "https://cdn.example.com/a.exe"),
        # Uppercase scheme and host are lowercased; path and query case stay intact:
        ("HTTP://Example.COM/MyFile.PDF?Token=AbC", "http://example.com/MyFile.PDF?Token=AbC"),
        ("HTTPS://FILES.EXAMPLE:8443/Path/To/File", "https://files.example:8443/Path/To/File"),
        # Backslashes in path/authority are normalized to forward slashes:
        (r"https://example.com\downloads\setup.exe", "https://example.com/downloads/setup.exe"),
        (
            r"example.com\downloads\setup.exe?a=b\c",
            r"https://example.com/downloads/setup.exe?a=b\c",
        ),
        # Percent-encoded host is kept untouched so check_target refuses `%` in host (D38):
        ("http://%31%32%37.0.0.1/", "http://%31%32%37.0.0.1/"),
    ],
)
def test_clean_url_normalizes_pasted_input(raw: str, expected: str) -> None:
    assert clean_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        '""',
        "<>",
        "...",
    ],
)
def test_clean_url_rejects_empty_input(raw: str) -> None:
    with pytest.raises(InputError) as exc_info:
        clean_url(raw, max_length=2048)
    assert exc_info.value.code == ErrorCode.URL_EMPTY


@pytest.mark.parametrize(
    "raw",
    [
        "https://a.example/1.pdf https://b.example/2.pdf",
        "<https://a.example/1.pdf> <https://b.example/2.pdf>",
        "a.example/1.pdf b.example/2.pdf",
        "magnet:?xt=urn:btih:1 https://b.example/2.pdf",
    ],
)
def test_clean_url_rejects_multiple_urls(raw: str) -> None:
    with pytest.raises(InputError) as exc_info:
        clean_url(raw, max_length=2048)
    assert exc_info.value.code == ErrorCode.URL_MULTIPLE


def test_clean_url_enforces_max_length() -> None:
    too_long = "https://example.com/" + "a" * 2040
    with pytest.raises(InputError) as exc_info:
        clean_url(too_long, max_length=2048)
    assert exc_info.value.code == ErrorCode.URL_TOO_LONG


# --- 2. Pure classify() function (spec §6, D6, D50, M3 edge cases 11, 12) ---------------


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://example.com/file.pdf",
            Classification(action="fetch", link_type=LinkType.http, finding=None),
        ),
        (
            "http://example.com/download?id=42",
            Classification(action="fetch", link_type=LinkType.http, finding=None),
        ),
        (
            "magnet:?xt=urn:btih:0123456789abcdef",
            Classification(
                action="unsupported",
                link_type=LinkType.magnet,
                finding=Finding("LINK_TYPE_UNSUPPORTED", {"link_kind": "Magnet links"}),
            ),
        ),
        (
            "ftp://ftp.example.com/pub/file.zip",
            Classification(
                action="unsupported",
                link_type=LinkType.ftp,
                finding=Finding("LINK_TYPE_UNSUPPORTED", {"link_kind": "FTP links"}),
            ),
        ),
        (
            "https://mirror.example.com/ubuntu-24.04.iso.TORRENT?dl=1",
            Classification(
                action="unsupported",
                link_type=LinkType.torrent,
                finding=Finding("LINK_TYPE_UNSUPPORTED", {"link_kind": "Torrent files"}),
            ),
        ),
        (
            "intent://scan/#Intent;scheme=zxing;package=com.example;end",
            Classification(
                action="unsupported",
                link_type=LinkType.other,
                finding=Finding("LINK_TYPE_UNSUPPORTED", {"link_kind": "App links (intent:)"}),
            ),
        ),
        (
            "file:///etc/passwd",
            Classification(
                action="rejected",
                link_type=LinkType.other,
                finding=Finding("URL_SCHEME_UNSUPPORTED", {"scheme": "file"}),
            ),
        ),
        (
            "gopher://gopher.example.com/",
            Classification(
                action="rejected",
                link_type=LinkType.other,
                finding=Finding("URL_SCHEME_UNSUPPORTED", {"scheme": "gopher"}),
            ),
        ),
        (
            "data:text/plain;base64,SGVsbG8=",
            Classification(
                action="rejected",
                link_type=LinkType.other,
                finding=Finding("URL_SCHEME_UNSUPPORTED", {"scheme": "data"}),
            ),
        ),
        (
            "javascript:alert(1)",
            Classification(
                action="rejected",
                link_type=LinkType.other,
                finding=Finding("URL_SCHEME_UNSUPPORTED", {"scheme": "javascript"}),
            ),
        ),
        (
            "blob:https://example.com/550e8400-e29b-41d4-a716-446655440000",
            Classification(
                action="rejected",
                link_type=LinkType.other,
                finding=Finding("URL_SCHEME_UNSUPPORTED", {"scheme": "blob"}),
            ),
        ),
        (
            "https:///path-without-host",
            Classification(
                action="rejected",
                link_type=LinkType.http,
                finding=Finding("URL_INVALID"),
            ),
        ),
        (
            "http://[::1",
            Classification(
                action="rejected",
                link_type=LinkType.http,
                finding=Finding("URL_INVALID"),
            ),
        ),
    ],
)
def test_classify_is_pure_and_covers_all_link_kinds(url: str, expected: Classification) -> None:
    assert classify(url) == expected


# --- 3. Web-page detection (headers + HTML body sniff, M3 edge cases 5, 6, 14, 15) -------


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"content-type": "text/html; charset=utf-8"}, True),
        ({"content-type": "application/xhtml+xml"}, True),
        ({"content-type": "text/html", "content-disposition": "inline"}, True),
        (
            {
                "content-type": "text/html",
                "content-disposition": 'attachment; filename="page.html"',
            },
            False,
        ),
        ({"content-type": "application/pdf"}, False),
    ],
)
def test_web_page_header_detection(headers: dict[str, str], expected: bool) -> None:
    assert is_web_page_headers(headers) is expected


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (b"<!DOCTYPE html><html><body>Error</body></html>", True),
        (b"   \n\t<!doctype html>\n<html></html>", True),
        (b"\xef\xbb\xbf<html lang='en'><head></head></html>", True),
        (b"\xff\xfe" + "<html><body>UTF-16</body></html>".encode("utf-16-le"), True),
        (b"<!-- comment -->\n<html><body>Index of /</body></html>", True),
        (b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\n", False),
        (b"console.log('<html>not at start');", False),
        (b" " * 1024 + b"<!doctype html>", False),  # beyond 1 KB window
        (b"", False),
    ],
)
def test_html_body_sniff(body: bytes, expected: bool) -> None:
    assert is_html_body(body) is expected


# --- 4. Cloud-share hints (P1, M3 edge case 14) ------------------------------------------


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("drive.google.com", "Google Drive"),
        ("docs.google.com", "Google Drive"),
        ("www.dropbox.com", "Dropbox"),
        ("dropbox.com", "Dropbox"),
        ("onedrive.live.com", "OneDrive"),
        ("1drv.ms", "OneDrive"),
        ("contoso.sharepoint.com", "OneDrive"),
        ("mega.nz", "Mega"),
        ("files.example.com", None),
        (None, None),
    ],
)
def test_cloud_share_service(host: str | None, expected: str | None) -> None:
    assert cloud_share_service(host) == expected


# --- 5. Homograph detection (P1, M3 edge case 16) ----------------------------------------


@pytest.mark.parametrize(
    ("display_host", "punycode_host", "expected"),
    [
        # Mixed Cyrillic 'а' (U+0430) + Latin 'pple':
        ("\u0430pple.com", "xn--pple-43d.com", True),
        # Whole label of Cyrillic confusables under .com:
        ("\u0430\u0440\u0440\u04cf\u0435.com", "xn--80ak6aa92e.com", True),
        # Greek alpha + Latin:
        ("\u03b1pple.com", "xn--pple-via.com", True),
        # Legitimate single-script Latin IDN (German umlaut):
        ("b\u00fccher.example", "xn--bcher-kva.example", False),
        ("m\u00fcnchen.de", "xn--mnchen-3ya.de", False),
        # Plain ASCII domain:
        ("apple.com", "apple.com", False),
    ],
)
def test_homograph_host_detection(display_host: str, punycode_host: str, expected: bool) -> None:
    assert is_homograph_host(display_host, punycode_host) is expected


# --- 6. Redirect-chain view model & full router-in-orchestrator flows --------------------


def test_redirect_chain_view_hides_single_blocked_hop_and_keeps_multi_hop() -> None:
    hop0_blocked = [
        RedirectHop(url="http://127.0.0.1/", status=None, address_class=AddressClass.blocked)
    ]
    assert redirect_chain_view(hop0_blocked, Status.rejected) == []

    chain_blocked = [
        RedirectHop(url="https://short.example/a", status=302, address_class=AddressClass.public),
        RedirectHop(url="http://127.0.0.1/", status=None, address_class=AddressClass.blocked),
    ]
    assert redirect_chain_view(chain_blocked, Status.rejected) == chain_blocked


@pytest.mark.asyncio
async def test_router_in_executor_handles_html_sniff_cloud_share_and_homograph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Row 7 (HTML error page served as file.pdf with application/pdf) plus P1 cloud-share
    and homograph flags; verifies LINK_IS_WEB_PAGE is never emitted twice."""
    html_bytes = b"<!DOCTYPE html>\n<html><body>Drive virus scan warning</body></html>"

    async def fake_fetch(url: str, settings: Settings, resolver: Any) -> FetchResult:
        return FetchResult(
            body_head=html_bytes,
            bytes_read=len(html_bytes),
            total_size=len(html_bytes),
            range_supported=True,
            ended="complete",
            status_code=200,
            headers={"content-type": "application/pdf"},
            hops=[RedirectHop(url=url, status=200, address_class=AddressClass.public)],
            final_url=url,
            display_host="drive.google.com",
            punycode_host="drive.google.com",
        )

    monkeypatch.setattr("app.orchestrator.executor.fetch", fake_fetch)
    registry = get_registry()
    store = ScanStore(
        make_session_factory(make_engine(f"sqlite:///{tmp_path / 'r.db'}")),
        registry.rules_version,
    )
    orch = Orchestrator(store, InProcessExecutor(Settings(), resolver=FakeResolver({})), registry)

    queued = orch.submit("  <https://drive.google.com/file.pdf.>  ")
    await orch.wait_for_running_scans()
    result = store.get(str(queued.scan_id))
    assert result is not None
    assert result.normalized_url == "https://drive.google.com/file.pdf"
    assert result.verdict == Verdict.UNABLE_TO_VERIFY
    assert result.display_verdict == DisplayVerdict.UNABLE_TO_VERIFY
    assert result.scope is not None and result.scope.mode == ScopeMode.full
    codes = [r.code for r in result.reasons or []]
    assert codes.count("LINK_IS_WEB_PAGE") == 1
    assert "LINK_CLOUD_SHARE_PAGE" in codes
    # Mismatch checks must not run on an HTML page:
    assert "TYPE_MISMATCH_TEXT" not in codes
    assert "TYPE_CONTENT_TYPE_MISMATCH" not in codes
