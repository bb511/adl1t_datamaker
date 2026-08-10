# Pileup of recorded data, read from the per-run CSV files that brilcalc writes. Only
# data has pileup this way: simulation carries its own in the ntuple.

from pathlib import Path
import numpy as np
import awkward as ak
import pandas as pd


def add_pileup_info(pileup_folder: Path, event_data: ak.Array) -> np.ndarray:
    """Overwrite nPV_True with the brilcalc pileup of the (run, lumi) of each event.

    brilcalc gives one average pileup per luminosity section, so every event of a
    section gets the same value, stored as float32.

    :param pileup_folder: Folder holding one brilcalc file per run, named
        ``run<run_number>*``.
    :param event_data: Event metadata, which must carry the run and lumi fields.
    :raises ValueError: If a run of the data has no file in the folder.
    :returns: event_data with nPV_True replaced. Events whose (run, lumi) is missing
        from the files get 0, which no later stage can tell apart from a genuine zero
        outside stable beams, so validation.check_pileup_present watches the fraction
        of zeros instead.
    """
    runs_array = ak.to_numpy(event_data["run"])
    lumi_array = ak.to_numpy(event_data["lumi"])
    runs = set(runs_array.tolist())
    print(f"Getting pileup for runs: {runs}")

    pileup_map = {}
    for run_number in runs:
        lumi_sections = set(event_data["lumi"][event_data["run"] == run_number])
        # Merge, do not overwrite: a file can span several runs.
        pileup_map |= get_pileup_map(pileup_folder, run_number, lumi_sections)

    # frompyfunc broadcasts the per-event dict lookup over the two arrays, but returns
    # dtype object, hence the cast.
    lookup_func = np.frompyfunc(lookup_pileup, 3, 1)
    pileup = ak.Array(
        lookup_func(pileup_map, runs_array, lumi_array).astype(np.float32)
    )

    return ak.with_field(event_data, pileup, "nPV_True")


def get_pileup_map(
    pileup_folder: Path, run_number: int, lumi_sections: set
) -> np.ndarray:
    """Average pileup of the given luminosity sections of one run.

    :raises ValueError: If no file in the folder is named after this run, which for
        recorded data means the folder is incomplete.
    :returns: brilcalc's avgpu keyed by (run, lumi). A section the file does not cover
        is absent from the map rather than zero.
    """
    run_number = int(run_number)
    pileup_file = pileup_folder.glob(f"run{run_number}*")
    try:
        pileup_file = next(pileup_file)
    except StopIteration:
        raise ValueError(
            f"No file for this run number in {pileup_folder}. "
            f"Check if this is truly data or might be simulation!"
        )

    # brilcalc puts a tag line above the header and a three-line summary below the data,
    # neither of which is a row.
    pileup = pd.read_csv(pileup_file, skiprows=1)[:-3]
    # brilcalc writes the section as lsnum:cmslsnum, so it needs splitting before it can
    # be matched against the lumi of an event.
    pileup["ls"] = pileup["ls"].astype(str).str.split(":").str[0].astype(int)

    pileup_map = {}
    for lumi in list(lumi_sections):
        if lumi in set(pileup["ls"].to_numpy()):
            pileup_value = pileup.loc[pileup["ls"] == lumi, "avgpu"].to_numpy()[0]
            pileup_map[(int(run_number), int(lumi))] = pileup_value

    return pileup_map


def lookup_pileup(pileup_map: dict, run: int, lumi: int):
    """Pileup of one event, 0 where the brilcalc files do not cover its (run, lumi).

    The 0 is a sentinel that survives into the parquet, where it reads as a genuine
    pileup of zero.
    """
    return pileup_map.get((int(run), int(lumi)), 0)
