"""Shared fixtures. The whole suite runs offline, from the checkout alone."""

from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """The repository root, resolved from this file rather than the CWD."""
    return Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def menus(repo_root) -> Path:
    return repo_root / "scripts" / "L1Menus"


@pytest.fixture(scope="session")
def pileup_files(repo_root) -> Path:
    return repo_root / "scripts" / "pileup_files"
