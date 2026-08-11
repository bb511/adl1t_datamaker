# Building the HuggingFace mirror from the finished release tree.
# Same events, same order, same values: only the shape differs.

import json
import shutil
from pathlib import Path

import awkward as ak
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from adl1t_datamaker.publish import card, export

SHARD_BYTES = 500 * 1024**2

# HuggingFace reads this block and nothing else to file the page. It takes the licence
# from the identifier here and never opens the LICENSE file, so a record without one
# renders as unlicensed. cc0-1.0 names the dedication in publish.card.LICENCE.
FRONT_MATTER = """license: cc0-1.0
pretty_name: Trigger Anomaly Detection for New Physics at the LHC
size_categories:
- 10M<n<100M
tags:
- physics
- particle-physics
- anomaly-detection
- cms
- level-1-trigger
"""

# Collections joined into the main table. seeds takes a third of the volume on its own,
# so it gets its own config and travels separately.
MAIN_OBJECTS = (
    "ET",
    "FET",
    "FHT",
    "HT",
    "MET",
    "MHT",
    "egammas",
    "jets",
    "muons",
    "taus",
)

# Directories of publish/assets that ship with the mirror: the loading pipeline and the
# configuration tree that drives it.
ASSET_DIRS = ("loader", "configs")

# Carried into the seeds table as well, so that a menu decision can be matched to the
# event it belongs to rather than to a row number.
JOIN_COLUMNS = ("event", "order")


def build(
    tree: Path, hf_root: Path, labels: dict, only: list[str] | None = None
) -> dict:
    """Write the mirror and report the data files each config resolves to."""
    written = {}
    for split_dir in sorted(tree.glob("*/*/*")):
        dataset = split_dir.parent.name
        if not split_dir.is_dir() or (only and dataset not in only):
            continue
        _write_dataset_split(split_dir, dataset, labels[dataset], hf_root, written)

    return written


def read_split(split_dir: Path) -> dict:
    """One split directory of the release tree, as ``{object: awkward array}``."""
    return {
        obj.name: ak.from_arrow(pq.read_table(sorted(obj.glob("*.parquet"))))
        for obj in sorted(split_dir.iterdir())
        if obj.is_dir()
    }


def joined_table(split_dir: Path, dataset: str, label: int) -> pa.Table:
    """Zip one split's object collections into a single row-per-event table."""
    objects = read_split(split_dir)

    columns = _prefixed_columns(objects)
    event_level = list(objects.get("event_info", ak.Array([])).fields)
    for field in event_level:
        columns[field] = objects["event_info"][field]
    if "seeds" in objects and "L1bit" in objects["seeds"].fields:
        columns["L1bit"] = objects["seeds"]["L1bit"]
        event_level.append("L1bit")

    rows = len(next(iter(columns.values())))
    table = ak.to_arrow_table(ak.Array(columns), extensionarray=False)
    table = unwrapped(table, event_level).append_column("dataset", pa.array([dataset] * rows))

    return table.append_column("label", pa.array([label] * rows, type=pa.int16()))


def seeds_table(split_dir: Path, dataset: str) -> pa.Table | None:
    """The menu decision, kept apart from the kinematics because of its volume."""
    seeds_dir = split_dir / "seeds"
    if not seeds_dir.is_dir():
        return None

    table = pq.read_table(sorted(seeds_dir.glob("*.parquet"))).replace_schema_metadata(
        None
    )
    table = unwrapped(table, table.schema.names)
    for name, column in _join_columns(split_dir).items():
        table = table.append_column(name, column)

    return table.append_column("dataset", pa.array([dataset] * table.num_rows))


def unwrapped(table: pa.Table, names) -> pa.Table:
    """Turn the named one-entry-per-event columns into one value per event.

    The record stores every column as a list, which is the shape the collections need and
    the shape nothing else does: a one-element list is truthy whatever it holds, so a cut
    on a seed would keep every event, and it cannot be sorted or joined on. The
    collections are left alone, the energy sums with them, so that a column prefixed by a
    collection is a list and every other column is a value.
    """
    for name in names:
        column = table[name]
        if not (pa.types.is_list(column.type) or pa.types.is_large_list(column.type)):
            continue
        flat = pc.list_flatten(column)
        if len(flat) != table.num_rows:
            raise ValueError(
                f"{name} holds {len(flat)} values for {table.num_rows} events, so it is "
                "not one per event and cannot be unwrapped."
            )
        table = table.set_column(table.schema.get_field_index(name), name, flat)

    return table


def write_shards(table: pa.Table, out_dir: Path, split: str) -> int:
    """Write a table as HuggingFace-style ``<split>-NNNNN-of-NNNNN.parquet`` shards.

    The row count per shard is estimated from the table in memory, so the files on disk
    land near SHARD_BYTES rather than on it: parquet compresses and the ratio is not
    known until the bytes are written.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    _clear_shards(out_dir, split)
    per_shard = max(1, int(table.num_rows * SHARD_BYTES / max(table.nbytes, 1)))
    chunks = [table.slice(s, per_shard) for s in range(0, table.num_rows, per_shard)]
    for index, chunk in enumerate(chunks):
        pq.write_table(
            chunk,
            out_dir / f"{split}-{index:05d}-of-{len(chunks):05d}.parquet",
            compression="snappy",
        )

    return len(chunks)


def labels_for(summary: dict) -> dict:
    """Zero bias 0, simulated background negative, signals positive by sorted name."""
    labels, signal, background = {}, 0, 0
    for name in sorted(summary["datasets"]):
        category = summary["datasets"][name]["category"]
        if category == "zerobias":
            labels[name] = 0
        elif category == "background":
            background -= 1
            labels[name] = background
        else:
            signal += 1
            labels[name] = signal

    return labels


def configs_block(written: dict) -> str:
    """The ``configs:`` YAML that lets ``load_dataset`` find the files without a script."""
    lines = ["configs:"]
    for name in sorted(written):
        lines.append(f"- config_name: {name}")
        lines.append("  data_files:")
        for split, pattern in sorted(written[name].items()):
            # HuggingFace names the middle split "validation"; the record names it valid.
            lines.append(f"  - split: {'validation' if split == 'valid' else split}")
            lines.append(f"    path: {pattern}")

    return "\n".join(lines) + "\n"


def write_card(hf_root: Path, written: dict, summary: dict) -> None:
    """Write the card, whose front matter is what HuggingFace reads to find the data.

    A card copied without that block renders but does not load.
    """
    front = f"{FRONT_MATTER}{configs_block(written)}"
    body = card.render_hf(summary, labels_for(summary))
    (hf_root / "README.md").write_text(f"---\n{front}---\n\n{body}")
    (hf_root / "LICENSE").write_text(card.LICENCE)


def copy_assets(hf_root: Path) -> list[str]:
    """Copy the loading pipeline and its configuration tree into the mirror.

    Each directory is replaced rather than written over, so a file renamed or dropped
    here does not survive in a mirror built on top of an earlier one.
    """
    assets = Path(__file__).resolve().parent / "assets"
    for name in ASSET_DIRS:
        shutil.rmtree(hf_root / name, ignore_errors=True)
        shutil.copytree(
            assets / name, hf_root / name, ignore=shutil.ignore_patterns("__pycache__")
        )

    return list(ASSET_DIRS)


def read_summary(summary_path: Path) -> dict:
    """The frozen split summary, which fixes the labels and the counts the card quotes."""
    return json.loads(Path(summary_path).read_text())


def _clear_shards(out_dir: Path, split: str) -> None:
    """Drop shards an earlier run left, which a rerun writing fewer would not overwrite.

    They carry the old shard count in their names, so nothing overwrites them and the
    config's glob would read them as extra rows.
    """
    for shard in out_dir.glob(f"{split}-*.parquet"):
        shard.unlink()


def _join_columns(split_dir: Path) -> dict:
    """The event_info columns that match a seeds row to a main-table row."""
    table = pq.read_table(
        sorted((split_dir / "event_info").glob("*.parquet")), columns=list(JOIN_COLUMNS)
    )
    table = unwrapped(table, JOIN_COLUMNS)

    return {name: table[name].combine_chunks() for name in JOIN_COLUMNS}


def _prefixed_columns(objects: dict) -> dict:
    """One column per object field, named ``<collection>_<branch>``.

    The branch names are the record's own, so that a column of the mirror and the column
    of the tree it was taken from are called the same thing.
    """
    return {
        f"{name}_{field}": objects[name][field]
        for name in MAIN_OBJECTS
        if name in objects
        for field in objects[name].fields
    }


def _write_dataset_split(
    split_dir: Path, dataset: str, label: int, hf_root: Path, written: dict
) -> None:
    """Write one data set's split, both the joined table and its seeds."""
    split = split_dir.name
    table = joined_table(split_dir, dataset, label)
    write_shards(table, hf_root / "data" / dataset, split)
    written.setdefault(dataset, {})[split] = f"data/{dataset}/{split}-*.parquet"

    seeds = seeds_table(split_dir, dataset)
    if seeds is not None:
        write_shards(seeds, hf_root / "data" / dataset / "seeds", split)
        written.setdefault(f"{dataset}-seeds", {})[
            split
        ] = f"data/{dataset}/seeds/{split}-*.parquet"
    print(f"  {dataset:46s} {split:5s} {table.num_rows:>9,} rows")


def finish(hf_root: Path, written: dict, summary: dict) -> None:
    """Write the card, copy the loader, and clear the stray files before upload."""
    write_card(hf_root, written, summary)
    copy_assets(hf_root)
    export.prune_stray(hf_root)
