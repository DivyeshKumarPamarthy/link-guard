"""Fixtures for the SSRF tests (task T1.2): a fake resolver (tests/ssrf/fakes.py) and a
socket guard that records and fails any attempt to resolve or connect for real, even if the
code under test catches the error.
"""

import socket
from collections.abc import Iterator

import pytest

from tests.ssrf.fakes import FAKE_DNS, FakeResolver


@pytest.fixture
def resolver() -> FakeResolver:
    return FakeResolver(FAKE_DNS)


class SocketGuard:
    def __init__(self) -> None:
        self.attempts: list[str] = []


@pytest.fixture(autouse=True)
def socket_guard(monkeypatch: pytest.MonkeyPatch) -> Iterator[SocketGuard]:
    """Fail the test if anything tries real DNS or an outbound connection.

    pytest-socket already blocks sockets for the whole suite; this guard also *records*
    attempts, so a test fails even when the code under test swallows the exception.
    """
    guard = SocketGuard()

    def refuse(name: str):  # type: ignore[no-untyped-def]
        def blocked(*args: object, **kwargs: object) -> object:
            guard.attempts.append(f"{name}{args!r}")
            raise AssertionError(f"SSRF test made a real network call: {name}{args!r}")

        return blocked

    monkeypatch.setattr(socket, "getaddrinfo", refuse("getaddrinfo"))
    monkeypatch.setattr(socket, "gethostbyname", refuse("gethostbyname"))
    monkeypatch.setattr(socket, "create_connection", refuse("create_connection"))
    monkeypatch.setattr(socket.socket, "connect", refuse("socket.connect"))
    yield guard
    assert guard.attempts == [], f"network attempted: {guard.attempts}"
