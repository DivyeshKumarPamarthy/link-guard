"""Smoke test for the repository skeleton (task T0.1).

Proves the package layout from CLAUDE.md exists and imports, so later tasks build on a known base.
It also stops pytest from exiting with "no tests collected", which would fail `make test`.
"""

import importlib

import pytest

PACKAGES = [
    "app",
    "app.api",
    "app.contract",
    "app.core",
    "app.orchestrator",
    "app.engine",
    "app.engine.router",
    "app.engine.fetcher",
    "app.engine.detect",
    "app.engine.scoring",
    "app.registry",
    "app.db",
]


@pytest.mark.parametrize("name", PACKAGES)
def test_package_imports(name: str) -> None:
    module = importlib.import_module(name)
    assert module.__doc__, f"{name} needs a docstring saying what belongs in it"
