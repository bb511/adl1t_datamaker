"""Talking to CERN EOS, and deciding whether that is possible at all.

Kept out of conftest.py so test modules can import it normally; importing conftest
directly makes pytest load it twice under different module names.
"""

import subprocess

EOS_REDIRECTOR = "root://eoscms.cern.ch"

# EOS keeps small placeholder entries for purged data sets, so a size floor is what
# distinguishes live data from a tombstone. Real L1TNtuples are megabytes.
STUB_SIZE_LIMIT = 1_000_000


def blocker() -> str | None:
    """Why EOS is unusable here, or None if it is usable."""
    try:
        import XRootD  # noqa: F401
    except ModuleNotFoundError:
        return "xrootd is not installed (pip install 'adl1t-datamaker[xrootd]')"

    try:
        if subprocess.run(["klist", "-s"], timeout=10).returncode != 0:
            return "no valid Kerberos ticket (run kinit)"
    except (OSError, subprocess.TimeoutExpired):
        return "klist unavailable, cannot confirm a Kerberos ticket"

    return None


def size(path: str) -> int | None:
    """Size in bytes of an EOS file, or None if it cannot be stat'd.

    :param path: EOS namespace path (``/eos/cms/...``), with no redirector in front of
        it: the redirector is what the stat call is issued against.
    """
    from XRootD import client

    _, info = client.FileSystem(EOS_REDIRECTOR).stat(path)
    return info.size if info is not None else None


def require_file(path: str, min_bytes: int = STUB_SIZE_LIMIT) -> str:
    """Return the URL of a live input, or skip the calling test.

    :param path: EOS namespace path (``/eos/cms/...``), with no redirector in front of it.
    :param min_bytes: Size floor separating a real ntuple from the stub left behind by a
        purge. Lower it for an input that is genuinely small.
    :returns: The path behind EOS_REDIRECTOR, ready to hand to uproot.
    """
    import pytest

    found = size(path)
    if found is None:
        pytest.skip(f"input no longer exists on EOS: {path}")
    if found < min_bytes:
        pytest.skip(f"input is a {found}-byte stub, dataset purged from EOS: {path}")

    return f"{EOS_REDIRECTOR}/{path}"
