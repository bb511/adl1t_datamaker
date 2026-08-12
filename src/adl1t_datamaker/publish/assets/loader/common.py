# Pieces the stages share: the split vocabulary and the published split index.

from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from omegaconf import OmegaConf

# The record is published pre-split. Zero bias carries all three; the simulated samples
# are validation data and carry valid and test alone.
SPLITS = ("train", "valid", "test")

# Object file holding the published split of each event and its position within that
# split. The extract stage writes it whatever select_features asks for, because every
# stage after it addresses rows by split.
SPLIT_INDEX = "splits"

INDEX_COLUMNS = ("split", "order")


def as_dict(config) -> dict:
    """A plain dict, whether the caller passed one or a hydra node."""
    if OmegaConf.is_config(config):
        return OmegaConf.to_container(config, resolve=True)

    return dict(config)


def objects_in(directory: Path) -> list[str]:
    """The object collections cached in one directory."""
    return sorted(path.stem for path in Path(directory).glob("*.parquet"))


def cached(directory: Path, names) -> bool:
    """Whether every named object is already cached in this directory.

    An empty listing counts as nothing cached, so that a data set whose directory is
    missing or empty is reported by the stage that reads it rather than skipped.
    """
    names = list(names)

    return bool(names) and all(
        (Path(directory) / f"{name}.parquet").is_file() for name in names
    )


def datasets_in(directory: Path) -> list[Path]:
    """The data set directories of one category, in name order."""
    directory = Path(directory)

    return (
        sorted(p for p in directory.iterdir() if p.is_dir())
        if directory.is_dir()
        else []
    )


def split_rows(paths: list[Path]) -> dict[str, np.ndarray]:
    """Row numbers of each split, in the order the study drew them.

    The two zero-bias runs were permuted together, so their rows interleave and ``order``
    counts across the whole split rather than within one run. Concatenating the runs and
    sorting by it therefore rebuilds the study's own ordering. Events its cut removed
    carry ``order = -1``, were never permuted, and go last.
    """
    index = pa.concat_tables([pq.read_table(path) for path in paths])
    order = index["order"].combine_chunks().to_numpy(zero_copy_only=False)
    names = pc.unique(index["split"].combine_chunks()).to_pylist()

    return {
        name: _ordered(_rows_of(index["split"], name), order) for name in sorted(names)
    }


def _rows_of(column, name: str) -> np.ndarray:
    """Rows belonging to one split, in file order."""
    return np.flatnonzero(
        pc.equal(column, name).combine_chunks().to_numpy(zero_copy_only=False)
    )


def _ordered(rows: np.ndarray, order: np.ndarray) -> np.ndarray:
    """One split's rows, sorted by their position in it, unplaced rows kept at the end."""
    placed = rows[order[rows] >= 0]
    placed = placed[np.argsort(order[placed], kind="stable")]

    return np.concatenate([placed, rows[order[rows] < 0]])
