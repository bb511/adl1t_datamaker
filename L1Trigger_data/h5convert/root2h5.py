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

from L1Trigger_data.h5convert.terminal_colors import tcols


class Root2h5(object):
    """Converts L1TNtuple root files to .h5 files while selecting the relevant objects.

    This class does not convert the entirety of the given L1TNtuple root file to .h5,
    but selects a subset of objects from these files.
    One can also use this class to read previously converted h5 files.
    """

    def __init__(self):
        # See README for meaning of each object and their corresponding features.
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
        self.cicada = {"cicada": "CICADAScore"}
        self.energies = {
            "ET": ["Et", "ETTEM"],
            "HT": ["Et", "tower_count"],
            "MET": ["Et", "phi"],
            "MHT": ["Et", "phi"],
            "FET": ["Et", "phi"],
            "FHT": ["Et", "phi"],
        }

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

        self._store_muons()
        self._store_jets()
        self._store_egammas()
        self._store_taus()
        self._store_cica()
        self._store_energies()
        self._store_geninfo()

        self.output_file.close()

    def read_file(self, file: Path):
        """Read an h5 that was produced using this class."""
        self.h5file = h5py.File(file, mode="r")

    def read_folder(self, folder: Path):
        """Read and merge all h5 files inside a folder."""
        self.files = list(folder.glob("L1N*.h5"))
        if folder / "links.h5" in self.files:
            self.files.remove(folder / "links.h5")

        self.h5file = h5py.File(folder / "links.h5", mode="w")
        for file in self.files:
            self.h5file[file.stem] = h5py.ExternalLink(file, "/")

    def close_h5(self):
        """Closes the h5 file that is opened using this class."""
        try:
            self.h5file.close()
        except AttributeError:
            print(
                tcols.WARNING
                + "No h5 file open previously so nothing to close!"
                + tcols.ENDC
            )

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
        # algo_map = self._filter_algo_map_alt(algo_map)
        # exit(1)
        seeds = self._get_level1_seeds(algo_map, final_decision_bits)

        for seed, values in seeds.items():
            self.output_file.create_dataset(seed, data=values, compression="gzip")

    def _get_algo_map(self):
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

    # WIP getting rid of the prescale file dependency.
    # def _filter_algo_map_alt(self, algo_map: dict):
    #     """Filter the algorithm dict to include only algos that are not prescaled.

    #     Each run has certain conditions for every uGT algorithm, i.e., how often they
    #     are allowed to trigger. For example, the L1_SingleMu0_BMTF algorithm triggers
    #     at most once in 2000 events.
    #     """
    #     algo_names =  self._global_trigger_tree[
    #         "L1uGT/m_algoDecisionPreScaled"
    #     ].aliases.keys()
    #     bit_arrays = self._global_trigger_tree.arrays(
    #         ["m_algoDecisionInitial", "m_algoDecisionPreScaled"], library="np"
    #     )
    #     initial_bits = np.stack(bit_arrays["m_algoDecisionInitial"], axis=0)
    #     prescale_bits = np.stack(bit_arrays["m_algoDecisionPreScaled"], axis=0)
    #     del bit_arrays
    #     prescaled_algo_bits = set(np.array([
    #         bit
    #         for bit
    #         in  range(prescale_bits.shape[1])
    #         if (initial_bits[:, bit] != prescale_bits[:, bit]).any()
    #     ]).flatten())
    #     print(prescaled_algo_bits)

    def _filter_algo_map(self, algo_map: dict):
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

    def _get_decision_bits(self):
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

    def _get_level1_seeds(self, algo_map: dict, final_decision_bits: np.ndarray):
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
        event_data = ak.to_pandas(event_data).to_numpy()
        self.output_file.create_dataset(
            "event_info", data=event_data, compression="gzip"
        )

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

    def _store_energies(self):
        """Store the different types of energies associated with the event to np array.

        The 'bx' in 'sum_bx' refers to the bunch crossing number. The global trigger
        looks at ±2 bunch crossings in the LHC, and setting the '[var]_bx' to 0
        establishes that we are looking only at the current bunch crossing data.
        Confusingly, the energies are stored in the L1TNtuple trees all in the same leaf,
        and the way to separate each energy type is through the sum_type flag.
        """
        sums_feats = ["nSums", "sumType", "sumBx", "sumIEt", "sumIPhi"]
        sums_data = self._level1_trigger_tree.arrays(sums_feats)

        # Convert everything to numpy arrays for easier manipulation.
        sum_type = self._to_np_array(sums_data["sumType"], maxN=sums_data["nSums"][0])
        sum_bx = self._to_np_array(sums_data["sumBx"], maxN=sums_data["nSums"][0])
        sum_et = self._to_np_array(sums_data["sumIEt"], maxN=sums_data["nSums"][0])
        sum_phi = self._to_np_array(sums_data["sumIPhi"], maxN=sums_data["nSums"][0])

        # Construct energy objects.
        ET_idx = np.where((sum_type == 0) & (sum_bx == 0))
        ETTEM_idx = np.where((sum_type == 16) & (sum_bx == 0))
        self._store_ET(ET_idx, ETTEM_idx, sum_et)

        HT_idx = np.where((sum_type == 1) & (sum_bx == 0))
        HT_twrcnt_idx = np.where((sum_type == 21) & (sum_bx == 0))
        self._store_HT(HT_idx, HT_twrcnt_idx, sum_et)

        MET_idx = np.where((sum_type == 2) & (sum_bx == 0))
        ASYMET_idx = np.where((sum_type == 23) & (sum_bx == 0))
        self._store_MET(MET_idx, ASYMET_idx, sum_et, sum_phi)

        MHT_idx = np.where((sum_type == 3) & (sum_bx == 0))
        ASYMHT_idx = np.where((sum_type == 24) & (sum_bx == 0))
        self._store_MHT(MHT_idx, ASYMHT_idx, sum_et, sum_phi)

        FET_idx = np.where((sum_type == 8) & (sum_bx == 0))
        ASYFET_idx = np.where((sum_type == 25) & (sum_bx == 0))
        CENT_idx = np.where((sum_type == 22) & (sum_bx == 0))
        self._store_FET(FET_idx, ASYFET_idx, CENT_idx, sum_et, sum_phi)

        FHT_idx = np.where((sum_type == 20) & (sum_bx == 0))
        ASYFHT_idx = np.where((sum_type == 26) & (sum_bx == 0))
        CENT_idx = np.where((sum_type == 22) & (sum_bx == 0))
        self._store_FHT(FHT_idx, ASYFHT_idx, CENT_idx, sum_et, sum_phi)

        print("Conversion of energy objects finished! \U0001F504")

    def _to_np_array(self, ak_array, maxN=100, pad=0, dtype=np.float16):
        """Convert awkward array to a numpy array."""
        return (
            ak.fill_none(ak.pad_none(ak_array, maxN, clip=True, axis=-1), pad)
            .to_numpy()
            .astype(dtype)
        )

    def _store_ET(self, ET_idx: list, ETTEM_idx: list, sum_et: np.ndarray):
        """Store the transverse energy object to a numpy array and save to h5.

        The ETTEM feature refers to the missing transverse energy recorded by the
        electromagnetic calorimeter of the detector and only that.
        """
        ET_data = np.zeros((self.nentries, 2), dtype=np.uint16)
        ET_data[:, 0] = sum_et[ET_idx]
        ET_data[:, 1] = sum_et[ETTEM_idx]

        self.output_file.create_dataset("ET", data=ET_data, compression="gzip")

    def _store_HT(self, HT_idx: list, HT_twrcnt_idx: list, sum_et: np.ndarray):
        """Store the hardonic transverse energy object to a numpy array and save to h5.

        twr_count refers to the number of towers detected in the hadronic calorimeter.
        """
        HT_data = np.zeros((self.nentries, 2), dtype=np.uint16)
        HT_data[:, 0] = sum_et[HT_idx]
        HT_data[:, 1] = sum_et[HT_twrcnt_idx]

        self.output_file.create_dataset("HT", data=HT_data, compression="gzip")

    def _store_MET(
        self, MET_idx: list, ASYMET_idx: list, sum_et: np.ndarray, sum_phi: np.ndarray
    ):
        """Store the missing transverse energy object to a numpy array and save to h5.

        ASY refers to the asymmetry in the missing transverse energy; only used for
        heavy ion collisions, hence ignore for now. If you want to include this feat
        in the h5 data, uncomment below and change the length of the array to 3.
        """
        MET_data = np.zeros((self.nentries, 2), dtype=np.uint16)
        MET_data[:, 0] = sum_et[MET_idx]
        MET_data[:, 1] = sum_phi[MET_idx]
        # MET_data[:, 2] = sum_et[ASYMET_idx]

        self.output_file.create_dataset("MET", data=MET_data, compression="gzip")

    def _store_MHT(
        self, MHT_idx: list, ASYMHT_idx: list, sum_et: np.ndarray, sum_phi: np.ndarray
    ):
        """Store the missing hadronic transverse energy object to a numpy array and
        save to h5.

        ASY refers to the asymmetry in the missing hadronic transverse energy; only used
        for heavy ion collisions, hence ignore for now. If you want to include this feat
        in the h5 data, uncomment below and change the length of the array to 3.
        """
        MHT_data = np.zeros((self.nentries, 2), dtype=np.uint16)
        MHT_data[:, 0] = sum_et[MHT_idx]
        MHT_data[:, 1] = sum_phi[MHT_idx]
        # MHT_data[:, 2] = sum_et[ASYMHT_idx]

        self.output_file.create_dataset("MHT", data=MHT_data, compression="gzip")

    def _store_FET(
        self,
        FET_idx: list,
        ASYFET_idx: list,
        CENT_idx: list,
        sum_et: np.ndarray,
        sum_phi: np.ndarray,
    ):
        """Store the forward missing transverse energy object, i.e., missing transverse
        energy object that includes data from the hadronic forward calorimeter object,
        to a numpy array and save to h5.

        ASY refers to the asymmetry in the missing forward transverse energy; only used
        for heavy ion collisions, hence ignore for now.
        CEN refers to the centrality of this object. Again, only used for heavy ion
        collisions and ignored for now.
        If you want to include these feats in the h5 data, uncomment below and change
        the length of the array to 4.
        """
        FET_data = np.zeros((self.nentries, 2), dtype=np.uint16)
        FET_data[:, 0] = sum_et[FET_idx]
        FET_data[:, 1] = sum_phi[FET_idx]
        # FET_data[:, 2] = sum_et[ASYFET_idx]
        # Store the same centrality bits to both the FHT and FET, for comfort.
        # FET_data[:, 3] = sum_et[CENT_idx]

        self.output_file.create_dataset("FET", data=FET_data, compression="gzip")

    def _store_FHT(
        self,
        FHT_idx: list,
        ASYFHT_idx: list,
        CENT_idx: list,
        sum_et: np.ndarray,
        sum_phi: np.ndarray,
    ):
        """Store the forward missing transverse hadronic energy object, i.e., missing
        hadronic transverse energy object that includes data from the hadronic forward
        calorimeter object, to a numpy array and save to h5.

        ASY refers to the asymmetry in the missing forward hadronic transverse energy;
        only used for heavy ion collisions, hence ignore for now.
        CEN refers to the centrality of this object. Again, only used for heavy ion
        collisions and ignored for now.
        If you want to include these feats in the h5 data, uncomment below and change
        the length of the array to 4.
        """
        FHT_data = np.zeros((self.nentries, 2), dtype=np.uint16)
        FHT_data[:, 0] = sum_et[FHT_idx]
        FHT_data[:, 1] = sum_phi[FHT_idx]
        # FHT_data[:, 2] = sum_et[ASYFHT_idx]
        # Store the same centrality bits to both the FHT and FET, for comfort.
        # FHT_data[:, 3] = sum_et[CENT_idx]

        self.output_file.create_dataset("FHT", data=FHT_data, compression="gzip")

    def _store_muons(self):
        """Store the muon feature data into numpy arrays and save to h5."""

        # See README.md for information on what each feature means.
        # Still missing: charge valid, index bits, phi (out), hadronic shower trigger
        data = self._level1_trigger_tree.arrays(self.particles["muons"])

        # We have info ±2 bunch crossings, so select data concerning only current one.
        mask = self._level1_trigger_tree.arrays(["muonBx"])["muonBx"] == 0

        # Total number of muon objects should be 8 max, zero pad otherwise.
        nobjects = 8
        # Convert the tree data to numpy arrays.
        muon_phi = self._to_np_array(
            data["muonIPhiAtVtx"][mask], maxN=nobjects, dtype=np.int16
        )
        muon_pt = self._to_np_array(
            data["muonIEt"][mask], maxN=nobjects, dtype=np.int16
        )
        muon_qul = self._to_np_array(
            data["muonQual"][mask], maxN=nobjects, dtype=np.int16
        )
        muon_eta = self._to_np_array(
            data["muonIEtaAtVtx"][mask], maxN=nobjects, dtype=np.int16
        )
        muon_chg = self._to_np_array(
            data["muonChg"][mask], maxN=nobjects, dtype=np.int16
        )
        muon_free_phi = self._to_np_array(
            data["muonIPhi"][mask], maxN=nobjects, dtype=np.int16
        )
        muon_free_eta = self._to_np_array(
            data["muonIEta"][mask], maxN=nobjects, dtype=np.int16
        )
        muon_idx = self._to_np_array(
            data["muonTfMuonIdx"][mask], maxN=nobjects, dtype=np.int16
        )
        muon_upt = self._to_np_array(
            data["muonIEtUnconstrained"][mask], maxN=nobjects, dtype=np.int16
        )

        muon_data = np.stack(
            [
                muon_phi,
                muon_pt,
                muon_qul,
                muon_eta,
                muon_chg,
                muon_idx,
                muon_free_phi,
                muon_free_eta,
                muon_upt,
            ],
            axis=2,
        )

        print("Conversion of muon objects finished! \U0001F504")
        self.output_file.create_dataset("muons", data=muon_data, compression="gzip")

    def _store_jets(self):
        """Store the jets feature data into numpy arrays and save to h5."""

        # See README.md for information on what each feature means.
        data = self._level1_trigger_tree.arrays(self.particles["jets"])

        # We have info ±2 bunch crossings, so select data concerning only current one.
        mask = self._level1_trigger_tree.arrays(["jetBx"])["jetBx"] == 0

        # Total number of jets objects should be 12 max, zero pad otherwise.
        nobjects = 12
        # Convert the tree data to numpy arrays.
        jets_pt = self._to_np_array(data["jetIEt"][mask], maxN=nobjects, dtype=np.int16)
        jets_eta = self._to_np_array(
            data["jetIEta"][mask], maxN=nobjects, dtype=np.int16
        )
        jets_phi = self._to_np_array(
            data["jetIPhi"][mask], maxN=nobjects, dtype=np.int16
        )
        jets_qul = self._to_np_array(
            data["jetHwQual"][mask], maxN=nobjects, dtype=np.int16
        )
        jets_upt = self._to_np_array(
            data["jetRawEt"][mask], maxN=nobjects, dtype=np.int16
        )

        jets_data = np.stack([jets_pt, jets_eta, jets_phi, jets_qul, jets_upt], axis=2)

        print("Conversion of jet objects finished! \U0001F504")
        self.output_file.create_dataset("jets", data=jets_data, compression="gzip")

    def _store_egammas(self):
        """Store the electron/gamma feature data into numpy arrays and save to h5."""

        # See README.md for information on what each feature means.
        data = self._level1_trigger_tree.arrays(self.particles["egammas"])

        # We have info ±2 bunch crossings, so select data concerning only current one.
        mask = self._level1_trigger_tree.arrays(["egBx"])["egBx"] == 0

        # Total number of elec objects should be 12 max, zero pad otherwise.
        nobjects = 12
        # Convert the tree data to numpy arrays.
        elec_pt = self._to_np_array(data["egIEt"][mask], maxN=nobjects, dtype=np.int16)
        elec_eta = self._to_np_array(
            data["egIEta"][mask], maxN=nobjects, dtype=np.int16
        )
        elec_phi = self._to_np_array(
            data["egIPhi"][mask], maxN=nobjects, dtype=np.int16
        )
        elec_iso = self._to_np_array(data["egIso"][mask], maxN=nobjects, dtype=np.int16)

        elec_data = np.stack([elec_pt, elec_eta, elec_phi, elec_iso], axis=2)

        print("Conversion of egamma objects finished! \U0001F504")
        self.output_file.create_dataset("egammas", data=elec_data, compression="gzip")

    def _store_taus(self):
        """Store the taus feature data into numpy arrays and save to h5."""

        # See README.md for information on what each feature means.
        data = self._level1_trigger_tree.arrays(self.particles["taus"])

        # We have info ±2 bunch crossings, so select data concerning only current one.
        mask = self._level1_trigger_tree.arrays(["tauBx"])["tauBx"] == 0

        # Total number of taus objects should be 12 max, zero pad otherwise.
        nobjects = 12
        # Convert the tree data to numpy arrays.
        taus_pt = self._to_np_array(data["tauIEt"][mask], maxN=nobjects, dtype=np.int16)
        taus_eta = self._to_np_array(
            data["tauIEta"][mask], maxN=nobjects, dtype=np.int16
        )
        taus_phi = self._to_np_array(
            data["tauIPhi"][mask], maxN=nobjects, dtype=np.int16
        )
        taus_iso = self._to_np_array(
            data["tauIso"][mask], maxN=nobjects, dtype=np.int16
        )

        taus_data = np.stack([taus_pt, taus_eta, taus_phi, taus_iso], axis=2)

        print("Conversion of tau objects finished! \U0001F504")
        self.output_file.create_dataset("taus", data=taus_data, compression="gzip")

    def _store_cica(self):
        """Store the Cicada (Anomaly detector for calo) feature data into arrays."""

        # See README.md for information on what each feature means.
        data = self._gtrigger_calos_tree.arrays(self.cicada["cicada"])

        # Get the cicada score for all the events.
        nobjects = ak.count(data)
        # Convert the tree data to numpy arrays.
        cica_score = self._to_np_array(
            data["CICADAScore"], maxN=nobjects, dtype=np.float16
        )

        print("Conversion of cicada objects finished! \U0001F504")
        self.output_file.create_dataset("cicada", data=cica_score, compression="gzip")
