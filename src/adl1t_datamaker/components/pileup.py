# Get the pileup information from a file generated with brilcalc corresponding to the 
# current set of runs that you are processing.

from pathlib import Path
import numpy as np
import awkward as ak
import pandas as pd


def add_pileup_info(pileup_folder: Path, event_data: ak.Array) -> np.ndarray:
    """Gets an array with the pileup corresponding to each event in the h5."""
    runs_array = ak.to_numpy(event_data['run'])
    lumi_array = ak.to_numpy(event_data['lumi'])
    runs = set(runs_array.tolist())
    print(f"Getting pileup for runs: {runs}")

    pileup_map = {}
    for run_number in runs:
        lumi_sections = set(event_data['lumi'][event_data['run'] == run_number])
        pileup_map = get_pileup_map(pileup_folder, run_number, lumi_sections)

    lookup_func = np.frompyfunc(lookup_pileup, 3, 1)
    pileup = ak.Array(lookup_func(pileup_map, runs_array, lumi_array).astype(np.float32))

    return ak.with_field(event_data, pileup, 'nPV_True')

def get_pileup_map(
    pileup_folder: Path, run_number: int, lumi_sections: set
) -> np.ndarray:
    """Looks inside brilcalc file and gets pileup info for list of lumi sections."""
    run_number = int(run_number)
    pileup_file = pileup_folder.glob(f"run{run_number}*")
    try:
        pileup_file = next(pileup_file)
    except StopIteration:
        raise ValueError(
            f"No file for this run number in {pileup_folder}. "
            f"Check if this is truly data or might be simulation!"
        )

    pileup = pd.read_csv(pileup_file, skiprows=1)[:-3]
    pileup["ls"] = (pileup["ls"].astype(str).str.split(":").str[0].astype(int))

    pileup_map = {}
    # Get map from run_number, lumi_section to pileup_value.
    for lumi in list(lumi_sections):
        if lumi in set(pileup["ls"].to_numpy()):
            pileup_value = pileup.loc[pileup["ls"] == lumi, "avgpu"].to_numpy()[0]
            pileup_map[(int(run_number), int(lumi))] = pileup_value

    return pileup_map

def lookup_pileup(pileup_map: dict, run: int, lumi: int):
    return pileup_map.get((int(run), int(lumi)), 0)
