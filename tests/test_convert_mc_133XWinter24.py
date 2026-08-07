"""L1TNtupleRun3-133XWinter24: MC, emulated trees, so CICADA is written.

Uses the 2023 menu, which filters seeds on a different luminosity column than the
142X campaign does, so the two MC tests do not produce the same seeds schema.
"""

import pytest

import eos
from conversion_helpers import (
    EMULATED, assert_layout, assert_readable, assert_seeds_and_events, convert,
)

INPUT = (
    "/eos/cms/store/group/cmst3/group/l1tr/jngadiub/L1TNtupleRun3-133XWinter24/"
    "haa-4b-ma15-POWHEG/mcRun3_Run3Winter24Digi-133XnoPU/240222_161438/0000/"
    "L1Ntuple_11.root"
)
MENU = "L1Menu_Collisions2023_v1_2_0.csv"


@pytest.mark.eos
def test_convert_and_read_back(tmp_path, repo_root):
    url = eos.require_file(INPUT)
    out = convert(url, tmp_path, repo_root, MENU, mc=True, converter=EMULATED)

    assert_layout(out, url, expect_cicada=True)
    data = assert_readable(out, expect_cicada=True)
    assert_seeds_and_events(data)
    assert "CICADAScore" in data["cica"].fields
