"""Shared test fixtures.

Every test starts with no LG_* variables set, so a developer's own environment
(for example LG_PROFILE=demo in their shell) can never change a test result.
"""

import os
from collections.abc import Iterator

import pytest

from tests.demo_server import Demo, run_demo_server


@pytest.fixture(autouse=True)
def clean_lg_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.startswith("LG_"):
            monkeypatch.delenv(name)


@pytest.fixture(scope="session")
def demo(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Demo]:
    """The real demo server, started on first use and stopped at the end of the session
    (D44). Only integration tests request it."""
    yield from run_demo_server(tmp_path_factory.mktemp("demo"))
