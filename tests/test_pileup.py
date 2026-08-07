"""Brilcalc pileup lookup. No ROOT file, no network."""

import awkward as ak
import pytest

from adl1t_datamaker.components import pileup

# Runs with a checked-in scripts/pileup_files/run*_brilcalc_PU file.
RUNS = [381148, 381149, 386554, 386593, 392642, 396102, 398183]


@pytest.mark.parametrize("run", RUNS)
def test_every_checked_in_run_is_readable(pileup_files, run):
    header = _first_lumi_sections(pileup_files, run)
    pileup_map = pileup.get_pileup_map(pileup_files, run, header)

    assert pileup_map, f"no pileup recovered for run {run}"
    assert all(key[0] == run for key in pileup_map)
    assert all(value > 0 for value in pileup_map.values())


def _first_lumi_sections(folder, run, n=5):
    """A handful of lumi sections that genuinely appear in the run's brilcalc file."""
    import pandas as pd

    path = next(folder.glob(f"run{run}*"))
    frame = pd.read_csv(path, skiprows=1)[:-3]
    sections = frame["ls"].astype(str).str.split(":").str[0].astype(int)
    return set(sections.to_numpy()[:n].tolist())


def test_missing_run_raises(pileup_files):
    with pytest.raises(ValueError, match="truly data or might be simulation"):
        pileup.get_pileup_map(pileup_files, 999999, {1})


def test_lookup_defaults_to_zero():
    assert pileup.lookup_pileup({(1, 2): 47.5}, 1, 2) == 47.5
    assert pileup.lookup_pileup({(1, 2): 47.5}, 1, 3) == 0


def test_two_run_map_is_merged_not_overwritten(pileup_files):
    """A file spanning two runs must keep pileup for both.

    add_pileup_info used to reassign pileup_map each iteration, so only the last run
    survived and every event of the other run silently fell back to 0.
    """
    early, late = 381148, 381149
    lumis_early = sorted(_first_lumi_sections(pileup_files, early, n=3))
    lumis_late = sorted(_first_lumi_sections(pileup_files, late, n=3))

    event_data = ak.Array({
        "run": [early] * len(lumis_early) + [late] * len(lumis_late),
        "lumi": lumis_early + lumis_late,
    })
    enriched = pileup.add_pileup_info(pileup_files, event_data)

    values = ak.to_numpy(enriched["nPV_True"])
    assert (values > 0).all(), f"some events fell back to pileup 0: {values}"
