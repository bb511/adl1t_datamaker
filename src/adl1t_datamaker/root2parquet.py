# Script that extracts the global trigger data from the L1TNtuples and saves it into
# parquet files, one folder per object. Not all the global trigger objects are saved to
# the parquets, since some objects/features are not useful for analysis; docs/README.md
# says which are kept and what each feature means.

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

    :param mc: Whether the input file contains Monte Carlo simulation. Data (``False``)
        has its ``nPV_True`` overwritten with the brilcalc pileup of the run and
        luminosity section of each event.
    :param l1_tree_name: Path within the root file of the tree holding the trigger
        objects and the energy sums, e.g. ``l1UpgradeEmuTree/L1UpgradeTree`` for the
        emulated branches or ``l1UpgradeTree/L1UpgradeTree`` for the unpacked ones.
    :param uGT_tree_name: Path within the root file of the tree holding the global
        trigger decision bits.
    :param event_tree_name: Path within the root file of the tree holding the run,
        luminosity section and event metadata.
    :param calosumm_tree_name: Path within the root file of the calorimeter summary
        tree. ``None`` skips the CICADA object, which lives only in that tree.
    :param silent: Whether to swallow the progress prints of the storing methods.
        Default is ``False``.
    """

    def __init__(
        self,
        mc: bool,
        l1_tree_name: str,
        uGT_tree_name: str,
        event_tree_name: str,
        calosumm_tree_name: str = None,
        silent: bool = False,
    ):
        self.l1_tree_name = l1_tree_name
        self.uGT_tree_name = uGT_tree_name
        self.event_tree_name = event_tree_name
        self.calosumm_tree_name = calosumm_tree_name
        self.silent = silent
        self.mc = mc

        # Branch names as they appear in the level 1 tree. See docs/README.md for the
        # meaning, hardware units and bit width of every feature listed here.
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

        # Each feature maps to the sumType flag that picks it out of the single sums
        # branch of the level 1 tree. The Et and phi of an object share a flag, since
        # they are two fields of the same entry: the feature name decides whether
        # sumIEt or sumIPhi is read.
        self.energies = {
            "ET": {"Et": 0, "ETTEM": 16},
            "HT": {"Et": 1, "tower_count": 21},
            "MET": {"Et": 2, "phi": 2},
            "MHT": {"Et": 3, "phi": 3},
            "FET": {"Et": 8, "phi": 8},
            "FHT": {"Et": 20, "phi": 20},
        }

        # CICADA scores the calorimeter towers for anomaly. It sits in the calorimeter
        # summary tree, so it is missing unless calosumm_tree_name was given.
        self.cicada = {"cicada": ["CICADAScore"]}

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
        apriori (see docs/README.md for more details).

        :param input_file: Local path or ``root://`` URL of the input L1TNtuple.
        :param prescale_file: Prescale menu (csv) whose unprescaled seeds become the
            columns of the seeds parquet.
        :param pileup_folder: Folder of brilcalc files, one per run. Only read for data,
            so it is ignored when the converter was built with ``mc=True``.
        :param output_path: Gains one subfolder per object, each holding a parquet named
            after the stem of the input file.
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
        allow_overwrite: bool = False,
    ):
        """Extract objects/features from folder of root files and convert to parquet.

        Include only the relevant quantities from each given TTree, which are defined
        apriori (see docs/README.md for more details).

        :param folder: Local path or ``root://`` URL of a folder of L1TNtuples. One tree
            configuration serves them all, so every root file in it must have the same
            structure.
        :param prescale_file: Prescale menu (csv) whose unprescaled seeds become the
            columns of the seeds parquet.
        :param pileup_folder: Folder of brilcalc files, one per run. Only read for data,
            so it is ignored when the converter was built with ``mc=True``.
        :param output_path: Gains one subfolder per object, each holding a parquet named
            after the stem of the input file.
        :param ncores: Number of files converted at the same time, one joblib worker
            each.
        :param allow_overwrite: Whether to permit replacing parquet already in the
            output folder. Default is ``False``.
        :raises ValueError: If the folder holds no root file.
        :raises FileExistsError: If an input stem would overwrite parquet already in the
            output folder and ``allow_overwrite`` is ``False``.
        """
        self.input_folder = util.check_xrootd_path(folder)
        self.prescale_file = Path(prescale_file)
        self.pileup_folder = Path(pileup_folder)
        self.output_path = Path(output_path)

        files_to_convert = util.glob(self.input_folder, "*.root")
        if not files_to_convert:
            raise ValueError(tcols.FAIL + f"{self.input_folder} is empty!" + tcols.ENDC)

        self._reject_overwrites(files_to_convert, allow_overwrite)

        print(tcols.HEADER + f"\nConverting {self.input_folder} to pq!" + tcols.ENDC)

        processes = joblib.Parallel(n_jobs=ncores)
        processes(
            joblib.delayed(self._conversion)(input_file)
            for input_file in files_to_convert
        )

        print(tcols.OKGREEN + f"Conversion of {self.input_folder} done!" + tcols.ENDC)
        print(tcols.OKGREEN + f"Files saved to {self.output_path}." + tcols.ENDC)

    def _reject_overwrites(self, files_to_convert: list, allow_overwrite: bool):
        """Refuse to clobber parquet produced from a different input file.

        Output files are named after the input stem, and convert_run maps several
        input folders onto a single output folder, so a stem repeated across those
        folders would silently replace the earlier conversion.
        """
        already_there = self.output_path / "seeds"
        if allow_overwrite or not already_there.is_dir():
            return

        stems = {Path(f).stem for f in files_to_convert}
        clashes = sorted(stems & {p.stem for p in already_there.glob("*.parquet")})
        if clashes:
            raise FileExistsError(
                tcols.FAIL + f"{len(clashes)} file(s) from {self.input_folder} would "
                f"overwrite parquet already in {self.output_path}, e.g. {clashes[:3]}. "
                "Pass allow_overwrite=True to reconvert on purpose." + tcols.ENDC
            )

    def _conversion(self, input_file: str):
        """Convert a root L1TNtuple file to a parquet file.

        The state of the file being converted (the open root file, its trees, the output
        stem) is kept on the instance, so running this concurrently is safe only under
        joblib's process backend, where each worker holds its own copy of the converter.
        """
        print(tcols.OKGREEN + f"Converting {input_file}..." + tcols.ENDC)

        self.output_path.mkdir(parents=True, exist_ok=True)
        self.output_filename = Path(input_file).stem

        self._input_file_root = uproot.open(input_file)
        self._level1_trigger_tree = self._input_file_root[self.l1_tree_name]
        self._global_trigger_tree = self._input_file_root[self.uGT_tree_name]
        self._gtrigger_event_tree = self._input_file_root[self.event_tree_name]
        if not self.calosumm_tree_name is None:
            self._gtrigger_calos_tree = self._input_file_root[self.calosumm_tree_name]
        else:
            self._gtrigger_calos_tree = None

        self.nentries = self._level1_trigger_tree.num_entries

        if self.silent:
            with contextlib.redirect_stdout(io.StringIO()) as f:
                self._store_objects()
        else:
            self._store_objects()

    def _store_objects(self) -> None:
        """Store objects of interest to the parquet files."""
        self._store_seeds()
        self._store_eventinfo()
        self._store_muons()
        self._store_jets()
        self._store_egammas()
        self._store_taus()
        self._store_energies()
        self._store_cica()

    def _store_seeds(self):
        """Store the level 1 global trigger seeds to a given parquet file.

        One boolean column per seed the prescale menu leaves unprescaled, True where the
        event passed that algorithm, plus the L1bit column that get_level1_seeds adds as
        the OR over all of them. The final decision bits are used, so the global trigger
        rules that veto an otherwise accepted event are already folded in.
        """
        seeds_directory = self.output_path / "seeds"
        seeds_directory.mkdir(parents=True, exist_ok=True)
        seeds_file = seeds_directory / f"{self.output_filename}.parquet"

        initial_decision_bits = l1_seeds.get_initial_decision(self._global_trigger_tree)
        final_decision_bits = l1_seeds.get_final_decision(self._global_trigger_tree)

        algo_map = l1_seeds.get_algo_map(self._global_trigger_tree)
        algo_map = l1_seeds.filter_algo_map(self.prescale_file, algo_map)
        seeds = l1_seeds.get_level1_seeds(algo_map, final_decision_bits)

        seeds = ak.Array(seeds)
        # Give the seeds the layout every other object folder has: wrapping each event
        # in a length-1 list takes (nevents, nfeats) to (nevents, 1, nfeats), the one
        # object being the event itself.
        seeds = ak.singletons(seeds)
        ak.to_parquet(seeds, seeds_file, compression="snappy")

    def _store_eventinfo(self):
        """Store the event information data and save to given parquet.

        For data, nPV_True as it comes out of the tree is replaced by the brilcalc
        pileup of the run and luminosity section of the event.
        """
        einfo_directory = self.output_path / "event_info"
        einfo_directory.mkdir(parents=True, exist_ok=True)
        einfo_file = einfo_directory / f"{self.output_filename}.parquet"

        event_data = self._gtrigger_event_tree.arrays(self.event_info["event_info"])
        if not self.mc:
            event_data = pileup.add_pileup_info(self.pileup_folder, event_data)

        # As for the seeds: (nevents, nfeats) becomes (nevents, 1, nfeats) so that every
        # object folder shares one layout.
        event_data = ak.singletons(event_data)
        ak.to_parquet(event_data, einfo_file, compression="snappy")

    def _store_muons(self):
        """Store the muon feature data and save to parquet."""
        muons_directory = self.output_path / "muons"
        muons_directory.mkdir(parents=True, exist_ok=True)
        muons_file = muons_directory / f"{self.output_filename}.parquet"

        data = self._level1_trigger_tree.arrays(self.particles["muons"])

        # The trigger records the two bunch crossings either side of the triggered one,
        # so Bx == 0 keeps the central crossing. The other objects below are cut the
        # same way, leaving a variable number of objects per event.
        mask = self._level1_trigger_tree.arrays(["muonBx"])["muonBx"] == 0

        data = ak.Array({feature: data[feature][mask] for feature in data.fields})

        ak.to_parquet(data, muons_file, compression="snappy")
        print("Conversion of muon objects finished! \U0001f504")

    def _store_jets(self):
        """Store the jets feature data and save to parquet."""
        jets_directory = self.output_path / "jets"
        jets_directory.mkdir(parents=True, exist_ok=True)
        jets_file = jets_directory / f"{self.output_filename}.parquet"

        data = self._level1_trigger_tree.arrays(self.particles["jets"])
        mask = self._level1_trigger_tree.arrays(["jetBx"])["jetBx"] == 0
        data = ak.Array({feature: data[feature][mask] for feature in data.fields})

        ak.to_parquet(data, jets_file, compression="snappy")
        print("Conversion of jet objects finished! \U0001f504")

    def _store_egammas(self):
        """Store the electron/gamma feature data and save to parquet."""
        egammas_directory = self.output_path / "egammas"
        egammas_directory.mkdir(parents=True, exist_ok=True)
        egammas_file = egammas_directory / f"{self.output_filename}.parquet"

        data = self._level1_trigger_tree.arrays(self.particles["egammas"])
        mask = self._level1_trigger_tree.arrays(["egBx"])["egBx"] == 0
        data = ak.Array({feature: data[feature][mask] for feature in data.fields})

        ak.to_parquet(data, egammas_file, compression="snappy")
        print("Conversion of egamma objects finished! \U0001f504")

    def _store_taus(self):
        """Store the taus feature data and save to parquet."""
        taus_directory = self.output_path / "taus"
        taus_directory.mkdir(parents=True, exist_ok=True)
        taus_file = taus_directory / f"{self.output_filename}.parquet"

        data = self._level1_trigger_tree.arrays(self.particles["taus"])
        mask = self._level1_trigger_tree.arrays(["tauBx"])["tauBx"] == 0
        data = ak.Array({feature: data[feature][mask] for feature in data.fields})

        ak.to_parquet(data, taus_file, compression="snappy")
        print("Conversion of tau objects finished! \U0001f504")

    def _store_energies(self):
        """Store the different types of energies associated with the event.

        Every sum sits in the same leaf of the L1TNtuple, one entry per (sumType, bunch
        crossing), so each object below is picked out by its sumType flag and by
        sumBx == 0, the central of the five bunch crossings the trigger records. The
        values stay in hardware units: sumIEt counts 0.5 GeV and sumIPhi counts
        2*pi/144 (see docs/README.md).
        """
        sums_feats = ["sumType", "sumBx", "sumIEt", "sumIPhi"]
        sums_data = self._level1_trigger_tree.arrays(sums_feats)

        self._store_ET(sums_data)
        self._store_HT(sums_data)
        self._store_MET(sums_data)
        self._store_MHT(sums_data)
        self._store_FET(sums_data)
        self._store_FHT(sums_data)
        print("Conversion of energy objects finished! \U0001f504")

    def _store_ET(self, sums_data: ak.Array):
        """Store the transverse energy event object and save to parquet.

        ETTEM is the total transverse energy seen by the electromagnetic calorimeter
        alone, not a missing energy.
        """
        ET_directory = self.output_path / "ET"
        ET_directory.mkdir(parents=True, exist_ok=True)
        ET_file = ET_directory / f"{self.output_filename}.parquet"

        data = {}
        for feature in self.energies["ET"]:
            sum_type = self.energies["ET"][feature]
            mask = (sums_data["sumType"] == sum_type) & (sums_data["sumBx"] == 0)
            data[feature] = sums_data["sumIEt"][mask]

        data = ak.Array(data)
        ak.to_parquet(data, ET_file, compression="snappy")

    def _store_HT(self, sums_data: ak.Array):
        """Store the hadronic transverse energy event object.

        tower_count is not an energy: sum type 21 carries the number of towers measured
        in the hadronic calorimeter, delivered through the same sumIEt field as the
        energies.
        """
        HT_directory = self.output_path / "HT"
        HT_directory.mkdir(parents=True, exist_ok=True)
        HT_file = HT_directory / f"{self.output_filename}.parquet"

        data = {}
        for feature in self.energies["HT"]:
            sum_type = self.energies["HT"][feature]
            mask = (sums_data["sumType"] == sum_type) & (sums_data["sumBx"] == 0)
            data[feature] = sums_data["sumIEt"][mask]

        data = ak.Array(data)
        ak.to_parquet(data, HT_file, compression="snappy")

    def _store_MET(self, sums_data: ak.Array):
        """Store the missing transverse energy event object."""
        MET_directory = self.output_path / "MET"
        MET_directory.mkdir(parents=True, exist_ok=True)
        MET_file = MET_directory / f"{self.output_filename}.parquet"

        data = {}
        for feature in self.energies["MET"]:
            sum_type = self.energies["MET"][feature]
            mask = (sums_data["sumType"] == sum_type) & (sums_data["sumBx"] == 0)
            if "phi" in feature:
                data[feature] = sums_data["sumIPhi"][mask]
            else:
                data[feature] = sums_data["sumIEt"][mask]

        data = ak.Array(data)
        ak.to_parquet(data, MET_file, compression="snappy")

    def _store_MHT(self, sums_data: ak.Array):
        """Store the missing hadronic transverse energy object."""
        MHT_directory = self.output_path / "MHT"
        MHT_directory.mkdir(parents=True, exist_ok=True)
        MHT_file = MHT_directory / f"{self.output_filename}.parquet"

        data = {}
        for feature in self.energies["MHT"]:
            sum_type = self.energies["MHT"][feature]
            mask = (sums_data["sumType"] == sum_type) & (sums_data["sumBx"] == 0)
            if "phi" in feature:
                data[feature] = sums_data["sumIPhi"][mask]
            else:
                data[feature] = sums_data["sumIEt"][mask]

        data = ak.Array(data)
        ak.to_parquet(data, MHT_file, compression="snappy")

    def _store_FET(self, sums_data: ak.Array):
        """Store the forward missing transverse energy event object.

        Missing transverse energy computed with the hadronic forward calorimeter
        included, which MET leaves out.
        """
        FET_directory = self.output_path / "FET"
        FET_directory.mkdir(parents=True, exist_ok=True)
        FET_file = FET_directory / f"{self.output_filename}.parquet"

        data = {}
        for feature in self.energies["FET"]:
            sum_type = self.energies["FET"][feature]
            mask = (sums_data["sumType"] == sum_type) & (sums_data["sumBx"] == 0)
            if "phi" in feature:
                data[feature] = sums_data["sumIPhi"][mask]
            else:
                data[feature] = sums_data["sumIEt"][mask]

        data = ak.Array(data)
        ak.to_parquet(data, FET_file, compression="snappy")

    def _store_FHT(self, sums_data: ak.Array):
        """Store the forward missing transverse hadronic energy event object.

        Missing hadronic transverse energy computed with the hadronic forward
        calorimeter included, which MHT leaves out.
        """
        FHT_directory = self.output_path / "FHT"
        FHT_directory.mkdir(parents=True, exist_ok=True)
        FHT_file = FHT_directory / f"{self.output_filename}.parquet"

        data = {}
        for feature in self.energies["FHT"]:
            sum_type = self.energies["FHT"][feature]
            mask = (sums_data["sumType"] == sum_type) & (sums_data["sumBx"] == 0)
            if "phi" in feature:
                data[feature] = sums_data["sumIPhi"][mask]
            else:
                data[feature] = sums_data["sumIEt"][mask]

        data = ak.Array(data)
        ak.to_parquet(data, FHT_file, compression="snappy")

    def _store_cica(self):
        """Store the CICADA (calo anomaly detector) scores, if a calo tree was given."""
        if self._gtrigger_calos_tree is None:
            return

        cica_directory = self.output_path / "cica"
        cica_directory.mkdir(parents=True, exist_ok=True)
        cica_file = cica_directory / f"{self.output_filename}.parquet"

        data = self._gtrigger_calos_tree.arrays(self.cicada["cicada"])
        data = ak.Array({feature: data[feature] for feature in data.fields})

        ak.to_parquet(data, cica_file, compression="snappy")
        print("Conversion of cicada objects finished! \U0001f504")
