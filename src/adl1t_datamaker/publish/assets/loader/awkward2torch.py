# Stacking the ml-ready objects into the tensor a model is fed.

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import awkward as ak
import numpy as np
import pyarrow.parquet as pq
import torch

from . import common

log = logging.getLogger(__name__)

CACHE_NAMES = ("cache", "mask", "l1bit")


@dataclass
class L1DataAwkward2Torch:
    """Pad every object to a fixed size and stack them along the constituent axis.

    Objects are stacked in the alphabetical order of their files and features within an
    object in the alphabetical order of their names, so that a model trained on one split
    reads every other split the same way. ``object_feature_map`` records where each one
    landed and is written beside the tensors.

    :param nconst: ``{object: constituents kept}``. An object missing from it keeps as
        many as the split holds.
    """

    workers: int = 8
    nconst: dict = field(default_factory=dict)
    verbose: bool = False

    def __post_init__(self):
        self.object_feature_map = None

    def load_folder(self, folder_path) -> tuple:
        """One cached split as ``(data, mask, l1bit)``.

        ``data`` is (events, constituents, features) float32 and ``mask`` marks the slots
        that hold a real object rather than padding.
        """
        folder_path = Path(folder_path)
        cached = self._read_cache(folder_path)
        if cached is not None:
            return cached

        parts = self._process_folder(folder_path)
        data = torch.from_numpy(
            np.concatenate([values for _, _, values, _ in parts], axis=1)
        )
        mask = torch.from_numpy(
            np.concatenate([flags for _, _, _, flags in parts], axis=1)
        )

        return self._write_cache(
            folder_path, parts, (data, mask, _l1bit(folder_path, len(data)))
        )

    def _process_folder(self, folder_path: Path) -> list[tuple]:
        """Every object of one split, padded, in the order they are stacked in."""
        paths = _object_paths(folder_path)
        if not paths:
            raise FileNotFoundError(f"No ml-ready object files in {folder_path}.")

        with ThreadPoolExecutor(
            max_workers=min(self.workers, os.cpu_count() or 4)
        ) as pool:
            return list(pool.map(self._object_tensor, paths))

    def _object_tensor(self, path: Path) -> tuple:
        """One object file as (name, features, values, mask), padded to its size."""
        data = ak.from_parquet(path)
        nconst = common.as_dict(self.nconst).get(path.stem) or _max_constituents(data)
        padded = ak.pad_none(data, nconst, axis=-1, clip=True)
        mask = ak.Array({f: ~ak.is_none(padded[f], axis=-1) for f in padded.fields})
        padded = ak.values_astype(ak.fill_none(padded, 0.0), np.float32)

        return (
            path.stem,
            sorted(data.fields),
            _rectangular(padded),
            _rectangular(mask, bool),
        )

    def _read_cache(self, folder_path: Path) -> tuple | None:
        """The cached tensors, or None when they are absent or describe other columns."""
        paths = [folder_path / f"torch_{name}.pt" for name in CACHE_NAMES]
        listing = folder_path / "cached_objects.json"
        if not (listing.is_file() and all(path.is_file() for path in paths)):
            return None
        if json.loads(listing.read_text()) != self._listing(folder_path):
            log.warning(
                "Cached tensors in %s were built otherwise, rebuilding.", folder_path
            )
            return None

        self._read_feature_map(folder_path)

        return tuple(torch.load(path) for path in paths)

    def _write_cache(
        self, folder_path: Path, parts: list[tuple], tensors: tuple
    ) -> tuple:
        """Keep the tensors and the metadata a later run needs to trust them."""
        for name, tensor in zip(CACHE_NAMES, tensors):
            torch.save(tensor, folder_path / f"torch_{name}.pt")
        (folder_path / "cached_objects.json").write_text(
            json.dumps(self._listing(folder_path))
        )
        self.object_feature_map = _feature_map(parts)
        _map_path(folder_path).write_text(json.dumps(self.object_feature_map, indent=4))

        return tensors

    def _read_feature_map(self, folder_path: Path) -> None:
        """Where each feature sits in the flattened tensor, for undoing the normalisation."""
        if self.object_feature_map is None and _map_path(folder_path).is_file():
            self.object_feature_map = json.loads(_map_path(folder_path).read_text())

    def _listing(self, folder_path: Path) -> dict:
        """What a cached tensor is valid for: the columns read and the sizes asked of them.

        The ml-ready directory is named after the earlier stages but not after this one,
        so without the sizes a rerun with other constituent counts would be handed the
        tensor of the run before it.
        """
        nconst = common.as_dict(self.nconst)
        objects = {
            path.stem: sorted(pq.read_schema(path).names)
            for path in _object_paths(folder_path)
        }

        return {
            "columns": objects,
            "nconst": {name: nconst.get(name) for name in objects},
        }


def _object_paths(folder_path: Path) -> list[Path]:
    """The object files of one split. L1bit is a per-event verdict, not an object."""
    return sorted(p for p in folder_path.glob("*.parquet") if p.stem != "L1bit")


def _map_path(folder_path: Path) -> Path:
    """The feature map sits one level up, being the same for every split of a data set."""
    return folder_path.parent / "object_feature_map.json"


def _max_constituents(data: ak.Array) -> int:
    """The largest number of entries any event holds, for an object with no set size."""
    return max(1, *(int(ak.max(ak.num(data[f]), initial=0)) for f in data.fields))


def _rectangular(data: ak.Array, dtype=np.float32) -> np.ndarray:
    """(events, constituents, features), the features in alphabetical order."""
    columns = [ak.to_numpy(data[f], allow_missing=False) for f in sorted(data.fields)]

    return np.stack(columns, axis=-1).astype(dtype, copy=False)


def _feature_map(parts: list[tuple]) -> dict:
    """Where each object's features land once the tensor is flattened."""
    mapping, offset = {}, 0
    for name, feats, values, _ in parts:
        nconst, nfeats = values.shape[-2:]
        mapping[name] = {
            feat: [offset + c * nfeats + i for c in range(nconst)]
            for i, feat in enumerate(feats)
        }
        offset += nconst * nfeats

    return mapping


def _l1bit(folder_path: Path, nevents: int) -> torch.Tensor:
    """The trigger's verdict per event, all true for a split that carries none."""
    path = folder_path / "L1bit.parquet"
    if not path.is_file():
        log.warning("No L1bit in %s, taking every event as accepted.", folder_path)
        return torch.ones(nevents, dtype=torch.bool)

    # ravel rather than flatten: the record carries one verdict per event as a value,
    # the release tree it mirrors carries it as a one-element list.
    return torch.from_numpy(ak.to_numpy(ak.ravel(ak.from_parquet(path)["L1bit"])))
