# Selecting the training features, normalising them, and caching one file per split.

import logging
from dataclasses import dataclass
from pathlib import Path

import awkward as ak
import numpy as np
import pyarrow as pa
import pyarrow.dataset as pds
import pyarrow.parquet as pq

from . import common

log = logging.getLogger(__name__)

CATEGORIES = ("background", "signal")


@dataclass
class L1DataMLReady:
    """Turn the processed data into the arrays a model is trained on.

    The split is not drawn here. The record is published pre-split and its ``splits``
    object carries that split, so this stage only has to read it. What it does decide is
    where the normalisation is fitted: on the training split alone, which is then applied
    unchanged to valid, to test and to every simulated sample.

    :param processed_datapath: The process stage's output, ``.../processed/<name>``.
    :param name: Names this cache; the normaliser's name is appended to it, so two
        schemes never share a directory.
    """

    processed_datapath: str
    cache_root_dir: str = "data"
    name: str = "default"
    verbose: bool = False

    def prepare(self, normalizer, select_feats: dict, flag: str = "") -> None:
        """Normalise and cache every split of the zero bias and of the simulations.

        :param flag: Subdirectory within each split, for keeping a second set of
            features beside the one a model trains on.
        """
        self.normalizer = normalizer
        self.select_feats = common.as_dict(select_feats)
        self.schema = set().union(*self.select_feats.values())
        self.cache_folder = Path(self.cache_root_dir) / "mlready" / self.name / normalizer.name
        self.flag = flag
        self._prepare_main()
        self._prepare_aux()

    def _prepare_main(self) -> None:
        """The zero bias, whose training split is the one the normalisation is fitted on."""
        objects = _merged_object_files(Path(self.processed_datapath) / "zerobias")
        if common.SPLIT_INDEX not in objects:
            raise FileNotFoundError(
                f"No processed zero bias under {self.processed_datapath}. The "
                "normalisation is fitted on its training split, so it cannot be skipped."
            )

        rows = common.split_rows(objects[common.SPLIT_INDEX])
        for split in common.SPLITS:
            if split in rows:
                out_dir = self.cache_folder / split
                self._cache_split(objects, rows[split], out_dir, fit=split == "train")

    def _prepare_aux(self) -> None:
        """The simulated samples, which are validation data and are never fitted on."""
        for category in CATEGORIES:
            for dataset_dir in common.datasets_in(Path(self.processed_datapath) / category):
                objects = _object_files(dataset_dir)
                out_dir = self.cache_folder / "aux" / dataset_dir.name
                for split, rows in common.split_rows(objects[common.SPLIT_INDEX]).items():
                    self._cache_split(objects, rows, out_dir / split, fit=False)

    def _cache_split(self, objects: dict, rows: np.ndarray, out_dir: Path, fit: bool) -> None:
        """One split of every selected object, normalised and padded to a common schema."""
        out_dir = out_dir / self.flag
        out_dir.mkdir(parents=True, exist_ok=True)
        for obj_name, feats in self.select_feats.items():
            if obj_name not in objects:
                log.warning("%s is trained on but was not extracted, so it is left out.", obj_name)
                continue
            self._cache_object(objects[obj_name], obj_name, feats, rows, out_dir, fit)
        _cache_l1bit(objects.get("seeds"), rows, out_dir)
        log.info("Cached ml-ready data at %s.", out_dir)

    def _cache_object(self, paths, obj_name, feats, rows, out_dir: Path, fit: bool) -> None:
        """Take one object's rows for this split, normalise them and write them out."""
        cache_file = out_dir / f"{obj_name}.parquet"
        # A cached file holds the features of the run that wrote it, and this directory
        # is not named after them, so a changed selection has to be rewritten.
        if cache_file.is_file() and set(pq.read_schema(cache_file).names) == self.schema:
            self._load_params(obj_name)
            return

        data = _take(paths, rows)[list(feats)]
        if fit:
            self.normalizer.fit(data, obj_name)
            self.normalizer.export_norm_params(self._params_path(obj_name), obj_name)
        else:
            self._load_params(obj_name)
        ak.to_parquet(_with_schema(self.normalizer.norm(data, obj_name), self.schema), cache_file)

    def _load_params(self, obj_name: str) -> None:
        """Read back what an earlier run fitted, so that a cached run can still denormalise."""
        if obj_name not in self.normalizer.norm_params:
            self.normalizer.import_norm_params(self._params_path(obj_name), obj_name)

    def _params_path(self, obj_name: str) -> Path:
        return self.cache_folder / f"{obj_name}_norm_params.pkl"


def _object_files(dataset_dir: Path) -> dict[str, list[Path]]:
    """One data set's objects, each as the single file holding it."""
    return {path.stem: [path] for path in sorted(dataset_dir.glob("*.parquet"))}


def _merged_object_files(category_dir: Path) -> dict[str, list[Path]]:
    """Every data set of one category, merged per object in data set order.

    The zero bias arrives as two runs whose rows were permuted together, so a split of it
    spans both directories and the files have to be read as one.
    """
    merged: dict[str, list[Path]] = {}
    for dataset_dir in common.datasets_in(category_dir):
        for obj, paths in _object_files(dataset_dir).items():
            merged.setdefault(obj, []).extend(paths)

    return merged


def _take(paths: list[Path], rows: np.ndarray) -> ak.Array:
    """The given rows of one object, read across the files that make up its split."""
    return ak.from_arrow(pds.dataset(paths, format="parquet").take(pa.array(rows)))


def _with_schema(data: ak.Array, schema: set) -> ak.Array:
    """Give an object the fields the others have, so that they stack into one tensor.

    A field an object has no counterpart for stays empty in every event, and the padding
    of the torch stage marks it as absent.
    """
    empty = ak.unflatten(ak.Array(np.empty(0, dtype=np.float32)), np.zeros(len(data), np.int64))
    for feature in sorted(schema - set(data.fields)):
        data = ak.with_field(data, empty, feature)

    return data


def _cache_l1bit(paths: list[Path] | None, rows: np.ndarray, out_dir: Path) -> None:
    """The trigger's own verdict on the same rows, kept for the rate comparisons."""
    if not paths or "L1bit" not in pq.read_schema(paths[0]).names:
        log.warning("No L1bit among the extracted seeds, so pure rates are unavailable.")
        return

    cache_file = out_dir / "L1bit.parquet"
    if not cache_file.is_file():
        ak.to_parquet(_take(paths, rows)[["L1bit"]], cache_file)
