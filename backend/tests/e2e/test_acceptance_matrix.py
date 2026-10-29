"""End-to-end acceptance matrix against the local demo server (task T3.3, spec §12).

One test per row of spec §12 (rows 1–22, with 18a/18b/18c for the three unsupported link
kinds). Runs the full backend (API -> Orchestrator -> InProcessExecutor -> Router ->
Fetcher -> Detectors -> Scorer -> SQLite) against the real demo server in the `test`
profile, with all network access blocked except loopback (`127.0.0.1`).

Per spec §12: assert `status`, `verdict`, `display_verdict`, `confidence`, `scope.mode` and
required reason codes — never exact scores.
"""

import shutil
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.contract.models import ScanResult
from app.core.config import Settings
from app.main import create_app
from tests.demo_server import Demo

pytestmark = [
    pytest.mark.integration,
    pytest.mark.allow_hosts(["127.0.0.1"]),
]

REPO_ROOT = Path(__file__).resolve().parents[3]
REPO_SAMPLES = REPO_ROOT / "samples"


@pytest.fixture(scope="module", autouse=True)
def populate_demo_samples(demo: Demo) -> None:
    """Copy the generated samples into the session demo server's samples directory."""
    if not (REPO_SAMPLES / "sample.pdf").is_file():
        pytest.fail("samples/ missing. Run `make samples` before running e2e tests.")
    for item in REPO_SAMPLES.iterdir():
        target = demo.samples_dir / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def make_e2e_settings(demo: Demo, tmp_path: Path, **overrides: Any) -> Settings:
    base = demo.settings()
    updates: dict[str, Any] = {
        "database_url": f"sqlite:///{tmp_path / 'e2e.db'}",
        "poll_after_ms": 20,
    }
    updates.update(overrides)
    return base.model_copy(update=updates)


def run_scan(demo: Demo, tmp_path: Path, url: str, **setting_overrides: Any) -> dict[str, Any]:
    """Submit `url` to `POST /api/scans` and poll `GET /api/scans/{id}` until `done`."""
    settings = make_e2e_settings(demo, tmp_path, **setting_overrides)
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/scans", json={"url": url})
        assert response.status_code == 202, response.text
        scan_id = response.json()["scan_id"]

        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            poll = client.get(f"/api/scans/{scan_id}")
            assert poll.status_code == 200
            body: dict[str, Any] = poll.json()
            ScanResult.model_validate(body)
            if body["state"] == "done":
                return body
            time.sleep(0.02)
    raise AssertionError(f"scan for {url} did not finish within 25s")


def assert_outcome(
    result: dict[str, Any],
    *,
    status: str,
    verdict: str | None,
    display_verdict: str,
    confidence: str | None,
    scope_mode: str,
    required_codes: list[str] | None = None,
    expect_no_reasons: bool = False,
) -> None:
    assert result["status"] == status
    assert result["verdict"] == verdict
    assert result["display_verdict"] == display_verdict
    assert result["confidence"] == confidence
    assert result["scope"]["mode"] == scope_mode
    codes = [r["code"] for r in (result["reasons"] or [])]
    if expect_no_reasons:
        assert codes == []
    for code in required_codes or []:
        assert code in codes, f"expected {code!r} in {codes}"


# --- Rows 1–7: direct file checks and disguises ------------------------------------------


def test_row_01_genuine_small_pdf(demo: Demo, tmp_path: Path) -> None:
    result = run_scan(demo, tmp_path, f"http://a.demo.test:{demo.http_port}/f/sample.pdf")
    assert_outcome(
        result,
        status="completed",
        verdict="SAFE",
        display_verdict="SAFE",
        confidence="high",
        scope_mode="full",
        expect_no_reasons=True,
    )


def test_row_02_large_mp4_with_range(demo: Demo, tmp_path: Path) -> None:
    result = run_scan(demo, tmp_path, f"http://a.demo.test:{demo.http_port}/big?range=yes")
    assert_outcome(
        result,
        status="completed",
        verdict="SAFE",
        display_verdict="NO_ISSUES_IN_CHECKED_PART",
        confidence="medium",
        scope_mode="partial",
        required_codes=["SCAN_PARTIAL"],
    )
    assert result["scope"]["range_supported"] is True


def test_row_03_disguised_movie_mp4_is_pe(demo: Demo, tmp_path: Path) -> None:
    result = run_scan(demo, tmp_path, f"http://a.demo.test:{demo.http_port}/disguised/movie.mp4")
    assert_outcome(
        result,
        status="completed",
        verdict="UNSAFE",
        display_verdict="UNSAFE",
        confidence="high",
        scope_mode="full",
        required_codes=["TYPE_MISMATCH_EXEC"],
    )


def test_row_04_genuine_pe_with_double_extension(demo: Demo, tmp_path: Path) -> None:
    result = run_scan(
        demo, tmp_path, f"http://a.demo.test:{demo.http_port}/disguised/invoice.pdf.exe"
    )
    assert_outcome(
        result,
        status="completed",
        verdict="SUSPICIOUS",
        display_verdict="SUSPICIOUS",
        confidence="high",
        scope_mode="full",
        required_codes=["EXT_DOUBLE"],
    )


def test_row_05_png_named_photo_jpg(demo: Demo, tmp_path: Path) -> None:
    result = run_scan(demo, tmp_path, f"http://a.demo.test:{demo.http_port}/disguised/photo.jpg")
    assert_outcome(
        result,
        status="completed",
        verdict="SAFE",
        display_verdict="SAFE",
        confidence="high",
        scope_mode="full",
        required_codes=["TYPE_MISMATCH_OTHER"],
    )


def test_row_06_plain_zip_named_report_docx(demo: Demo, tmp_path: Path) -> None:
    result = run_scan(demo, tmp_path, f"http://a.demo.test:{demo.http_port}/disguised/report.docx")
    assert_outcome(
        result,
        status="completed",
        verdict="SAFE",
        display_verdict="SAFE",
        confidence="high",
        scope_mode="full",
        required_codes=["TYPE_MISMATCH_OTHER"],
    )


def test_row_07_html_error_page_served_as_pdf(demo: Demo, tmp_path: Path) -> None:
    result = run_scan(demo, tmp_path, f"http://a.demo.test:{demo.http_port}/disguised/file.pdf")
    assert_outcome(
        result,
        status="completed",
        verdict="UNABLE_TO_VERIFY",
        display_verdict="UNABLE_TO_VERIFY",
        confidence="low",
        scope_mode="full",
        required_codes=["LINK_IS_WEB_PAGE"],
    )


# --- Rows 8–12: redirects and SSRF blocks ------------------------------------------------


def test_row_08_two_hop_chain_to_clean_pdf(demo: Demo, tmp_path: Path) -> None:
    result = run_scan(
        demo,
        tmp_path,
        f"http://a.demo.test:{demo.http_port}/redirect/chain?n=2&to=/f/sample.pdf",
    )
    assert_outcome(
        result,
        status="completed",
        verdict="SAFE",
        display_verdict="SAFE",
        confidence="high",
        scope_mode="full",
        required_codes=["REDIR_CROSS_DOMAIN"],
    )
    assert result["link_type"] == "shortened"


def test_row_09_two_hop_chain_to_disguised_pe(demo: Demo, tmp_path: Path) -> None:
    result = run_scan(
        demo,
        tmp_path,
        f"http://a.demo.test:{demo.http_port}/redirect/chain?n=2&to=/disguised/movie.mp4",
    )
    assert_outcome(
        result,
        status="completed",
        verdict="UNSAFE",
        display_verdict="UNSAFE",
        confidence="high",
        scope_mode="full",
        required_codes=["TYPE_MISMATCH_EXEC"],
    )
    assert result["link_type"] == "shortened"


def test_row_10_redirect_loop(demo: Demo, tmp_path: Path) -> None:
    result = run_scan(demo, tmp_path, f"http://a.demo.test:{demo.http_port}/redirect/loop")
    assert_outcome(
        result,
        status="completed",
        verdict="UNABLE_TO_VERIFY",
        display_verdict="UNABLE_TO_VERIFY",
        confidence="low",
        scope_mode="none",
        required_codes=["REDIR_LOOP"],
    )


def test_row_11_redirect_to_loopback_blocked_at_hop(demo: Demo, tmp_path: Path) -> None:
    result = run_scan(demo, tmp_path, f"http://a.demo.test:{demo.http_port}/redirect/internal")
    assert_outcome(
        result,
        status="rejected",
        verdict=None,
        display_verdict="REJECTED",
        confidence=None,
        scope_mode="none",
        required_codes=["SSRF_BLOCKED_AT_HOP"],
    )
    assert len(result["redirects"]) == 2
    assert result["redirects"][-1]["address_class"] == "blocked"


def test_row_12_cloud_metadata_private_address_rejected(demo: Demo, tmp_path: Path) -> None:
    result = run_scan(demo, tmp_path, "http://169.254.169.254/latest/meta-data/")
    assert_outcome(
        result,
        status="rejected",
        verdict=None,
        display_verdict="REJECTED",
        confidence=None,
        scope_mode="none",
        required_codes=["URL_PRIVATE_ADDRESS"],
    )


# --- Rows 13–22: range-ignored, slow, errors, web page, unsupported, empty, gzip, TLS ----


def test_row_13_large_file_server_ignores_range(demo: Demo, tmp_path: Path) -> None:
    result = run_scan(demo, tmp_path, f"http://a.demo.test:{demo.http_port}/big?range=no")
    assert_outcome(
        result,
        status="completed",
        verdict="SAFE",
        display_verdict="NO_ISSUES_IN_CHECKED_PART",
        confidence="low",
        scope_mode="partial",
        required_codes=["SCAN_PARTIAL"],
    )
    assert result["scope"]["range_supported"] is False


def test_row_14_slow_drip_timeout(demo: Demo, tmp_path: Path) -> None:
    result = run_scan(
        demo,
        tmp_path,
        f"http://a.demo.test:{demo.http_port}/slow",
        min_throughput_grace_s=0.4,
    )
    assert_outcome(
        result,
        status="completed",
        verdict="UNABLE_TO_VERIFY",
        display_verdict="UNABLE_TO_VERIFY",
        confidence="low",
        scope_mode="partial",
        required_codes=["FETCH_TIMEOUT"],
    )


def test_row_15_http_404(demo: Demo, tmp_path: Path) -> None:
    result = run_scan(demo, tmp_path, f"http://a.demo.test:{demo.http_port}/status/404")
    assert_outcome(
        result,
        status="completed",
        verdict="UNABLE_TO_VERIFY",
        display_verdict="UNABLE_TO_VERIFY",
        confidence="low",
        scope_mode="none",
        required_codes=["FETCH_HTTP_ERROR"],
    )


def test_row_16_http_401_auth_required(demo: Demo, tmp_path: Path) -> None:
    result = run_scan(demo, tmp_path, f"http://a.demo.test:{demo.http_port}/status/401")
    assert_outcome(
        result,
        status="completed",
        verdict="UNABLE_TO_VERIFY",
        display_verdict="UNABLE_TO_VERIFY",
        confidence="low",
        scope_mode="none",
        required_codes=["FETCH_AUTH_REQUIRED"],
    )


def test_row_17_html_web_page_headers_only(demo: Demo, tmp_path: Path) -> None:
    result = run_scan(demo, tmp_path, f"http://a.demo.test:{demo.http_port}/page")
    assert_outcome(
        result,
        status="completed",
        verdict="UNABLE_TO_VERIFY",
        display_verdict="UNABLE_TO_VERIFY",
        confidence="low",
        scope_mode="metadata-only",
        required_codes=["LINK_IS_WEB_PAGE"],
    )


@pytest.mark.parametrize(
    "url",
    [
        "magnet:?xt=urn:btih:0123456789abcdef",
        "https://a.demo.test/ubuntu.torrent",
        "ftp://a.demo.test/pub/file.zip",
    ],
    ids=["18a-magnet", "18b-torrent", "18c-ftp"],
)
def test_row_18_unsupported_link_types(demo: Demo, tmp_path: Path, url: str) -> None:
    result = run_scan(demo, tmp_path, url)
    assert_outcome(
        result,
        status="unsupported",
        verdict=None,
        display_verdict="UNSUPPORTED",
        confidence=None,
        scope_mode="none",
        required_codes=["LINK_TYPE_UNSUPPORTED"],
    )


def test_row_19_zero_byte_empty_body(demo: Demo, tmp_path: Path) -> None:
    result = run_scan(demo, tmp_path, f"http://a.demo.test:{demo.http_port}/empty")
    assert_outcome(
        result,
        status="completed",
        verdict="UNABLE_TO_VERIFY",
        display_verdict="UNABLE_TO_VERIFY",
        confidence="low",
        scope_mode="none",
        required_codes=["FETCH_EMPTY"],
    )


def test_row_20_gzip_encoded_small_pdf(demo: Demo, tmp_path: Path) -> None:
    result = run_scan(demo, tmp_path, f"http://a.demo.test:{demo.http_port}/gzip/sample.pdf")
    assert_outcome(
        result,
        status="completed",
        verdict="SAFE",
        display_verdict="NO_ISSUES_IN_CHECKED_PART",
        confidence="low",
        scope_mode="partial",
        required_codes=["FETCH_UNEXPECTED_ENCODING"],
    )


def test_row_21_https_valid_pinned_tls_png(demo: Demo, tmp_path: Path) -> None:
    result = run_scan(demo, tmp_path, f"https://a.demo.test:{demo.https_port}/f/sample.png")
    assert_outcome(
        result,
        status="completed",
        verdict="SAFE",
        display_verdict="SAFE",
        confidence="high",
        scope_mode="full",
        expect_no_reasons=True,
    )


def test_row_22_https_wrong_host_certificate(demo: Demo, tmp_path: Path) -> None:
    result = run_scan(demo, tmp_path, f"https://a.demo.test:{demo.wrong_cert_port}/f/sample.png")
    assert_outcome(
        result,
        status="completed",
        verdict="UNABLE_TO_VERIFY",
        display_verdict="UNABLE_TO_VERIFY",
        confidence="low",
        scope_mode="none",
        required_codes=["FETCH_TLS_ERROR"],
    )
