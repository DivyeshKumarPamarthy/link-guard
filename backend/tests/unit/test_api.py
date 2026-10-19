"""API tests with the MockExecutor (task T0.7, spec §2)."""

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.__main__ import server_options
from app.contract.models import ScanResult
from app.core.config import Settings
from app.main import create_app
from app.orchestrator.mock_executor import ExecutorOutput


def make_settings(tmp_path: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": f"sqlite:///{tmp_path / 'api.db'}",
        "mock_delay_ms": 30,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(make_settings(tmp_path)), raise_server_exceptions=False) as c:
        yield c


def poll_until_done(client: TestClient, scan_id: str, timeout_s: float = 5) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        body: dict[str, Any] = client.get(f"/api/scans/{scan_id}").json()
        if body["state"] == "done":
            return body
        time.sleep(0.02)
    raise AssertionError("scan did not finish in time")


# --- happy path ----------------------------------------------------------------------


def test_submit_returns_202_then_poll_reaches_done(client: TestClient) -> None:
    response = client.post("/api/scans", json={"url": "  https://short.example/abc  "})
    assert response.status_code == 202
    accepted = response.json()
    assert accepted["schema_version"] == "1.0"
    assert accepted["state"] == "queued"
    assert accepted["poll_after_ms"] == 500

    result = poll_until_done(client, accepted["scan_id"])
    ScanResult.model_validate(result)  # the response itself satisfies the contract
    assert result["scan_id"] == accepted["scan_id"]
    assert result["status"] == "completed"
    assert result["verdict"] == "UNSAFE"
    assert result["display_verdict"] == "UNSAFE"
    assert result["input_url"] == "https://short.example/abc"  # trimmed
    assert result["engine_version"] == "1.0.0"
    assert result["rules_version"] == "1.0.0"
    assert result["completed_at"] is not None


def test_scan_is_not_done_before_the_mock_delay(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path, mock_delay_ms=300))
    with TestClient(app) as client:
        scan_id = client.post("/api/scans", json={"url": "https://x.example/a"}).json()["scan_id"]
        first = client.get(f"/api/scans/{scan_id}").json()
        assert first["state"] in ("queued", "running")
        assert first["verdict"] is None and first["reasons"] is None  # null until done
        ScanResult.model_validate(first)
        assert poll_until_done(client, scan_id)["verdict"] == "UNSAFE"


def test_every_scan_gets_its_own_id(client: TestClient) -> None:
    ids = {
        client.post("/api/scans", json={"url": "https://x.example/a"}).json()["scan_id"]
        for _ in range(3)
    }
    assert len(ids) == 3  # no dedupe (D17)


def test_unknown_request_fields_are_ignored(client: TestClient) -> None:
    response = client.post("/api/scans", json={"url": "https://x.example/a", "future_option": True})
    assert response.status_code == 202


# --- input errors (400) --------------------------------------------------------------


def error_code(response: Any) -> str:
    body = response.json()
    assert body["schema_version"] == "1.0"
    code: str = body["error"]["code"]
    return code


@pytest.mark.parametrize("url", ["", "   ", "\n\t"])
def test_empty_url_is_400(client: TestClient, url: str) -> None:
    response = client.post("/api/scans", json={"url": url})
    assert response.status_code == 400
    assert error_code(response) == "URL_EMPTY"


def test_missing_url_field_is_url_empty(client: TestClient) -> None:
    response = client.post("/api/scans", json={})
    assert (response.status_code, error_code(response)) == (400, "URL_EMPTY")


def test_url_over_max_length_is_400(client: TestClient) -> None:
    url = "https://x.example/" + "a" * (2048 - len("https://x.example/") + 1)
    response = client.post("/api/scans", json={"url": url})
    assert (response.status_code, error_code(response)) == (400, "URL_TOO_LONG")


def test_url_at_exactly_max_length_is_accepted(client: TestClient) -> None:
    url = "https://x.example/" + "a" * (2048 - len("https://x.example/"))
    assert client.post("/api/scans", json={"url": url}).status_code == 202


def test_length_is_measured_after_trimming(client: TestClient) -> None:
    url = "https://x.example/" + "a" * (2048 - len("https://x.example/"))
    assert client.post("/api/scans", json={"url": f"   {url}   "}).status_code == 202


@pytest.mark.parametrize(
    "text",
    [
        "https://a.example/x https://b.example/y",
        "https://a.example/x\nhttps://b.example/y",
        "check www.a.example and http://b.example",
        "magnet:?xt=urn:btih:abc https://b.example/y",
    ],
)
def test_more_than_one_url_is_400(client: TestClient, text: str) -> None:
    response = client.post("/api/scans", json={"url": text})
    assert (response.status_code, error_code(response)) == (400, "URL_MULTIPLE")


def test_one_url_with_a_space_in_the_path_is_not_multiple(client: TestClient) -> None:
    assert (
        client.post("/api/scans", json={"url": "https://a.example/my file.pdf"}).status_code == 202
    )


@pytest.mark.parametrize(
    "body",
    [b"not json", b'{"url": 5}', b"[1, 2]", b'{"url": ["https://a.example"]}'],
)
def test_malformed_body_is_400_invalid_request(client: TestClient, body: bytes) -> None:
    response = client.post("/api/scans", content=body, headers={"Content-Type": "application/json"})
    assert (response.status_code, error_code(response)) == (400, "INVALID_REQUEST")


# --- 404 / 405 / 413 / 500 --------------------------------------------------------------


def test_unknown_scan_id_is_404(client: TestClient) -> None:
    response = client.get("/api/scans/00000000-0000-4000-8000-000000000000")
    assert (response.status_code, error_code(response)) == (404, "NOT_FOUND")


@pytest.mark.parametrize("scan_id", ["not-a-uuid", "1", "../etc/passwd"])
def test_malformed_scan_id_is_404(client: TestClient, scan_id: str) -> None:
    assert client.get(f"/api/scans/{scan_id}").status_code == 404


def test_there_is_no_list_or_history_endpoint(client: TestClient) -> None:
    response = client.get("/api/scans")
    assert response.status_code == 405
    assert error_code(response) == "METHOD_NOT_ALLOWED"


def test_oversized_body_is_413(client: TestClient) -> None:
    body = b'{"url": "' + b"a" * 9000 + b'"}'
    response = client.post("/api/scans", content=body, headers={"Content-Type": "application/json"})
    assert (response.status_code, error_code(response)) == (413, "REQUEST_TOO_LARGE")


def test_oversized_chunked_body_without_length_is_413(client: TestClient) -> None:
    def chunks() -> Iterator[bytes]:
        yield b'{"url": "'
        for _ in range(10):
            yield b"a" * 1000
        yield b'"}'

    response = client.post(
        "/api/scans", content=chunks(), headers={"Content-Type": "application/json"}
    )
    assert (response.status_code, error_code(response)) == (413, "REQUEST_TOO_LARGE")


def test_body_just_under_the_limit_is_not_413(client: TestClient) -> None:
    url = "https://x.example/" + "a" * 2000
    assert client.post("/api/scans", json={"url": url}).status_code == 202


class ExplodingExecutor:
    async def run(self, url: str) -> ExecutorOutput:
        raise RuntimeError("secret internal detail /home/user/token=abc")


def test_executor_crash_becomes_unable_to_verify_not_safe(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), executor=ExplodingExecutor())
    with TestClient(app) as client:
        scan_id = client.post("/api/scans", json={"url": "https://x.example/a"}).json()["scan_id"]
        result = poll_until_done(client, scan_id)
    assert result["verdict"] == "UNABLE_TO_VERIFY"
    assert [r["code"] for r in result["reasons"]] == ["ANALYSIS_ERROR"]
    assert "secret internal detail" not in str(result)


class InvalidOutputExecutor:
    async def run(self, url: str) -> ExecutorOutput:
        # Claims plain SAFE for a partial scan: the contract must refuse it.
        return {
            "status": "completed",
            "verdict": "SAFE",
            "display_verdict": "SAFE",
            "score": 0,
            "confidence": "low",
            "headline": "x",
            "reasons": [],
            "scope": {
                "mode": "partial",
                "bytes_analyzed": 1,
                "range_supported": False,
                "label": "x",
            },
        }


def test_dishonest_executor_output_is_refused(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), executor=InvalidOutputExecutor())
    with TestClient(app) as client:
        scan_id = client.post("/api/scans", json={"url": "https://x.example/a"}).json()["scan_id"]
        result = poll_until_done(client, scan_id)
    assert result["display_verdict"] == "UNABLE_TO_VERIFY"


def test_unexpected_error_is_500_without_stack_trace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app(make_settings(tmp_path))

    def explode(url: str) -> None:
        raise RuntimeError("Traceback secret detail")

    monkeypatch.setattr(app.state.orchestrator, "submit", explode)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/api/scans", json={"url": "https://x.example/a"})
    assert (response.status_code, error_code(response)) == (500, "INTERNAL_ERROR")
    assert "Traceback" not in response.text and "secret" not in response.text


# --- CORS and binding ----------------------------------------------------------------


def test_cors_allows_any_origin_without_credentials(client: TestClient) -> None:
    response = client.options(
        "/api/scans",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
    assert "access-control-allow-credentials" not in response.headers


def test_cors_headers_on_error_responses(client: TestClient) -> None:
    response = client.post(
        "/api/scans", json={"url": ""}, headers={"Origin": "http://localhost:5173"}
    )
    assert response.headers["access-control-allow-origin"] == "*"


def test_api_binds_to_loopback_by_default() -> None:
    assert server_options(Settings()) == {"host": "127.0.0.1", "port": 8000}
