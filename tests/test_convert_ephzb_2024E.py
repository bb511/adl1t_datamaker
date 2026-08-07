"""EphZB_2024E_run381148-381149: real ZeroBias data spanning two runs.

The input campaign folder has been deleted from EOS, so this test skips. It is kept
because the config is still checked in and because it is the only experiment that
spans two runs, which is what exercises the pileup map merge in
components/pileup.add_pileup_info. Repoint INPUT if the data is ever restaged.
"""

import pytest

import eos
from conversion_helpers import (
    EMULATED, assert_layout, assert_pileup_present, assert_readable,
    assert_seeds_and_events, convert,
)

INPUT = (
    "/eos/cms/store/group/dpg_trigger/comm_trigger/L1Trigger/caruta/condor/"
    "EphZB_2024E_run381148-381149_all_14_0_7_menuv110_1716739892/0.root"
)
MENU = "L1Menu_Collisions2024_v1_1_0.csv"


@pytest.mark.eos
def test_convert_and_read_back(tmp_path, repo_root):
    url = eos.require_file(INPUT)
    out = convert(url, tmp_path, repo_root, MENU, mc=False, converter=EMULATED)

    assert_layout(out, url, expect_cicada=True)
    data = assert_readable(out, expect_cicada=True)
    assert_seeds_and_events(data)
    assert_pileup_present(data)
