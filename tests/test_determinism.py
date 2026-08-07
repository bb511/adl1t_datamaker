"""Converting the same ntuple twice must produce byte-identical parquet.

A stable output means column order, compression and row grouping do not drift, which
is what makes it safe to compare or resume conversions across runs.
"""

import hashlib

import pytest

import eos
from conversion_helpers import EMULATED, convert

# The 2 MB 142X sample, so this costs the least EOS traffic of any conversion test.
INPUT = (
    "/eos/cms/store/cmst3/group/l1tr/axol1tl/MC/L1TNtupleRun3-142XWinter25/"
    "haa-4b-ma15-POWHEG/mcRun3_Run3Winter25Digi-142XnoPU/250522_115555/0000/"
    "L1Ntuple_105.root"
)
MENU = "L1Menu_Collisions2024_v1_3_0_last.csv"


def digests(folder):
    return {
        str(path.relative_to(folder)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(folder.rglob("*.parquet"))
    }


@pytest.mark.eos
def test_two_conversions_are_byte_identical(tmp_path, repo_root):
    url = eos.require_file(INPUT, min_bytes=500_000)

    first = convert(url, tmp_path / "first", repo_root, MENU, mc=True, converter=EMULATED)
    second = convert(url, tmp_path / "second", repo_root, MENU, mc=True, converter=EMULATED)

    left, right = digests(first), digests(second)
    assert set(left) == set(right), "the two conversions wrote different files"

    differing = sorted(name for name in left if left[name] != right[name])
    assert not differing, f"conversion is not reproducible for: {differing}"
