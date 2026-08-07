"""EphZB_2025G_run398183: real ZeroBias data, unpacked trees, so no CICADA."""

import pytest

import eos
from conversion_helpers import (
    UNPACKED, assert_layout, assert_pileup_present, assert_readable,
    assert_seeds_and_events, convert,
)

INPUT = (
    "/eos/cms/store/group/dpg_trigger/comm_trigger/L1Trigger/emsmith/condor/"
    "ForAxoTraining_EphZB_2025G_run398183_15_0_10_menu2025_v130_1760965469/1005.root"
)
MENU = "L1Menu_Collisions2025_v1_3_0.csv"


@pytest.mark.eos
def test_convert_and_read_back(tmp_path, repo_root):
    url = eos.require_file(INPUT)
    out = convert(url, tmp_path, repo_root, MENU, mc=False, converter=UNPACKED)

    assert_layout(out, url, expect_cicada=False)
    data = assert_readable(out, expect_cicada=False)
    assert_seeds_and_events(data)
    assert_pileup_present(data)
