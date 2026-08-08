# Helper methods to convert the level 1 seeds from the root file into a better format
# that is then stored into the parquet files.

import csv
import numpy as np
import uproot
import re
from pathlib import Path


# Zero-based columns of the prescale menu CSV. The prescale one holds the prescale at
# nominal luminosity, and its header names that luminosity, so it changes with the menu
# generation (2p1E34 in the 2023 menus, a 2p0E34 variant in 2024, 1p95E34 in 2025,
# 1.5E+34 in Prescale_2022), yet every menu shipped with this repo keeps it in the same
# position. A value of "1" there means unprescaled.
PRESCALE_COLUMN = 6
NAME_COLUMN = 1


def get_initial_decision(global_trigger_tree: uproot.TTree) -> np.ndarray:
    """Extracts the initial decision bits from the global trigger tree in the root file.

    These initial decision bits are what each of the algorithms in the L1 trigger return
    after processing the events: either accept (1) or reject (0), before the global
    trigger rules apply.

    :returns: Shape (events, algorithms), the column index being the decision bit
        number that get_algo_map reports for an algorithm.
    """
    initial_bits = global_trigger_tree.arrays(["m_algoDecisionInitial"], library="np")
    initial_bits = np.stack(initial_bits["m_algoDecisionInitial"], axis=0)

    return initial_bits

def get_final_decision(global_trigger_tree: uproot.TTree) -> np.ndarray[bool]:
    """Extracts the final decision bits from the global trigger tree in the root file.

    These final decision bits are the initial ones after the global trigger rules have
    been applied, so an algorithm that accepted an event can still read 0 here: a
    trigger rule caps how often accepts may follow one another.

    :returns: Shape (events, algorithms), columns indexed as in get_initial_decision.
    """
    final_bits = global_trigger_tree.arrays(["m_algoDecisionFinal"], library="np")
    final_bits = np.stack(final_bits["m_algoDecisionFinal"], axis=0)

    return final_bits

def get_algo_map(global_trigger_tree: uproot.TTree) -> dict:
    """Get all the algorithms in the global trigger and their corresp decision bit nbs.

    The bit number is parsed out of the ROOT aliases of the initial decision branch,
    which spell out the array index behind each algorithm name, e.g.

    L1_SingleMuCosmics: 438

    get_level1_seeds indexes the final decision array with these numbers, which assumes
    the initial and final arrays order their columns the same way.
    """
    algo_map = {}
    for name, bit in global_trigger_tree["L1uGT/m_algoDecisionInitial"].aliases.items():
        matchbit = re.match(r"L1uGT\.m_algoDecisionInitial\[([0-9]+)\]", bit)
        algo_map[name] = int(matchbit.group(1))

    return algo_map

def unprescaled_names(prescale_file_path: Path) -> list[str]:
    """Names of the seeds a menu leaves unprescaled, in menu order.

    The menu alone gives these names, with no root file involved, so the seed columns of
    an already converted data set can be checked against the menu that supposedly
    produced them. Duplicates survive: L1Menu_Collisions2025_v1_1_1 lists three tau
    seeds twice, and collapsing them is the caller's business.
    """
    with open(prescale_file_path, newline="") as prescale_file:
        rows = csv.reader(prescale_file)
        header = next(rows)  # Bound only to name the column in the error below.
        names = [
            row[NAME_COLUMN]
            for row in rows
            if len(row) > PRESCALE_COLUMN and row[PRESCALE_COLUMN] == "1"
        ]

    if not names:
        raise ValueError(
            f"No unprescaled algorithms found in {prescale_file_path}. Column "
            f"{PRESCALE_COLUMN} ({header[PRESCALE_COLUMN]!r}) never holds '1', so this "
            "menu probably does not have the column layout this code expects."
        )

    return names


def filter_algo_map(prescale_file_path: Path, algo_map: dict) -> dict:
    """The unprescaled seeds of a menu, with the decision bit number of each.

    Returning a dict collapses the seeds a menu happens to list twice.

    :param prescale_file_path: Prescale menu (csv) whose column ``PRESCALE_COLUMN``
        decides which seeds count as unprescaled.
    :param algo_map: Decision bit index keyed by algorithm name, as
        ``get_algo_map`` reads it from the trigger tree.
    :raises KeyError: When the menu names a seed the trigger tree lacks, so that a
        mismatched menu fails during conversion rather than dropping columns unnoticed.
    """
    return {key: algo_map[key] for key in unprescaled_names(prescale_file_path)}


def prescale_column_header(prescale_file_path: Path) -> str:
    """Name of the luminosity column that decides which seeds count as unprescaled."""
    with open(prescale_file_path, newline="") as prescale_file:
        return next(csv.reader(prescale_file))[PRESCALE_COLUMN]


def get_level1_seeds(algo_map: dict, final_decision_bits: np.ndarray) -> dict:
    """Construct dictionary of level 1 algorithm seeds.

    A seed is a trigger algorithm as CMS names it, and each one becomes a boolean array
    over the events, True where the event passed that algorithm.

    :param algo_map: Seed name to decision bit number, in practice the unprescaled
        subset of a menu that filter_algo_map returns.
    :param final_decision_bits: Shape (events, algorithms), as get_final_decision gives.
    :returns: The seeds of algo_map, plus an "L1bit" holding their logical OR. L1bit is
        thus the accept of the seeds passed in, not of the whole menu.
    """
    seeds = {}
    for algo_name, bit in algo_map.items():
        seeds.update({algo_name: final_decision_bits[:, bit].astype(bool)})

    seeds["L1bit"] = np.logical_or.reduce(
        [seeds[algo_name] for algo_name in algo_map.keys()]
    ).astype(bool)

    return seeds
