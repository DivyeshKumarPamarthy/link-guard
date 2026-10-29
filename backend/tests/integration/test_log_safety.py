"""Integration log and error safety review (task T3.5, spec §13, decision D30).

Runs scans against the demo server (and simulated crashes), captures every log record,
and verifies:
- No raw query-string values (e.g. signed-URL tokens) ever appear in logs.
- No control characters, ANSI escapes or bidi overrides appear in logs.
- No downloaded body bytes appear in logs.
- No stack traces or internal secrets appear in HTTP responses.
"""

import logging
import shutil
import time
import unicodedata
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.log import REDACTED
from app.main import create_app
from app.orchestrator.mock_executor import ExecutorOutput
from tests.demo_server import Demo

pytestmark = [
    pytest.mark.integration,
    pytest.mark.allow_hosts(["127.0.0.1"]),
]

REPO_ROOT = Path(__file__).resolve().parents[3]
REPO_SAMPLES = REPO_ROOT / "samples"
SECRET_TOKEN = "supersecret_signed_token_998877"
INVISIBLE_CHARS = set(
    "\u200b\u200c\u200d\u200e\u200f"
    "\u202a\u202b\u202c\u202d\u202e"
    "\u2066\u2067\u2068\u2069"
    "\ufeff\u2028\u2029"
)


@pytest.fixture(scope="module", autouse=True)
def populate_demo_samples(demo: Demo) -> None:
    if not (REPO_SAMPLES / "sample.pdf").is_file():
        pytest.fail("samples/ missing. Run `make samples` first.")
    for item in REPO_SAMPLES.iterdir():
        target = demo.samples_dir / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def poll_scan(client: TestClient, url: str) -> dict[str, Any]:
    res = client.post("/api/scans", json={"url": url})
    assert res.status_code == 202
    scan_id = res.json()["scan_id"]
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        body: dict[str, Any] = client.get(f"/api/scans/{scan_id}").json()
        if body["state"] == "done":
            return body
        time.sleep(0.02)
    raise AssertionError("scan timed out")


def test_scans_against_demo_server_never_log_secrets_control_chars_or_body_bytes(
    demo: Demo, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    settings = demo.settings().model_copy(
        update={"database_url": f"sqlite:///{tmp_path / 'logs.db'}", "poll_after_ms": 20}
    )
    base = f"http://a.demo.test:{demo.http_port}"
    urls = [
        f"{base}/f/sample.pdf?token={SECRET_TOKEN}&sig={SECRET_TOKEN}",
        f"{base}/disguised/movie.mp4?key={SECRET_TOKEN}",
        f"{base}/cd/rtl?auth={SECRET_TOKEN}",
        f"{base}/cd/nul?auth={SECRET_TOKEN}",
        f"{base}/status/404?secret={SECRET_TOKEN}",
        f"http://127.0.0.1/admin?password={SECRET_TOKEN}",
    ]

    with (
        caplog.at_level(logging.DEBUG, logger="linkguard"),
        TestClient(create_app(settings)) as client,
    ):
        for url in urls:
            poll_scan(client, url)

    messages = [record.getMessage() for record in caplog.records]
    assert len(messages) >= len(urls)
    full_log = "\n".join(messages)

    # 1. Query secrets are redacted, never logged raw.
    assert SECRET_TOKEN not in full_log
    assert REDACTED in full_log

    # 2. No control or invisible/bidi characters appear in any log message.
    for msg in messages:
        for ch in msg:
            assert unicodedata.category(ch) != "Cc", f"control char U+{ord(ch):04X} in {msg!r}"
            assert ch not in INVISIBLE_CHARS, f"invisible char U+{ord(ch):04X} in {msg!r}"

    # 3. No file body bytes or greetings appear in logs.
    assert "Hello from LinkGuard" not in full_log
    assert "%PDF-1.4" not in full_log


class CrashingWithUrlExecutor:
    async def run(self, url: str) -> ExecutorOutput:
        raise RuntimeError(f"failed on {url} with\x1b[31mANSI\x1b[0m and\u202ebidi")


def test_crash_logs_and_responses_never_leak_stack_traces_or_raw_secrets(
    demo: Demo, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    settings = demo.settings().model_copy(
        update={"database_url": f"sqlite:///{tmp_path / 'crash.db'}", "poll_after_ms": 20}
    )
    app = create_app(settings, executor=CrashingWithUrlExecutor())
    with (
        caplog.at_level(logging.DEBUG, logger="linkguard"),
        TestClient(app, raise_server_exceptions=False) as client,
    ):
        result = poll_scan(
            client, f"http://a.demo.test:{demo.http_port}/f/sample.pdf?token={SECRET_TOKEN}"
        )

    assert result["display_verdict"] == "UNABLE_TO_VERIFY"
    assert "Traceback" not in str(result)
    assert SECRET_TOKEN not in str(result).replace(
        result["input_url"], ""
    )  # only input_url holds the submitted URL

    full_log = "\n".join(r.getMessage() for r in caplog.records)
    assert SECRET_TOKEN not in full_log
    assert REDACTED in full_log
    assert "\x1b" not in full_log
    assert "\u202e" not in full_log
    assert "Traceback" not in full_log
