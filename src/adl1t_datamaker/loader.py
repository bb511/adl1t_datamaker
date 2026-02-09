# Data loader class for the converted parquet files.
from pathlib import Path
from collections.abc import Iterator

import awkward as ak
import pyarrow
import pyarrow.dataset


class ParquetLoader(object):
    """Abstract reader class that reads parquet file datasets created with Root2Parquet.

    Args:
        root_folder_path: Path to the root folder where subfolders with parquet files
            are stored.
        select_features: Dictionary of objects and their corresponding features to
            select from the whole data. If None, then read everything.
        bs: Int specifying the batch size of samples loaded in memory at one time.
        threading: Bool whether to use threading in loading the parquet files.
    """
    def __init__(
        self,
        root_folder_path: str,
        select_feats: dict = None,
        bs: int = 1_000_000,
        threading: bool = True
    ):
        super().__init__()
        self.root_folder_path = Path(root_folder_path)
        self.object_names = self._get_object_names()
        self.select_feats = self._get_select_feats(select_feats)
        self.batch_size = bs
        self.threading = threading

    def _get_object_names(self) -> list[str]:
        """Get the names of the objects.

        Infer the names of the objects constituting the data set from the names of the
        folders that are found within the root folder instantiated with this class.
        """
        object_names = []
        for subdir in self.root_folder_path.iterdir():
            if subdir.is_dir() and any(subdir.glob('*.parquet')):
                object_names.append(subdir.name)

        return object_names

    def _get_select_feats(self, select_feats: dict) -> dict:
        """Build the select_feats dictionary.

        If an object that is present in the data is missing from this dictionary, do not
        load this object.
        """
        if select_feats is None:
            select_feats = {obj_name: None for obj_name in self.object_names}
        if select_feats:
            missing_obj_names = set(self.object_names) - set(select_feats.keys())
            missing_objs = {obj_name: 'none' for obj_name in missing_obj_names}
            select_feats.update(missing_objs)

        return select_feats

    def _read_ds(self, data_path: Path, feats: list = None) -> pyarrow.dataset.Dataset:
        """Read a dataset, e.g., muons, to a pyarrow dataset that streams the data."""
        data_files = sorted(list(data_path.glob('*.parquet')))
        dataset = pyarrow.dataset.dataset(data_files, format="parquet")
        if not self._feats_in_obj(feats, dataset):
            raise ValueError(f"Given features are not in data loaded from {data_path}")
        return dataset.scanner(
            columns=feats, batch_size=self.batch_size, use_threads=self.threading
        )

    def _feats_in_obj(self, feats: list, dataset: pyarrow.dataset.Dataset) -> bool:
        """Checks if the features selected by the user actually exits."""
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

    The expected structure if the data folder is data/object1/*.parquet,
    data/object2/*.parquet etc.

    When you instantiate this object, e.g., data = Parquet2Awkward(folder), use
        data['muons'] to load the full muon data
        data('muons') to generate an interator that iterates through the muon data

    The default batch size for the iterator is 1_000_000 events.
    """
    def __init__(self, root_folder_path: str, **kwargs):
        super().__init__(root_folder_path, **kwargs)
        self.data = self._construct_dataset()

    def _construct_dataset(self) -> dict:
        """Construct the full dataset out of pyarrow object-related datasets.

        Skip loading objects for which no features are loaded.
        """
        data = {}
        for obj_name in self.object_names:
            dataset_path = self.root_folder_path / obj_name
            if self.select_feats[obj_name] == 'none':
                continue
            object_stream = self._read_ds(dataset_path, self.select_feats[obj_name])
            data[obj_name] = object_stream

        # Rewrite object_names list to contain only objects that are loaded.
        self.object_names = list(data.keys())

        return data

    def __call__(self, obj_name: str) -> Iterator[ak.Array]:
        for batch in self.data[obj_name].to_batches():
            yield ak.from_arrow(batch)

    def __getitem__(self, obj_name: str) -> ak.Array:
        return ak.from_arrow(self.data[obj_name].to_table())
