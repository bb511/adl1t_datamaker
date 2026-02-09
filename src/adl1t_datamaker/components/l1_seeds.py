# Helper methods to convert the level 1 seeds from the root file into a better format
# that is then stored into the parquet files.

import numpy as np
import uproot
import re
from pathlib import Path


def get_initial_decision(global_trigger_tree: uproot.TTree) -> np.ndarray:
    """Extracts the initial decision bits from the global trigger tree in the root file.

    These initial decision bits are what each of the algorithms in the L1 trigger return
    after processing the events: either accept (1) or reject (0).

    This method returns a numpy array with each row representing an event and each
    column representing the decision of a specific algorithm in the trigger.
    """
    initial_bits = global_trigger_tree.arrays(["m_algoDecisionInitial"], library="np")
    initial_bits = np.stack(initial_bits["m_algoDecisionInitial"], axis=0)

    return initial_bits

def get_final_decision(global_trigger_tree: uproot.TTree) -> np.ndarray[bool]:
    """Extracts the initial decision bits from the global trigger tree in the root file.

    These final decision bits are what each of the algorithms in the L1 trigger return
    after the initial bits are processed according to the global trigger rules, for
    example, if the last event passed selection, then wait 2-3 events before allowing
    another event to pass selection, even if the initial decision bit is 1.

    This method returns a numpy array with each row representing an event and each
    column representing the final decision for each algorithm given GT rules.
    """
    final_bits = global_trigger_tree.arrays(["m_algoDecisionFinal"], library="np")
    final_bits = np.stack(final_bits["m_algoDecisionFinal"], axis=0)

    return final_bits

def get_algo_map(global_trigger_tree: uproot.TTree) -> dict:
    """Get all the algorithms in the global trigger and their corresp decision bit nbs.

    The branch that is accessed here is not exactly the same as the one in the method
    @get_final_decision_bits. This method constructs a dictionary with the name of the
    algorithm and the corresponding number of the decision bit, e.g.,

    L1_SingleMuCosmics: 438
    """
    algo_map = {}
    for name, bit in global_trigger_tree["L1uGT/m_algoDecisionInitial"].aliases.items():
        matchbit = re.match(r"L1uGT\.m_algoDecisionInitial\[([0-9]+)\]", bit)
        algo_map[name] = int(matchbit.group(1))

    return algo_map

def filter_algo_map(prescale_file_path: Path, algo_map: dict) -> dict:
    """Filter the algorithm dictionary to only the ones that are not prescaled.

    Args:
        prescale_file_path: Path object pointing to the file that contains the
            prescaling information for each algorithm.
        algo_map: Dictionary of algorithm names and corresponding bit that they flip.
    """
    # [1] corresponds to algo name
    # [4] corresponds to "2.3E+34"
    with open(prescale_file_path) as prescale_file:
        unprescaled_keys = [
            line.split(",")[1]
            for line in prescale_file
            if line.split(",")[6] == "1"
        ]

    return {key: algo_map[key] for key in unprescaled_keys}

def get_level1_seeds(algo_map: dict, final_decision_bits: np.ndarray) -> dict:
    """Construct dictionary of level 1 algorithm seeds.

    Construct dictionary where for each trigger algorithm name corresponds to a
    boolean list of all events in the data file, with True if it passes the algorithm
    and False if it does not. These are called 'seeds' in CMS.'
    """
    seeds = {}
    for algo_name, bit in algo_map.items():
        seeds.update({algo_name: final_decision_bits[:, bit].astype(bool)})

    # Compute the final decision based on all algorithms for each event.
    seeds["L1bit"] = np.logical_or.reduce(
        [seeds[algo_name] for algo_name in algo_map.keys()]
    ).astype(bool)

    return seeds
