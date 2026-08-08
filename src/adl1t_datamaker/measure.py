# Measuring a converted data set: the file inventory and the one streaming pass.
#
# This module produces numbers and nothing else: summary.py assembles them, report.py
# renders them and figures.py plots them.
#
# Every folder holds one row per event, but not at the same depth: the particle folders
# are jagged, (events, objects in the event), the energy sums are jagged with at most one
# entry per event, seeds and event_info went through ak.singletons and so are (events, 1),
# and cica is flat, (events,). Flattening a column therefore gives one entry per event for
# seeds, event_info and cica, but not for the particle folders, nor for a sum an event
# lacks.

import hashlib
from pathlib import Path

import awkward as ak
import numpy as np
import pyarrow.parquet as pq

from adl1t_datamaker import schema
from adl1t_datamaker import stats
from adl1t_datamaker.loader import Parquet2Awkward

# The overall level 1 accept, synthesised by l1_seeds as the OR of every other seed, so
# counting it as a seed would add one to the fired count of every accepted event.
L1BIT = "L1bit"

# Joint counts key on integers, and brilcalc reports pileup as a per-luminosity-section
# average (its avgpu column). A run spans a narrow band of pileup, so whole units would
# leave a few bins; tenths keep the resolution. figures.py divides the axis back out.
PILEUP_SCALE = 10


class ObjectCounts:
    """Exact counts for one object folder, accumulated over streamed batches.

    `rows` counts events, since every folder stores one row per event whatever its depth.
    """

    def __init__(self, name: str, documented: dict):
        self.name = name
        self.documented = documented
        self.features: dict[str, stats.ValueCounts] = {}
        self.multiplicity = stats.ValueCounts()
        self.seed_multiplicity = stats.ValueCounts()
        self.occupancy: dict = {}
        self.pairs: dict = {}
        self.event_keys: list = []
        self.rows = 0

    def update(self, batch: ak.Array) -> None:
        """Fold one batch of one object in.

        Each column is flattened once and the array reused by every counter below: the
        seeds folder holds a few hundred columns, so converting each one again per counter
        would dominate the pass. The flattened columns run one entry per event for seeds,
        event_info and cica, and one entry per object elsewhere.
        """
        self.rows += len(batch)
        columns = {name: flat(batch[name]) for name in sorted(batch.fields)}
        for name, values in columns.items():
            self.features.setdefault(name, stats.ValueCounts()).update(values)
        self._update_multiplicity(batch, columns)
        self._update_occupancy(columns)
        self._update_run_lumi(columns)

    def _update_multiplicity(self, batch: ak.Array, columns: dict) -> None:
        self.multiplicity.update(counts_per_event(batch))
        if self.name == "seeds":
            self.seed_multiplicity.update(seeds_per_event(columns, len(batch)))

    def _update_occupancy(self, columns: dict) -> None:
        wanted = schema.OCCUPANCY_COLUMNS.get(self.name)
        if wanted and all(column in columns for column in wanted):
            stats.count_pairs(self.occupancy, *(columns[column] for column in wanted))

    def _update_run_lumi(self, columns: dict) -> None:
        """The (run, lumi) map and the event identifiers, for coverage and duplicates."""
        if self.name != "event_info" or not {"run", "lumi", "event"} <= set(columns):
            return
        run, lumi, event = (columns[name] for name in ("run", "lumi", "event"))
        stats.count_pairs(self.pairs, run, lumi)
        packed = _pack_event_key(run, lumi, event)
        self.event_keys = None if packed is None else (self.event_keys or []) + [packed]

    def duplicate_events(self) -> int | None:
        """Identifiers occurring more than once, or None when they could not be packed.

        The keys of every batch are held to the end of the pass, since a repeat can span
        batches. A batch too wide to pack drops the store to None, which a later packable
        batch clears again: the check assumes a field that overflows its slot does so for
        the whole data set rather than for one batch.
        """
        if self.event_keys is None or not self.event_keys:
            return None if self.event_keys is None else 0
        keys = np.concatenate(self.event_keys)

        return int(keys.size - np.unique(keys).size)


def flat(array: ak.Array) -> np.ndarray:
    """One object's column as a flat numpy array, jagged or not."""
    return ak.to_numpy(ak.flatten(array, axis=None))


def counts_per_event(batch: ak.Array) -> np.ndarray:
    """How many entries each event holds, which is 1 throughout for a flat column.

    The converter stores one CICADA score per event rather than a list, so cica arrives
    one deep rather than two and ak.num would raise on it. The first column answers for
    the whole folder, whose columns all carry the same event structure.
    """
    column = batch[sorted(batch.fields)[0]]
    if column.ndim < 2:
        return np.ones(len(batch), dtype=np.int16)

    return ak.to_numpy(ak.num(column, axis=1))


def seeds_per_event(columns: dict, events: int) -> np.ndarray:
    """How many seeds fired per event, excluding the synthesised overall accept.

    :param columns: One flat boolean array per seed, each holding one entry per event
        because the seeds folder is ak.singletons-wrapped.
    :param events: Events in the batch, which every column must match in length.
    """
    fired = np.zeros(events, dtype=np.int16)
    for name, values in columns.items():
        if name != L1BIT:
            fired += values

    return fired


def measure(folder: Path, batch_size: int, objects: list[str] | None = None) -> dict:
    """Stream every object folder once, returning the accumulated counts per object.

    :param folder: Root of the converted data set, one subfolder of shards per object.
    :param batch_size: Largest number of events pyarrow puts in one batch.
    :param objects: Restricts the pass to these object folders, every column of each.
        None reads every folder.
    :returns: One ObjectCounts per folder, keyed by folder name.
    """
    documented = schema.documented_features()
    loader = Parquet2Awkward(str(folder), bs=batch_size, select_feats=_selection(objects))
    measured = {}
    for name in sorted(loader.object_names):
        measured[name] = ObjectCounts(name, documented.get(name, {}))
        for batch in loader(name):
            measured[name].update(batch)

    return measured


def inventory(folder: Path, checksums: bool = True) -> dict:
    """Per object shard counts, rows, bytes and schema, read from the parquet footers.

    :param folder: Root of the converted data set, one subfolder of shards per object.
    :param checksums: Adds a sha256 per shard, which reads every shard in full rather
        than its footer alone.
    :returns: One entry per subfolder holding at least one parquet file.
    """
    return {
        directory.name: _object_inventory(directory, checksums)
        for directory in sorted(folder.iterdir())
        if directory.is_dir() and any(directory.glob("*.parquet"))
    }


def pileup_against_towers(folder: Path) -> dict:
    """Joint counts of event pileup and HCAL tower count, paired shard by shard.

    Pairing goes shard by shard rather than by zipping two streams: pyarrow takes batch
    boundaries from each data set's own row groups, so batches from the two folders need
    not line up event for event. An event_info shard with no HT shard of the same name is
    left out.

    :returns: Counts keyed by (pileup in tenths, tower count), over events carrying both.
    """
    joint: dict = {}
    for shard in sorted((folder / "event_info").glob("*.parquet")):
        towers = folder / "HT" / shard.name
        if towers.is_file():
            _add_pileup_towers(joint, shard, towers)

    return joint


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)

    return digest.hexdigest()


def _selection(objects: list[str] | None) -> dict | None:
    """Read every column of every object unless the caller named the objects it wants."""
    return None if not objects else {name: None for name in objects}


def _object_inventory(directory: Path, checksums: bool) -> dict:
    shards = sorted(directory.glob("*.parquet"))
    files = [_shard_inventory(shard, checksums) for shard in shards]
    # Every shard of an object comes from the same branch selection, so the first one's
    # schema stands for all of them; nothing here compares one shard against another.
    first = pq.ParquetFile(shards[0]).schema_arrow

    return {
        "shards": len(shards),
        "rows": sum(shard["rows"] for shard in files),
        "bytes": sum(shard["bytes"] for shard in files),
        "row_groups": sum(shard["row_groups"] for shard in files),
        "dtypes": {name: str(first.field(name).type) for name in sorted(first.names)},
        "compression": _compression(shards[0]),
        "files": files,
    }


def _shard_inventory(shard: Path, checksums: bool) -> dict:
    metadata = pq.ParquetFile(shard).metadata
    entry = {
        "name": shard.name,
        "rows": metadata.num_rows,
        "bytes": shard.stat().st_size,
        "row_groups": metadata.num_row_groups,
    }

    return entry | ({"sha256": sha256(shard)} if checksums else {})


def _compression(shard: Path) -> list[str]:
    metadata = pq.ParquetFile(shard).metadata
    if not metadata.num_row_groups:
        return []
    # The converter writes a shard with one codec, so the first row group speaks for it.
    group = metadata.row_group(0)

    return sorted({group.column(i).compression for i in range(group.num_columns)})


def _add_pileup_towers(joint: dict, event_shard: Path, towers_shard: Path) -> None:
    """Pair one shard's pileup with its tower count, over events that carry both."""
    pileup, has_pileup = _first_entries(event_shard, "nPV_True")
    towers, has_towers = _first_entries(towers_shard, "tower_count")
    if len(has_pileup) != len(has_towers):
        return  # misaligned shards are a validation finding, not something to plot
    both = has_pileup & has_towers
    binned = np.rint(pileup[both] * PILEUP_SCALE).astype(np.int64)

    stats.count_pairs(joint, binned, towers[both])


# (run, lumi, event) packed into one key: run in bits 44..62, lumi in 32..43, event in
# 0..31. The budget is 19 + 12 + 32 = 63 bits, leaving the sign bit of the int64 clear.
RUN_SHIFT, LUMI_SHIFT = 44, 32
KEY_LIMITS = (1 << 19, 1 << 12, 1 << 32)


def _pack_event_key(run: np.ndarray, lumi: np.ndarray, event: np.ndarray):
    """One integer per event identifier, or None when a field is too wide to pack.

    Packing rather than hashing keeps the duplicate check exact. Width is judged on the
    batch maximum, and a field that overflows its slot returns None, so an unusual run
    or event number makes the check report itself as not performed rather than answer
    wrongly.
    """
    if any(int(part.max()) >= limit for part, limit in zip((run, lumi, event), KEY_LIMITS)):
        return None
    packed = (run.astype(np.int64) << RUN_SHIFT) | (lumi.astype(np.int64) << LUMI_SHIFT)

    return packed | event.astype(np.int64)


def _first_entries(shard: Path, name: str) -> tuple[np.ndarray, np.ndarray]:
    """First entry of each event, zero-filled, and a mask of events that had one.

    The energy sums can hold no entry at all for an event, and the mask is what keeps such
    an event out of the joint counts instead of entering it there as a genuine zero.
    """
    values = ak.from_arrow(pq.read_table(shard, columns=[name]))[name]
    if values.ndim < 2:
        return ak.to_numpy(values), np.ones(len(values), dtype=bool)
    present = ak.to_numpy(ak.num(values, axis=1)) > 0

    return ak.to_numpy(ak.fill_none(ak.firsts(values), 0)), present
