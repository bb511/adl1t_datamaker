"""Brilcalc pileup lookup. No ROOT file, no network."""

import awkward as ak
import pytest

from adl1t_datamaker.components import pileup

# Runs with a checked-in scripts/pileup_files/run*_brilcalc_PU file.
RUNS = [381148, 381149, 386554, 386593, 392642, 396102, 398183]


@pytest.mark.parametrize("run", RUNS)
def test_every_checked_in_run_is_readable(pileup_files, run):
    """Each brilcalc file parses and yields pileup keyed by (run, luminosity section).

    Values are only required to be non-negative, because the checked-in files record
    avgpu 0 for some sections themselves, mostly ones taken outside stable beams.
    """
    sections = _first_lumi_sections(pileup_files, run)
    pileup_map = pileup.get_pileup_map(pileup_files, run, sections)

    assert pileup_map, f"no pileup recovered for run {run}"
    assert all(key[0] == run for key in pileup_map)
    assert all(value >= 0 for value in pileup_map.values())


@pytest.mark.parametrize("run", RUNS)
def test_stable_beam_sections_have_real_pileup(pileup_files, run):
    """Somewhere in every run there must be genuine, non-zero pileup."""
    import pandas as pd

    path = next(pileup_files.glob(f"run{run}*"))
    # brilcalc writes a tag line above the header and a three-line summary below the
    # data, and pandas would otherwise read that summary as three luminosity sections.
    frame = pd.read_csv(path, skiprows=1)[:-3]
    assert (frame["avgpu"] > 0).any(), f"run {run} has no lumi section with pileup"


def _first_lumi_sections(folder, run, n=5, only_with_pileup=False):
    """Luminosity sections that genuinely appear in the run's brilcalc file.

    The ``ls`` column holds a pair such as ``12:12``, of which only the first field is
    kept, as get_pileup_map does, so these numbers key the same map production builds.

    :param n: How many of the run's first sections to return.
    :param only_with_pileup: Keep only sections whose recorded avgpu is above zero.
        Without it a genuine zero reading is indistinguishable from the 0 that
        lookup_pileup returns for a section it cannot find.
    """
    import pandas as pd

    path = next(folder.glob(f"run{run}*"))
    frame = pd.read_csv(path, skiprows=1)[:-3]
    if only_with_pileup:
        frame = frame[frame["avgpu"] > 0]
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
    lumis_early = sorted(_first_lumi_sections(pileup_files, early, 3, only_with_pileup=True))
    lumis_late = sorted(_first_lumi_sections(pileup_files, late, 3, only_with_pileup=True))

    event_data = ak.Array({
        "run": [early] * len(lumis_early) + [late] * len(lumis_late),
        "lumi": lumis_early + lumis_late,
    })
    enriched = pileup.add_pileup_info(pileup_files, event_data)

    values = ak.to_numpy(enriched["nPV_True"])
    assert (values > 0).all(), f"some events fell back to pileup 0: {values}"
