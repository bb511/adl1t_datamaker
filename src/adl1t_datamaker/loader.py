# Data loader class for the converted parquet files.
from pathlib import Path
from collections.abc import Iterator

import awkward as ak
import pyarrow
import pyarrow.dataset


class ParquetLoader(object):
    """Abstract reader class that reads parquet data sets created with Root2Parquet.

    :param root_folder_path: Folder holding one subfolder of parquet shards per object,
        as written by Root2Parquet.
    :param select_feats: Features to read, keyed by object name. ``None`` reads every
        feature of every object, and an object absent from the dictionary is not read
        at all.
    :param bs: Rows (events) held in memory at one time.
    :param threading: Whether pyarrow may read the shards on several threads.
    """

    def __init__(
        self,
        root_folder_path: str,
        select_feats: dict = None,
        bs: int = 1_000_000,
        threading: bool = True,
    ):
        super().__init__()
        self.root_folder_path = Path(root_folder_path)
        self.object_names = self._get_object_names()
        self.select_feats = self._get_select_feats(select_feats)
        self.batch_size = bs
        self.threading = threading

    def _get_object_names(self) -> list[str]:
        """Object names, taken from the root folder's subfolders holding parquet."""
        object_names = []
        for subdir in self.root_folder_path.iterdir():
            if subdir.is_dir() and any(subdir.glob("*.parquet")):
                object_names.append(subdir.name)

        return object_names

    def _get_select_feats(self, select_feats: dict) -> dict:
        """Build the select_feats dictionary.

        An object present in the data but missing from the caller's dictionary is
        marked ``'none'``, which _construct_dataset reads as "do not load this object".
        The string sentinel is distinct from a ``None`` value, which means every feature
        of that object. The caller's dictionary is never modified, so one dictionary can
        drive several loaders.
        """
        if select_feats is None:
            return {obj_name: None for obj_name in self.object_names}

        missing_obj_names = set(self.object_names) - set(select_feats.keys())

        return {**select_feats, **{obj: "none" for obj in missing_obj_names}}

    def _read_ds(self, data_path: Path, feats: list = None) -> pyarrow.dataset.Dataset:
        """Open the shards of one object, e.g. muons, as a scanner that streams them.

        :param feats: Columns to read. ``None`` reads every column.
        :raises ValueError: If any requested feature is absent from the shards.
        """
        data_files = sorted(list(data_path.glob("*.parquet")))
        dataset = pyarrow.dataset.dataset(data_files, format="parquet")
        if not self._feats_in_obj(feats, dataset):
            raise ValueError(f"Given features are not in data loaded from {data_path}")
        return dataset.scanner(
            columns=feats, batch_size=self.batch_size, use_threads=self.threading
        )

    def _feats_in_obj(self, feats: list, dataset: pyarrow.dataset.Dataset) -> bool:
        """Whether every selected feature exists, printing those that do not."""
        if feats is None:
            # None means "read every feature", so there is nothing to check.
            return True

        selected_feats = set(feats)
        all_feats = set(dataset.schema.names)

        diff_feats = selected_feats.difference(all_feats)
        if len(diff_feats) != 0:
            print(f"Missing features in data set present in select_feats: {diff_feats}")
        return selected_feats.issubset(all_feats)

    def _construct_dataset(self):
        pass


class Parquet2Awkward(ParquetLoader):
    """Reads a folder structure of parquet files to awkward arrays.

    The expected structure of the data folder is data/object1/*.parquet,
    data/object2/*.parquet etc.

    Given data = Parquet2Awkward(folder), ``data['muons']`` reads the whole muon data
    into memory, while ``data('muons')`` yields it batch by batch. Keyword arguments go
    to ParquetLoader, so the batches hold 1_000_000 events unless bs says otherwise.
    """

    def __init__(self, root_folder_path: str, **kwargs):
        super().__init__(root_folder_path, **kwargs)
        self.data = self._construct_dataset()

    def _construct_dataset(self) -> dict:
        """Construct the full data set out of the per-object pyarrow datasets.

        Objects that select_feats marks ``'none'`` are skipped, and self.object_names is
        narrowed to those loaded.
        """
        data = {}
        for obj_name in self.object_names:
            dataset_path = self.root_folder_path / obj_name
            if self.select_feats[obj_name] == "none":
                continue
            object_stream = self._read_ds(dataset_path, self.select_feats[obj_name])
            data[obj_name] = object_stream

        self.object_names = list(data.keys())

        return data

    def __call__(self, obj_name: str) -> Iterator[ak.Array]:
        for batch in self.data[obj_name].to_batches():
            yield ak.from_arrow(batch)

    def __getitem__(self, obj_name: str) -> ak.Array:
        return ak.from_arrow(self.data[obj_name].to_table())
