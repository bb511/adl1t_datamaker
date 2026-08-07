"""EphZB_2025B_run392642: real ZeroBias data, emulated trees.

Every .root under the configured input folder is a 134-byte EOS placeholder, so the
dataset has been purged and this test skips on the size floor in eos.require_file.
Kept so that the purge is recorded rather than forgotten; repoint INPUT if the data
is ever restaged.
"""

import pytest

import eos
from conversion_helpers import (
    EMULATED, assert_layout, assert_pileup_present, assert_readable,
    assert_seeds_and_events, convert,
)

INPUT = "/eos/cms/store/cmst3/group/l1tr/axol1tl/Data/101.root"
MENU = "L1Menu_Collisions2025_v1_1_1.csv"


@pytest.mark.eos
def test_convert_and_read_back(tmp_path, repo_root):
    url = eos.require_file(INPUT)
    out = convert(url, tmp_path, repo_root, MENU, mc=False, converter=EMULATED)

    assert_layout(out, url, expect_cicada=True)
    data = assert_readable(out, expect_cicada=True)
    assert_seeds_and_events(data)
    assert_pileup_present(data)
