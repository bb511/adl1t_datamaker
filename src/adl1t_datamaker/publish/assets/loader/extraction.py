# Reading the published tables back into one file per object collection.
#
# The record stores one row per event, with every object collection flattened into
# <collection>_<branch> columns. Undoing that flattening is all that separates the
# published layout from the converter's own output, which every stage after this one is
# written against.

import logging
from dataclasses import dataclass
from pathlib import Path

import awkward as ak
import pyarrow as pa
import pyarrow.parquet as pq

from . import common

log = logging.getLogger(__name__)

# Column prefixes that name an object collection. A prefix missing from here marks an
# event-level column, which is what keeps nPV_True whole rather than splitting it in two.
OBJECTS = ("ET", "FET", "FHT", "HT", "MET", "MHT", "egammas", "jets", "muons", "taus")


@dataclass
class L1DataExtractor:
    """Turn the published tables into one parquet file per object collection.

    :param select_features: ``{object: [branch names]}`` to read, named as the record
        names them. An object mapped to ``none``, or left out, is not extracted.
    :param feat_name_map: ``{object: {branch name: short name}}``, applied on the way
        out, so that everything downstream sees Et, eta and phi.
    :param cache_root_dir: Root of the extracted, processed and ml-ready caches.
    :param name: Names this extraction; the caches built on top of it inherit it.
    """

    select_features: dict
    feat_name_map: dict
    cache_root_dir: str = "data"
    name: str = "default"
    verbose: bool = False

    def extract(self, datasets: dict, data_category: str) -> None:
        """Extract every data set of one category.

        :param datasets: ``{data set: directory holding its published shards}``.
        :param data_category: ``zerobias``, ``background`` or ``signal``.
        """
        self.feats = _selected(self.select_features)
        self.renames = common.as_dict(self.feat_name_map)
        root = Path(self.cache_root_dir) / "extracted" / self.name / data_category
        for name, dataset_dir in common.as_dict(datasets).items():
            if common.cached(root / name, [*self.feats, common.SPLIT_INDEX]):
                log.info("Extracted %s exists at %s.", name, root / name)
                continue
            self._extract_dataset(Path(dataset_dir), root / name)

    def _extract_dataset(self, dataset_dir: Path, out_dir: Path) -> None:
        """Stream one data set's shards into one file per object collection.

        The seeds travel in files of their own, so they are read in a second pass. Both
        passes walk the splits in the same order, which is what keeps the object files
        row aligned without a key to join on.
        """
        shards = _shards(dataset_dir)
        if not shards:
            log.warning("No shards under %s, so %s is left out.", dataset_dir, out_dir.name)
            return

        out_dir.mkdir(parents=True, exist_ok=True)
        writers = {}
        for shard in shards:
            _stream(writers, out_dir, self._objects(pq.read_table(shard)))
        for shard in self._seed_shards(dataset_dir):
            _stream(writers, out_dir, {"seeds": _read(shard, self.feats["seeds"])})
        for writer in writers.values():
            writer.close()
        _check_aligned(out_dir)
        log.info("Cached extracted data at %s.", out_dir)

    def _objects(self, table: pa.Table) -> dict:
        """One shard regrouped by object collection, with the split index alongside."""
        objects = {common.SPLIT_INDEX: ak.from_arrow(table.select(common.INDEX_COLUMNS))}
        for obj, feats in self.feats.items():
            if obj != "seeds":
                objects[obj] = self._collection(table, obj, feats)

        return objects

    def _collection(self, table: pa.Table, obj: str, feats: list[str]) -> ak.Array:
        """One object's columns, under the short names the pipeline works with."""
        prefix = f"{obj}_" if obj in OBJECTS else ""
        mapping = self.renames.get(obj, {})
        array = ak.from_arrow(table.select([f"{prefix}{feat}" for feat in feats]))

        return ak.Array({mapping.get(f, f): array[f"{prefix}{f}"] for f in feats})

    def _seed_shards(self, dataset_dir: Path) -> list[Path]:
        """The menu shards, which only matter when the configuration asks for seeds."""
        return _shards(dataset_dir / "seeds") if "seeds" in self.feats else []


def _selected(select_features) -> dict:
    """The objects actually asked for. 'none' is how a configuration leaves one out."""
    return {
        obj: list(feats)
        for obj, feats in common.as_dict(select_features).items()
        if feats and feats != "none"
    }


def _shards(dataset_dir: Path) -> list[Path]:
    """One data set's shards, split by split, so the row order is the published one."""
    return [
        shard
        for split in common.SPLITS
        for shard in sorted(dataset_dir.glob(f"{split}-*.parquet"))
    ]


def _read(shard: Path, feats: list[str]) -> ak.Array:
    return ak.from_arrow(pq.read_table(shard, columns=list(feats)))


def _check_aligned(out_dir: Path) -> None:
    """Refuse a seeds file of a length the events cannot explain.

    The two passes pair a menu decision with its event by row number alone, so a copy of
    the record that is missing shards on one side of the pair would otherwise go through
    and hand every later event another event's trigger decision.
    """
    seeds = out_dir / "seeds.parquet"
    if not seeds.is_file():
        return

    rows = pq.read_metadata(seeds).num_rows
    events = pq.read_metadata(out_dir / f"{common.SPLIT_INDEX}.parquet").num_rows
    if rows != events:
        raise ValueError(
            f"{out_dir.name}: {rows:,} seed rows against {events:,} events. Shards are "
            "missing from the downloaded record, so the two cannot be paired."
        )


def _stream(writers: dict, out_dir: Path, objects: dict) -> None:
    """Append each object's rows to its file, opening the writer on first sight."""
    for obj, array in objects.items():
        table = ak.to_arrow_table(array, extensionarray=False)
        path = out_dir / f"{obj}.parquet"
        if path not in writers:
            writers[path] = pq.ParquetWriter(path, table.schema, compression="snappy")
        writers[path].write_table(table)
