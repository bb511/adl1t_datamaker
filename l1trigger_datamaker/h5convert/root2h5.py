# Script that extracts all the global trigger data from the L1Tntuples and saves it
# into h5 files. Not all the global trigger objects are saved to the h5s, since some
# objects/features are not useful for analysis; see README.md for more details..

import re
from pathlib import Path
from functools import singledispatch

import h5py
import numpy as np
import uproot
import awkward as ak
import pandas as pd

from l1trigger_datamaker.h5convert.terminal_colors import tcols


class Root2h5(object):
    """Converts L1TNtuple root files to .h5 files while selecting the relevant objects.

    This class does not convert the entirety of the given L1TNtuple root file to .h5,
    but selects a subset of objects from these files.
    One can also use this class to read previously converted h5 files.
    """

    def __init__(self):
        # See README for meaning of each object and their corresponding features.

        # Define the number of objects present for each type of particle.
        self.muon_nobjects = 8
        self.egammas_nobjects = 12
        self.taus_nobjects = 12
        self.jets_nobjects = 12

        # Define the particle object names and the features that describe them.
        self.particles = {
            "muons": [
                "muonIPhiAtVtx",
                "muonIEt",
                "muonQual",
                "muonIEtaAtVtx",
                "muonChg",
                "muonTfMuonIdx",
                "muonIPhi",
                "muonIEta",
                "muonIEtUnconstrained",
            ],
            "jets": ["jetIEt", "jetIEta", "jetIPhi", "jetHwQual", "jetRawEt"],
            "egammas": ["egIEt", "egIEta", "egIPhi", "egIso"],
            "taus": ["tauIEt", "tauIEta", "tauIPhi", "tauIso"],
        }

        # Define the energy objects of the each event and their features.
        self.energies = {
            "ET": ["Et", "ETTEM"],
            "HT": ["Et", "tower_count"],
            "MET": ["Et", "phi"],
            "MHT": ["Et", "phi"],
            "FET": ["Et", "phi"],
            "FHT": ["Et", "phi"],
        }

        # Define the cicada (calo anomaly detector) object.
        self.cicada = {"cicada": "CICADAScore"}

        # Define the metadata of the event and the corresponding features.
        self.event_info = {
            "event_info": ["run", "lumi", "event", "bx", "orbit", "time", "PU"]
        }

        # Define the generator information, only useful for data generated with MC.
        self.geninfo = {"generator_HT": ["jetPt", "jetEta"]}

    def read_file(self, file: Path) -> h5py.File:
        """Read an h5 that was produced using this class."""
        return h5py.File(file, mode="r")

    def read_folder(self, folder: Path) -> h5py.File:
        """Read and merge all h5 files inside a folder."""
        print(f"Reading folder of h5 files {folder}...")
        self.file_names = list(folder.glob("*.h5"))

        if folder / "merged_folder.h5" in self.file_names:
            return h5py.File(folder / "merged_folder.h5", mode="r")

        print("Could not find merged h5 so merging the folder now...")
        self._merge_folder(folder)

        return h5py.File(folder / "merged_folder.h5", mode="r")

    def _merge_folder(self, folder: Path):
        """Merge folder of h5s into one h5 file."""
        # Get the names of the datasets that are found in every h5 file in the folder.
        initial_file = h5py.File(folder / self.file_names[0], mode="r")
        dataset_names = list(initial_file.keys())

        # Write empty file with dataset names.
        merged_h5 = h5py.File(folder / "merged_folder.h5", mode="w")
        for dataset_name in dataset_names:
            merged_h5.create_dataset(
                dataset_name,
                data=np.empty(initial_file[dataset_name].shape),
                chunks=True,
                maxshape=[None] * len(initial_file[dataset_name].shape),
            )
        initial_file.close()

        # Populate this empty file.
        for filename in self.file_names:
            print(f"Currently merging {filename}...", end="\r")
            current_file = h5py.File(folder / filename, mode="r")
            for dataset_name in dataset_names:
                merged_h5[dataset_name].resize(
                    (
                        merged_h5[dataset_name].shape[0]
                        + current_file[dataset_name].shape[0]
                    ),
                    axis=0,
                )
                merged_h5[dataset_name][
                    -current_file[dataset_name].shape[0] :
                ] = current_file[dataset_name]
            current_file.close()

        merged_h5.close()
        print(f"Finished merging folder. Saved to {folder / 'merged_folder.h5'}.")

    def convert(
        self,
        input_file: str,
        prescale_file: str,
        mc: bool,
        output_path: str,
        l1_tree_name: str = "l1UpgradeEmuTree/L1UpgradeTree",
        uGT_tree_name: str = "l1uGTEmuTree/L1uGTTree",
        event_tree_name: str = "l1EventTree/L1EventTree",
        calosumm_tree_name: str = "l1CaloSummaryEmuTree/L1CaloSummaryTree",
        gen_tree_name: str = "l1GeneratorTree/L1GenTree",
    ):
        """Convert given L1TNtuple file to h5 while extracting meaningful objects/feats.

        Include in the h5 only the relevant quantities from each given TTree, which are
        defined apriori (see README for more details).

        Args:
            input_file: The path to the input L1TNtuple root file.
            prescale_file: Path to the file with information on the prescale factors.
            mc: Whether the input file contains Monte Carlo simulation or not.
            output_path: Path to directory where output should be stored.
            tree_name: The name of the tree with the level 1 trigger information, that is
                found within the input L1TNtuple root file.
            uGT_tree_name: The name of the tree containing the global trigger objects
                found within the input L1TNtuple root file..
            event_tree_name: The name of the tree containing the event data, found within
                the input L1TNtuple root file.
            gen_tree_name: The name of the tree containing information on how the data
                was generated, given it is a Monte Carlo simulation.
        """
        self.input_file = Path(input_file)
        self.prescale_file = Path(prescale_file)
        self.output_path = Path(output_path)
        self.mc = mc

        print(tcols.HEADER + f"\nConverting {self.input_file} to h5!" + tcols.ENDC)

        # Get the interesting root trees that we want to convert.
        self._input_file_root = uproot.open(input_file)
        self._level1_trigger_tree = self._input_file_root[l1_tree_name]
        self._global_trigger_tree = self._input_file_root[uGT_tree_name]
        self._gtrigger_event_tree = self._input_file_root[event_tree_name]
        self._gtrigger_calos_tree = self._input_file_root[calosumm_tree_name]
        self._gen_tree_name = gen_tree_name

        # Get the number of events in the root file.
        self.nentries = self._level1_trigger_tree.num_entries

        # Store the interesting information from these root trees into an h5 file.
        self.output_file = h5py.File(self._get_output_filepath(), "w")
        self._store_seeds()
        self._store_eventinfo()
        self._store_geninfo()

        self._store_muons()
        self._store_jets()
        self._store_egammas()
        self._store_taus()
        self._store_energies()
        self._store_cica()

        self.output_file.close()

        print(tcols.OKGREEN + "Conversion to h5 finished!" + tcols.ENDC)
        print(tcols.OKGREEN + f"Saved: {self._get_output_filepath()}" + tcols.ENDC)

    def _get_output_filepath(self) -> Path:
        """Creates output dir and determines the name of the output file."""
        self.output_path.mkdir(parents=True, exist_ok=True)
        output_file = self.output_path / f"{self.input_file.stem}.h5"

        return output_file

    def _store_seeds(self):
        """Store the level 1 global trigger seeds to a given h5 file.

        This corresponds to constructing a dictionary that contains the name of each
        relevant algorithm in the global trigger and the corresponding decision bit
        for each event in the data file, i.e., 1 if it passed the algorithm and 0 if it
        did not pass the algorithm selection.
        """
        initial_decision_bits, final_decision_bits = self._get_decision_bits()

        algo_map = self._get_algo_map()
        algo_map = self._filter_algo_map(algo_map)
        seeds = self._get_level1_seeds(algo_map, final_decision_bits)

        for seed, values in seeds.items():
            self.output_file.create_dataset(seed, data=values, compression="gzip")

    def _get_algo_map(self) -> dict:
        """Get all the algorithms in the global trigger and their corresp decision bit nbs.

        The branch that is accessed here is not exactly the same as the one in the func
        @get_decision_bits. This method constructs a dictionary with the name of the
        algorithm and the corresponding number of the decision bit, e.g.,

        L1_SingleMuCosmics: 438
        """
        algo_map = {}
        for name, bit in self._global_trigger_tree[
            "L1uGT/m_algoDecisionInitial"
        ].aliases.items():
            matchbit = re.match(r"L1uGT\.m_algoDecisionInitial\[([0-9]+)\]", bit)
            algo_map[name] = int(matchbit.group(1))

        return algo_map

    def _filter_algo_map(self, algo_map: dict) -> dict:
        """Filter the algorithm dictionary to only the ones present in prescale file."""
        # [1] corresponds to algo name
        # [4] corresponds to "2.3E+34"

        # MAYBE REMOVE AT SOME LATER POINT.
        with open(self.prescale_file) as prescale_file:
            wanted_keys = [
                line.split(",")[1]
                for line in prescale_file
                if line.split(",")[6] == "1"
            ]

        return {key: algo_map[key] for key in wanted_keys}

    def _get_decision_bits(self) -> tuple[np.ndarray, np.ndarray]:
        """Get the decision bits for each algorithm in the global trigger for each event.

        The initial decision is the actual decision of the algorithm, while the final
        decision bits are due to applying global trigger rules to the event, i.e.,
        if the last event passes selection, then wait 2-3 events before you can take
        another one.
        """
        bit_arrays = self._global_trigger_tree.arrays(
            ["m_algoDecisionInitial", "m_algoDecisionFinal"], library="np"
        )
        initial_bits = np.stack(bit_arrays["m_algoDecisionInitial"], axis=0)
        final_bits = np.stack(bit_arrays["m_algoDecisionFinal"], axis=0)
        del bit_arrays

        return initial_bits, final_bits

    def _get_level1_seeds(self, algo_map: dict, final_decision_bits: np.ndarray) -> dict:
        """Construct dictionary of level 1 algorithm seeds.

        Construct dictionary where for each trigger algorithm name corresponds to a
        boolean list of all events in the data file, with True if it passes the algorithm
        and False if it does not.
        """
        seeds = {
            algo_name: np.empty([self.nentries], dtype=bool)
            for algo_name in algo_map.keys()
        }
        for algo_name, bit in algo_map.items():
            seeds[algo_name][:] = final_decision_bits[:, bit].astype(bool)
        seeds["L1bit"] = np.logical_or.reduce(
            [seeds[seedname] for seedname in algo_map.keys()]
        ).astype(bool)

        return seeds

    def _store_eventinfo(self):
        """Store the event information data to a numpy array and save to given h5."""
        event_info = ["run", "lumi", "event", "bx", "orbit", "time", "nPV_True"]
        event_data = self._gtrigger_event_tree.arrays(event_info)
        event_data = ak.to_dataframe(event_data).to_numpy()
        if not self.mc:
            pileups_all_runs = self._get_pileup_array(event_data)
        event_data = np.hstack([event_data, pileups_all_runs[:, 1].reshape(-1, 1)])
        self.output_file.create_dataset(
            "event_info", data=event_data, compression="gzip"
        )

    def _get_pileup_array(self, event_data):
        """Gets an array with the pileup corresponding to each event in the h5."""
        pileups_all_runs = []
        for run_number in set(event_data[:, 0]):
            idxs_events_per_run = np.where(event_data[:, 0] == run_number)[0]
            lumi_sections = event_data[idxs_events_per_run, 1]
            lumi_vs_pileup = self._get_pileup_info(run_number, set(lumi_sections))
            pileups = [lumi_vs_pileup[lumi] for lumi in lumi_sections]
            pileups = np.stack([idxs_events_per_run, pileups], axis=1)
            pileups_all_runs.append(pileups)

        pileups_all_runs = np.concatenate(pileups_all_runs, axis=0)
        pileups_all_runs = pileups_all_runs[pileups_all_runs[:, 0].argsort()]

        return pileups_all_runs

    def _get_pileup_info(self, run_number: int, lumi_sections: set) -> np.ndarray:
        """Looks inside brilcalc file and gets pileup info for list of lumi sections."""
        current_dir = Path(__file__).parent.resolve()
        pileup_files_folder = Path(current_dir / "pileup_files")
        pileup_file = next(pileup_files_folder.glob(f"run{run_number}*"))

        pileup_data = pd.read_csv(pileup_file, skiprows=1)[:-3]
        pileup_data['ls'] = pileup_data["ls"].astype(str).str.split(":").str[0].astype(int)

        lumi_sections = list(lumi_sections)
        pileup = pileup_data.query("ls == @lumi_sections")['avgpu'].to_numpy()
        lumi_vs_pileup = dict(zip(lumi_sections, pileup))

        return lumi_vs_pileup

    def _store_geninfo(self):
        """If the data file is monte carlo generated, then store additional info."""
        generator_HT = np.zeros((self.nentries,), dtype=np.float16)
        if self.mc == False:
            self.output_file.create_dataset(
                "generator_HT", data=generator_HT, compression="gzip"
            )
            return

        generator_tree = self._input_file_root[self._gen_tree_name]
        generator_feat = ["jetPt", "jetEta"]
        generator_data = generator_tree.arrays(generator_feat)
        generator_jets = np.zeros((self.nentries, 100, 2), dtype=np.float16)
        generator_jets[:, :, 0] = self._to_np_array(generator_data["jetPt"], maxN=100)
        generator_jets[:, :, 1] = self._to_np_array(generator_data["jetEta"], maxN=100)
        mask_pt = generator_jets[:, :, 0] > 30
        mask_eta = generator_jets[:, :, 1] < 2.5
        mask = (
            np.concatenate(
                (mask_pt[:, :, np.newaxis], mask_eta[:, :, np.newaxis]), axis=2
            )
            * 1
        )
        generator_jets = generator_jets * mask
        generator_HT = np.sum(generator_jets[:, :, 0], axis=1)

        self.output_file.create_dataset(
            "generator_HT", data=generator_HT, compression="gzip"
        )

    def _store_muons(self):
        """Store the muon feature data into numpy arrays and save to h5."""

        # See README.md for information on what each feature means.
        data = self._level1_trigger_tree.arrays(self.particles["muons"])

        # We have info ±2 bunch crossings, so select data concerning only current one.
        mask = self._level1_trigger_tree.arrays(["muonBx"])["muonBx"] == 0

        nobjects = self.muon_nobjects
        # Pad and convert variable length awkward arrays extracted from tree to np.
        muon_data = []
        for feature in self.particles["muons"]:
            feature_data = self._awk_to_np(data[feature][mask], nobjects, 0, np.int16)
            muon_data.append(feature_data)

        muon_data = np.stack(muon_data, axis=2)
        print("Conversion of muon objects finished! \U0001F504")
        self.output_file.create_dataset("muons", data=muon_data, compression="gzip")

    def _store_jets(self):
        """Store the jets feature data into numpy arrays and save to h5."""

        # See README.md for information on what each feature means.
        data = self._level1_trigger_tree.arrays(self.particles["jets"])

        # We have info ±2 bunch crossings, so select data concerning only current one.
        mask = self._level1_trigger_tree.arrays(["jetBx"])["jetBx"] == 0

        # Total number of jets objects should be 12 max, zero pad otherwise.
        nobjects = self.jets_nobjects
        # Convert the tree data to numpy arrays.
        jets_data = []
        for feature in self.particles["jets"]:
            feature_data = self._awk_to_np(data[feature][mask], nobjects, 0, np.int16)
            jets_data.append(feature_data)

        jets_data = np.stack(jets_data, axis=2)
        print("Conversion of jet objects finished! \U0001F504")
        self.output_file.create_dataset("jets", data=jets_data, compression="gzip")

    def _store_egammas(self):
        """Store the electron/gamma feature data into numpy arrays and save to h5."""

        # See README.md for information on what each feature means.
        data = self._level1_trigger_tree.arrays(self.particles["egammas"])

        # We have info ±2 bunch crossings, so select data concerning only current one.
        mask = self._level1_trigger_tree.arrays(["egBx"])["egBx"] == 0

        # Total number of elec objects should be 12 max, zero pad otherwise.
        nobjects = self.egammas_nobjects
        # Convert the tree data to numpy arrays.
        egammas_data = []
        for feature in self.particles["egammas"]:
            feature_data = self._awk_to_np(data[feature][mask], nobjects, 0, np.int16)
            egammas_data.append(feature_data)

        egammas_data = np.stack(egammas_data, axis=2)

        print("Conversion of egamma objects finished! \U0001F504")
        self.output_file.create_dataset("egammas", data=egammas_data, compression="gzip")

    def _store_taus(self):
        """Store the taus feature data into numpy arrays and save to h5."""

        # See README.md for information on what each feature means.
        data = self._level1_trigger_tree.arrays(self.particles["taus"])

        # We have info ±2 bunch crossings, so select data concerning only current one.
        mask = self._level1_trigger_tree.arrays(["tauBx"])["tauBx"] == 0

        # Total number of taus objects should be 12 max, zero pad otherwise.
        nobjects = self.taus_nobjects
        # Convert the tree data to numpy arrays.
        taus_data = []
        for feature in self.particles["taus"]:
            feature_data = self._awk_to_np(data[feature][mask], nobjects, 0, np.int16)
            taus_data.append(feature_data)

        taus_data = np.stack(taus_data, axis=2)
        print("Conversion of tau objects finished! \U0001F504")
        self.output_file.create_dataset("taus", data=taus_data, compression="gzip")

    def _store_energies(self):
        """Store the different types of energies associated with the event to np array.

        The 'bx' in 'sum_bx' refers to the bunch crossing number. The global trigger
        looks at ±2 bunch crossings in the LHC, and setting the '[var]_bx' to 0
        establishes that we are looking only at the current bunch crossing data.
        The energies are stored in the L1TNtuple trees all in the same leaf,
        and the way to separate each energy type is through the sum_type flag.
        """
        sums_feats = ["nSums", "sumType", "sumBx", "sumIEt", "sumIPhi"]
        sums_data = self._level1_trigger_tree.arrays(sums_feats)
        # Convert everything to numpy arrays for easier manipulation.

        nsums = sums_data["nSums"][0]
        sum_type = sums_data["sumType"].to_numpy().astype(np.int16)
        sum_bx = sums_data["sumBx"].to_numpy().astype(np.int16)
        sum_et = sums_data["sumIEt"].to_numpy().astype(np.int16)
        sum_phi = sums_data["sumIPhi"].to_numpy().astype(np.int16)

        # Construct energy objects.
        ET_idx = np.where((sum_type == 0) & (sum_bx == 0))
        ETTEM_idx = np.where((sum_type == 16) & (sum_bx == 0))
        self._store_ET(ET_idx, ETTEM_idx, sum_et)

        HT_idx = np.where((sum_type == 1) & (sum_bx == 0))
        HT_twrcnt_idx = np.where((sum_type == 21) & (sum_bx == 0))
        self._store_HT(HT_idx, HT_twrcnt_idx, sum_et)

        MET_idx = np.where((sum_type == 2) & (sum_bx == 0))
        self._store_MET(MET_idx, sum_et, sum_phi)

        MHT_idx = np.where((sum_type == 3) & (sum_bx == 0))
        self._store_MHT(MHT_idx, sum_et, sum_phi)

        FET_idx = np.where((sum_type == 8) & (sum_bx == 0))
        self._store_FET(FET_idx, sum_et, sum_phi)

        FHT_idx = np.where((sum_type == 20) & (sum_bx == 0))
        self._store_FHT(FHT_idx, sum_et, sum_phi)

        print("Conversion of energy objects finished! \U0001F504")

    def _store_ET(self, ET_idx: list, ETTEM_idx: list, sum_et: np.ndarray):
        """Store the transverse energy event object to a numpy array and save to h5.

        The ETTEM feature refers to the missing transverse energy recorded by the
        electromagnetic calorimeter of the detector and only that.
        """
        ET_data = np.zeros((self.nentries, 2), dtype=np.uint16)
        ET_data[:, 0] = sum_et[ET_idx]
        ET_data[:, 1] = sum_et[ETTEM_idx]

        self.output_file.create_dataset("ET", data=ET_data, compression="gzip")

    def _store_HT(self, HT_idx: list, HT_twrcnt_idx: list, sum_et: np.ndarray):
        """Store the hardonic transverse energy event object.

        twr_count refers to the number of towers detected in the hadronic calorimeter.
        """
        HT_data = np.zeros((self.nentries, 2), dtype=np.uint16)
        HT_data[:, 0] = sum_et[HT_idx]
        HT_data[:, 1] = sum_et[HT_twrcnt_idx]

        self.output_file.create_dataset("HT", data=HT_data, compression="gzip")

    def _store_MET(self, MET_idx: list, sum_et: np.ndarray, sum_phi: np.ndarray):
        """Store the missing transverse energy event object."""
        MET_data = np.zeros((self.nentries, 2), dtype=np.uint16)
        MET_data[:, 0] = sum_et[MET_idx]
        MET_data[:, 1] = sum_phi[MET_idx]

        self.output_file.create_dataset("MET", data=MET_data, compression="gzip")

    def _store_MHT(self, MHT_idx: list, sum_et: np.ndarray, sum_phi: np.ndarray):
        """Store the missing hadronic transverse energy object."""
        MHT_data = np.zeros((self.nentries, 2), dtype=np.uint16)
        MHT_data[:, 0] = sum_et[MHT_idx]
        MHT_data[:, 1] = sum_phi[MHT_idx]

        self.output_file.create_dataset("MHT", data=MHT_data, compression="gzip")

    def _store_FET(self, FET_idx: list, sum_et: np.ndarray, sum_phi: np.ndarray):
        """Store the forward missing transverse energy event object.

        Missing transverse energy object that includes data from the hadronic forward
        calorimeter object, to a numpy array and save to h5.
        """
        FET_data = np.zeros((self.nentries, 2), dtype=np.uint16)
        FET_data[:, 0] = sum_et[FET_idx]
        FET_data[:, 1] = sum_phi[FET_idx]

        self.output_file.create_dataset("FET", data=FET_data, compression="gzip")

    def _store_FHT(self, FHT_idx: list, sum_et: np.ndarray, sum_phi: np.ndarray):
        """Store the forward missing transverse hadronic energy event object.

        Missing hadronic transverse energy object that includes data from the hadronic
        forward calorimeter object, to a numpy array and save to h5.
        """
        FHT_data = np.zeros((self.nentries, 2), dtype=np.uint16)
        FHT_data[:, 0] = sum_et[FHT_idx]
        FHT_data[:, 1] = sum_phi[FHT_idx]

        self.output_file.create_dataset("FHT", data=FHT_data, compression="gzip")

    def _store_cica(self):
        """Store the Cicada (Anomaly detector for calo) feature data into arrays."""

        # See README.md for information on what each feature means.
        data = self._gtrigger_calos_tree.arrays(self.cicada["cicada"])
        nobjects = len(data["CICADAScore"])

        # Convert the tree data to numpy arrays.
        cica_score = self._awk_to_np(data["CICADAScore"], nobjects, 0, np.float16)
        print("Conversion of cicada objects finished! \U0001F504")
        self.output_file.create_dataset("cicada", data=cica_score, compression="gzip")

    def _awk_to_np(self, awk_array: ak.Array, length: int, padder, dtype: np.dtype):
        """Convert awkward array to a numpy array.

        Args:
            ak_array: Awkward array to convert.
            length: The length that the numpy array should have.
            padder: The object to pad the awk array with, can be a number or None.
            dtype: The data type of the generated numpy array.
        """
        # Pad the innermost dimension: axis=-1.
        awk_array = ak.pad_none(awk_array, length, clip=True, axis=-1)
        awk_array = ak.fill_none(awk_array, padder)
        return awk_array.to_numpy().astype(dtype)
