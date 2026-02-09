# Script that extracts all the global trigger data from the L1Tntuples and saves it
# into h5 files. Not all the global trigger objects are saved to the h5s, since some
# objects/features are not useful for analysis; see README.md for more details..

import io
import pathlib
from pathlib import Path
import joblib
import contextlib

import uproot
import awkward as ak

from adl1t_datamaker.terminal_colors import tcols
from adl1t_datamaker import util
from adl1t_datamaker.components import l1_seeds
from adl1t_datamaker.components import pileup


class Root2Parquet(object):
    """Converts L1TNtuple root files to parquet files.

    This class does not convert the entirety of the given L1TNtuple root, but selects a
    subset of objects from these files. See the init for a list of the extracted objects
    and their associated features.

    Args:
        mc: Whether the input file contains Monte Carlo simulation or not.
        output_path: Path to directory where output should be stored.
        l1_tree_name: The name of the tree with the level 1 trigger information, that is
            found within the input L1TNtuple root file.
        uGT_tree_name: The name of the tree containing the global trigger objects
            found within the input L1TNtuple root file.
        event_tree_name: The name of the tree containing the event data, found within
            the input L1TNtuple root file.
        calosumm_tree_name: The name of the arrays containing calorimeter sums.
    """

    def __init__(
        self,
        mc: bool,
        l1_tree_name: str,
        uGT_tree_name: str,
        event_tree_name: str,
        calosumm_tree_name: str = None,
        silent: bool = False
    ):
        self.l1_tree_name = l1_tree_name
        self.uGT_tree_name = uGT_tree_name
        self.event_tree_name = event_tree_name
        self.calosumm_tree_name = calosumm_tree_name
        self.silent = silent
        self.mc = mc

        # Metadata information for objects found in these trees.
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

        # Define the energy objects of the each event and their sum type number.
        self.energies = {
            "ET":{"Et": 0, "ETTEM": 1},
            "HT":{"Et": 1, "tower_count": 21},
            "MET":{"Et": 2, "phi": 2},
            "MHT":{"Et": 3, "phi": 3},
            "FET":{"Et": 8, "phi": 8},
            "FHT":{"Et": 20, "phi": 20},
        }

        # Define the cicada (calo anomaly detector) object.
        self.cicada = {"cicada": ["CICADAScore"]}

        # Define the metadata of the event and the corresponding features.
        self.event_info = {
            "event_info": [
                "run",
                "lumi",
                "event",
                "bx",
                "orbit",
                "time",
                "nPV_True",
            ]
        }

    def convert_file(
        self, input_file: str, prescale_file: str, pileup_folder: str, output_path: str
    ):
        """Convert given L1TNtuple file.

        Include only the relevant quantities from each given TTree, which are defined
        apriori (see README for more details).

        Args:
            input_file: The path to the input L1TNtuple root file.
            prescale_file: Path to the file with information on the prescale factors.
            pileup_folder: Path to the folder containing files with pileup information.
            output_path: Path to the folder where the converted data is stored.
        """
        self.input_file = util.check_xrootd_path(input_file)
        self.prescale_file = Path(prescale_file)
        self.pileup_folder = Path(pileup_folder)
        self.output_path = Path(output_path)

        print(tcols.HEADER + f"\nConverting {self.input_file} to parquet!" + tcols.ENDC)
        self._conversion(self.input_file)
        print(tcols.OKGREEN + "Conversion finished!" + tcols.ENDC)
        print(f"Saved: {self.output_path}.")

    def convert_folder(
        self,
        folder: str,
        prescale_file: str,
        pileup_folder: str,
        output_path: str,
        ncores: int = 1,
    ):
        """Extract objects/features from folder of root files and convert to h5s.

        Include in the h5 only the relevant quantities from each given TTree, which are
        defined apriori (see README for more details).

        Args:
            folder: The path to the folder containing L1TNtuples. All these
                L1TNtuple root files must have the same structure.
            prescale_file: Path to the file with information on the prescale factors.
            pileup_folder: Path to the folder containing files with pileup information.
            output_path: Path to directory where output should be stored.
            ncores: Number of files to be converted at the same time.
        """
        self.input_folder = util.check_xrootd_path(folder)
        self.prescale_file = Path(prescale_file)
        self.pileup_folder = Path(pileup_folder)
        self.output_path = Path(output_path)

        files_to_convert = util.glob(self.input_folder, "*.root")
        if not files_to_convert:
            raise ValueError(tcols.FAIL + f"{self.input_folder} is empty!" + tcols.ENDC)

        print(tcols.HEADER + f"\nConverting {self.input_folder} to pq!" + tcols.ENDC)

        processes = joblib.Parallel(n_jobs=ncores)
        processes(
            joblib.delayed(self._conversion)(input_file)
            for input_file in files_to_convert
        )

        print(tcols.OKGREEN + f"Conversion of {self.input_folder} done!" + tcols.ENDC)
        print(tcols.OKGREEN + f"Files saved to {self.output_path}." + tcols.ENDC)

    def _conversion(self, input_file: str):
        """Convert a root l1ntuple file to a parquet file."""
        print(tcols.OKGREEN + f"Converting {input_file}..." + tcols.ENDC)

        # Create output directory and set the name of the output file for each object.
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.output_filename = Path(input_file).stem

        # Get the root trees of interest for anomaly detection.
        self._input_file_root = uproot.open(input_file)
        self._level1_trigger_tree = self._input_file_root[self.l1_tree_name]
        self._global_trigger_tree = self._input_file_root[self.uGT_tree_name]
        self._gtrigger_event_tree = self._input_file_root[self.event_tree_name]
        if not self.calosumm_tree_name is None:
            self._gtrigger_calos_tree = self._input_file_root[self.calosumm_tree_name]
        else:
            self._gtrigger_calos_tree = None

        # Get the number of events in the root file.
        self.nentries = self._level1_trigger_tree.num_entries

        # Suppress output of the storing methods if the 'silent' flag is true.
        if self.silent:
            with contextlib.redirect_stdout(io.StringIO()) as f:
                self._store_objects()
        else:
            self._store_objects()

    def _store_objects(self) -> None:
        """Store objects of interest to the h5 files."""
        self._store_seeds()
        self._store_eventinfo()
        self._store_muons()
        self._store_jets()
        self._store_egammas()
        self._store_taus()
        self._store_energies()
        self._store_cica()

    def _store_seeds(self):
        """Store the level 1 global trigger seeds to a given h5 file.

        This corresponds to constructing a dictionary that contains the name of each
        relevant algorithm in the global trigger and the corresponding decision bit
        for each event in the data file, i.e., 1 if it passed the algorithm and 0 if it
        did not pass the algorithm selection.
        """
        seeds_directory = self.output_path / 'seeds'
        seeds_directory.mkdir(parents=True, exist_ok=True)
        seeds_file = seeds_directory / f'{self.output_filename}.parquet'

        initial_decision_bits = l1_seeds.get_initial_decision(self._global_trigger_tree)
        final_decision_bits = l1_seeds.get_final_decision(self._global_trigger_tree)

        algo_map = l1_seeds.get_algo_map(self._global_trigger_tree)
        algo_map = l1_seeds.filter_algo_map(self.prescale_file, algo_map)
        seeds = l1_seeds.get_level1_seeds(algo_map, final_decision_bits)

        # Save seeds to parquet file.
        seeds = ak.Array(seeds)
        # Make the seeds data follow the same structure as the rest.
        # Go from (nevents, nfeat) to (nevents, 1, nfeats), 1 const data.
        seeds = ak.singletons(seeds)
        ak.to_parquet(seeds, seeds_file, compression='snappy')

    def _store_eventinfo(self):
        """Store the event information data to a numpy array and save to given h5."""
        einfo_directory = self.output_path / "event_info"
        einfo_directory.mkdir(parents=True, exist_ok=True)
        einfo_file = einfo_directory / f'{self.output_filename}.parquet'

        event_data = self._gtrigger_event_tree.arrays(self.event_info['event_info'])
        if not self.mc:
            event_data = pileup.add_pileup_info(self.pileup_folder, event_data)

        # Make the event data follow the same structure as the rest.
        # Go from (nevents, nfeat) to (nevents, 1, nfeats), 1 const data.
        event_data = ak.singletons(event_data)
        # Save event info to parquet file.
        ak.to_parquet(event_data, einfo_file, compression='snappy')

    def _store_muons(self):
        """Store the muon feature data into numpy arrays and save to h5."""
        muons_directory = self.output_path / "muons"
        muons_directory.mkdir(parents=True, exist_ok=True)
        muons_file = muons_directory / f'{self.output_filename}.parquet'

        # See README.md for information on what each feature means.
        data = self._level1_trigger_tree.arrays(self.particles["muons"])

        # We have info ±2 bunch crossings, so select data concerning only current one.
        mask = self._level1_trigger_tree.arrays(["muonBx"])["muonBx"] == 0

        # Restructure array into feature_name: array_of_values_for_each_event.
        data = ak.Array({feature: data[feature][mask] for feature in data.fields})

        # Save muon data to parquet file.
        ak.to_parquet(data, muons_file, compression='snappy')
        print("Conversion of muon objects finished! \U0001F504")

    def _store_jets(self):
        """Store the jets feature data into numpy arrays and save to h5."""
        jets_directory = self.output_path / "jets"
        jets_directory.mkdir(parents=True, exist_ok=True)
        jets_file = jets_directory / f'{self.output_filename}.parquet'

        data = self._level1_trigger_tree.arrays(self.particles["jets"])
        mask = self._level1_trigger_tree.arrays(["jetBx"])["jetBx"] == 0
        data = ak.Array({feature: data[feature][mask] for feature in data.fields})

        ak.to_parquet(data, jets_file, compression='snappy')
        print("Conversion of jet objects finished! \U0001F504")

    def _store_egammas(self):
        """Store the electron/gamma feature data into numpy arrays and save to h5."""
        egammas_directory = self.output_path / "egammas"
        egammas_directory.mkdir(parents=True, exist_ok=True)
        egammas_file = egammas_directory / f'{self.output_filename}.parquet'

        data = self._level1_trigger_tree.arrays(self.particles["egammas"])
        mask = self._level1_trigger_tree.arrays(["egBx"])["egBx"] == 0
        data = ak.Array({feature: data[feature][mask] for feature in data.fields})

        ak.to_parquet(data, egammas_file, compression='snappy')
        print("Conversion of egamma objects finished! \U0001F504")

    def _store_taus(self):
        """Store the taus feature data into numpy arrays and save to h5."""
        taus_directory = self.output_path / "taus"
        taus_directory.mkdir(parents=True, exist_ok=True)
        taus_file = taus_directory / f'{self.output_filename}.parquet'

        data = self._level1_trigger_tree.arrays(self.particles["taus"])
        mask = self._level1_trigger_tree.arrays(["tauBx"])["tauBx"] == 0
        data = ak.Array({feature: data[feature][mask] for feature in data.fields})

        ak.to_parquet(data, taus_file, compression='snappy')
        print("Conversion of tau objects finished! \U0001F504")

    def _store_energies(self):
        """Store the different types of energies associated with the event to np array.

        The 'bx' in 'sum_bx' refers to the bunch crossing number. The global trigger
        looks at ±2 bunch crossings in the LHC, and setting the '[var]_bx' to 0
        establishes that we are looking only at the current bunch crossing data.
        The energies are stored in the L1TNtuple trees all in the same leaf,
        and the way to separate each energy type is through the sum_type flag.
        """
        sums_feats = ['sumType', 'sumBx', 'sumIEt', 'sumIPhi']
        sums_data = self._level1_trigger_tree.arrays(sums_feats)
        # Convert everything to numpy arrays for easier manipulation.

        # Construct energy objects.
        self._store_ET(sums_data)
        self._store_HT(sums_data)
        self._store_MET(sums_data)
        self._store_MHT(sums_data)
        self._store_FET(sums_data)
        self._store_FHT(sums_data)
        print("Conversion of energy objects finished! \U0001F504")

    def _store_ET(self, sums_data: ak.Array):
        """Store the transverse energy event object to a numpy array and save to h5.

        The ETTEM feature refers to the missing transverse energy recorded by the
        electromagnetic calorimeter of the detector and only that.
        """
        ET_directory = self.output_path / "ET"
        ET_directory.mkdir(parents=True, exist_ok=True)
        ET_file = ET_directory / f'{self.output_filename}.parquet'

        data = {}
        for feature in self.energies['ET']:
            sum_type = self.energies['ET'][feature]
            mask = (sums_data['sumType'] == sum_type) & (sums_data['sumBx'] == 0)
            data[feature] = sums_data['sumIEt'][mask]

        data = ak.Array(data)
        ak.to_parquet(data, ET_file, compression='snappy')

    def _store_HT(self, sums_data: ak.Array):
        """Store the hardonic transverse energy event object.

        twr_count refers to the number of towers detected in the hadronic calorimeter.
        """
        HT_directory = self.output_path / "HT"
        HT_directory.mkdir(parents=True, exist_ok=True)
        HT_file = HT_directory / f'{self.output_filename}.parquet'

        data = {}
        for feature in self.energies['HT']:
            sum_type = self.energies['HT'][feature]
            mask = (sums_data['sumType'] == sum_type) & (sums_data['sumBx'] == 0)
            data[feature] = sums_data['sumIEt'][mask]

        data = ak.Array(data)
        ak.to_parquet(data, HT_file, compression='snappy')

    def _store_MET(self, sums_data: ak.Array):
        """Store the missing transverse energy event object."""
        MET_directory = self.output_path / "MET"
        MET_directory.mkdir(parents=True, exist_ok=True)
        MET_file = MET_directory / f'{self.output_filename}.parquet'

        data = {}
        for feature in self.energies['MET']:
            sum_type = self.energies['MET'][feature]
            mask = (sums_data['sumType'] == sum_type) & (sums_data['sumBx'] == 0)
            if 'phi' in feature:
                data[feature] = sums_data['sumIPhi'][mask]
            else:
                data[feature] = sums_data['sumIEt'][mask]

        data = ak.Array(data)
        ak.to_parquet(data, MET_file, compression='snappy')

    def _store_MHT(self, sums_data: ak.Array):
        """Store the missing hadronic transverse energy object."""
        MHT_directory = self.output_path / "MHT"
        MHT_directory.mkdir(parents=True, exist_ok=True)
        MHT_file = MHT_directory / f'{self.output_filename}.parquet'

        data = {}
        for feature in self.energies['MHT']:
            sum_type = self.energies['MHT'][feature]
            mask = (sums_data['sumType'] == sum_type) & (sums_data['sumBx'] == 0)
            if 'phi' in feature:
                data[feature] = sums_data['sumIPhi'][mask]
            else:
                data[feature] = sums_data['sumIEt'][mask]

        data = ak.Array(data)
        ak.to_parquet(data, MHT_file, compression='snappy')

    def _store_FET(self, sums_data: ak.Array):
        """Store the forward missing transverse energy event object.

        Missing transverse energy object that includes data from the hadronic forward
        calorimeter object, to a numpy array and save to h5.
        """
        FET_directory = self.output_path / "FET"
        FET_directory.mkdir(parents=True, exist_ok=True)
        FET_file = FET_directory / f'{self.output_filename}.parquet'

        data = {}
        for feature in self.energies['FET']:
            sum_type = self.energies['FET'][feature]
            mask = (sums_data['sumType'] == sum_type) & (sums_data['sumBx'] == 0)
            if 'phi' in feature:
                data[feature] = sums_data['sumIPhi'][mask]
            else:
                data[feature] = sums_data['sumIEt'][mask]

        data = ak.Array(data)
        ak.to_parquet(data, FET_file, compression='snappy')

    def _store_FHT(self, sums_data: ak.Array):
        """Store the forward missing transverse hadronic energy event object.

        Missing hadronic transverse energy object that includes data from the hadronic
        forward calorimeter object, to a numpy array and save to h5.
        """
        FHT_directory = self.output_path / "FHT"
        FHT_directory.mkdir(parents=True, exist_ok=True)
        FHT_file = FHT_directory / f'{self.output_filename}.parquet'

        data = {}
        for feature in self.energies['FHT']:
            sum_type = self.energies['FHT'][feature]
            mask = (sums_data['sumType'] == sum_type) & (sums_data['sumBx'] == 0)
            if 'phi' in feature:
                data[feature] = sums_data['sumIPhi'][mask]
            else:
                data[feature] = sums_data['sumIEt'][mask]

        data = ak.Array(data)
        ak.to_parquet(data, FHT_file, compression='snappy')

    def _store_cica(self):
        """Store the Cicada (Anomaly detector for calo) feature data into arrays."""
        if self._gtrigger_calos_tree is None:
            return

        cica_directory = self.output_path / "cica"
        cica_directory.mkdir(parents=True, exist_ok=True)
        cica_file = cica_directory / f'{self.output_filename}.parquet'

        data = self._gtrigger_calos_tree.arrays(self.cicada["cicada"])
        data = ak.Array({feature: data[feature] for feature in data.fields})

        ak.to_parquet(data, cica_file, compression='snappy')
        print("Conversion of cicada objects finished! \U0001F504")
