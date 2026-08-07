"""Shared fixtures and the EOS skip logic.

Tests marked `eos` stream real L1Ntuples from CERN EOS. They are skipped unless both
the xrootd extra is installed and a Kerberos ticket is live, so the suite stays usable
on a machine with a reader-only install.
"""

from pathlib import Path

import matplotlib
import pytest

import eos

# plots.py mutates global rcParams on import and no backend is set anywhere.
matplotlib.use("Agg")


def pytest_collection_modifyitems(config, items):
    reason = eos.blocker()
    if reason is None:
        return
    skip = pytest.mark.skip(reason=f"EOS unavailable: {reason}")
    for item in items:
        if "eos" in item.keywords:
            item.add_marker(skip)


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
