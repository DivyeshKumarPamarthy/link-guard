"""Shared test fixtures.

Every test starts with no LG_* variables set, so a developer's own environment
(for example LG_PROFILE=demo in their shell) can never change a test result.
"""

import os

import pytest


@pytest.fixture(autouse=True)
def clean_lg_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.startswith("LG_"):
            monkeypatch.delenv(name)
