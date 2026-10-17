"""Proves the test suite cannot reach the network (CLAUDE.md: tests never touch the internet)."""

import socket

import pytest
from pytest_socket import SocketBlockedError

# pytest-socket warns each time it blocks; here the block is the point of the test.
pytestmark = pytest.mark.filterwarnings("ignore:A test tried to use socket")


def test_opening_an_internet_socket_fails() -> None:
    with pytest.raises(SocketBlockedError):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)


def test_connecting_to_loopback_fails_too() -> None:
    with pytest.raises(SocketBlockedError):
        socket.create_connection(("127.0.0.1", 80), timeout=0.1)
