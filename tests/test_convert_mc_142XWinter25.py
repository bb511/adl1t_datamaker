"""L1TNtupleRun3-142XWinter25: MC, emulated trees, so CICADA is written.

Being MC, pileup comes straight from the ntuple and no brilcalc lookup happens.
This is the cheapest EOS input in the suite at 2 MB.
"""

import pytest

import eos
from conversion_helpers import (
    EMULATED, assert_layout, assert_readable, assert_seeds_and_events, convert,
)

INPUT = (
    "/eos/cms/store/cmst3/group/l1tr/axol1tl/MC/L1TNtupleRun3-142XWinter25/"
    "haa-4b-ma15-POWHEG/mcRun3_Run3Winter25Digi-142XnoPU/250522_115555/0000/"
    "L1Ntuple_105.root"
)
MENU = "L1Menu_Collisions2024_v1_3_0_last.csv"


@pytest.mark.eos
def test_convert_and_read_back(tmp_path, repo_root):
    url = eos.require_file(INPUT, min_bytes=500_000)
    out = convert(url, tmp_path, repo_root, MENU, mc=True, converter=EMULATED)

    assert_layout(out, url, expect_cicada=True)
    data = assert_readable(out, expect_cicada=True)
    assert_seeds_and_events(data)
    assert "CICADAScore" in data["cica"].fields
