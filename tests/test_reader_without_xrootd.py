"""The reader-only install must never require xrootd.

xrootd is CERN-specific and deliberately an optional extra, because most consumers of
this package only ever read the produced parquet. These tests run the import in a
subprocess with XRootD forced to be unimportable, so they hold even on a machine where
the extra happens to be installed.
"""

import subprocess
import sys

import pytest

# Make any import of XRootD fail, however it is spelled.
BLOCK_XROOTD = """
import sys
class Blocker:
    def find_module(self, name, path=None):
        if name == "XRootD" or name.startswith("XRootD."):
            return self
    def load_module(self, name):
        raise ImportError("XRootD blocked by test")
sys.meta_path.insert(0, Blocker())
"""


def run_isolated(body: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", BLOCK_XROOTD + body],
        capture_output=True, text=True, timeout=120,
    )


def test_loader_imports_without_xrootd():
    result = run_isolated("""
from adl1t_datamaker.loader import Parquet2Awkward, ParquetLoader
import sys
assert "XRootD" not in sys.modules, "reader pulled in XRootD"
print("ok")
""")
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_converter_module_imports_without_xrootd():
    """root2parquet reaches util, which used to import XRootD at module scope."""
    result = run_isolated("""
import adl1t_datamaker.root2parquet
import sys
assert "XRootD" not in sys.modules, "importing the converter pulled in XRootD"
print("ok")
""")
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_local_glob_needs_no_xrootd(tmp_path):
    """Globbing a local directory must not touch xrootd, and must not raise."""
    (tmp_path / "a.root").touch()
    (tmp_path / "b.root").touch()

    result = run_isolated(f"""
from pathlib import Path
from adl1t_datamaker import util
found = util.glob(Path({str(tmp_path)!r}), "*.root")
assert [p.name for p in found] == ["a.root", "b.root"], found
print("ok")
""")
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_remote_glob_without_xrootd_explains_itself():
    """A root:// path with no xrootd must name the extra, not fail obscurely."""
    result = run_isolated("""
from adl1t_datamaker import util
try:
    util.glob("root://eoscms.cern.ch//eos/cms/store", "*.root")
except ModuleNotFoundError as err:
    assert "adl1t-datamaker[xrootd]" in str(err), str(err)
    print("ok")
""")
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


@pytest.mark.parametrize("field", ["dependencies", "optional-dependencies"])
def test_xrootd_stays_an_extra(repo_root, field):
    """Guard the packaging contract itself, not just the imports."""
    import tomllib

    with open(repo_root / "pyproject.toml", "rb") as handle:
        project = tomllib.load(handle)["project"]

    if field == "dependencies":
        assert not any("xrootd" in dep for dep in project["dependencies"])
    else:
        assert "xrootd" in project["optional-dependencies"]
