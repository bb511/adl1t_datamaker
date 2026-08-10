# Building the HuggingFace mirror from the finished release tree.
# Same events, same order, same values: only the shape differs.

import json
from pathlib import Path

import awkward as ak
import pyarrow as pa
import pyarrow.parquet as pq

from adl1t_datamaker.publish import export
from adl1t_datamaker.publish.assets import adl1t_l1ad as l1

SHARD_BYTES = 500 * 1024**2

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


def joined_table(split_dir: Path, dataset: str, label: int) -> pa.Table:
    """Zip one split's object collections into a single row-per-event table."""
    objects = l1.read_split(split_dir)
    renamed = l1.rename_fields(objects)

    columns = _prefixed_columns(renamed)
    for field in objects.get("event_info", ak.Array([])).fields:
        columns[field] = objects["event_info"][field]
    if "seeds" in objects and "L1bit" in objects["seeds"].fields:
        columns["L1bit"] = objects["seeds"]["L1bit"]

    rows = len(next(iter(columns.values())))
    table = ak.to_arrow_table(ak.Array(columns), extensionarray=False)
    table = table.append_column("dataset", pa.array([dataset] * rows))

    return table.append_column("label", pa.array([label] * rows, type=pa.int16()))


def seeds_table(split_dir: Path, dataset: str) -> pa.Table | None:
    """The menu decision, kept apart from the kinematics because of its volume."""
    seeds_dir = split_dir / "seeds"
    if not seeds_dir.is_dir():
        return None

    table = pq.read_table(sorted(seeds_dir.glob("*.parquet"))).replace_schema_metadata(
        None
    )

    return table.append_column("dataset", pa.array([dataset] * table.num_rows))


def write_shards(table: pa.Table, out_dir: Path, split: str) -> int:
    """Write a table as HuggingFace-style ``<split>-NNNNN-of-NNNNN.parquet`` shards.

    The row count per shard is estimated from the table in memory, so the files on disk
    land near SHARD_BYTES rather than on it: parquet compresses and the ratio is not
    known until the bytes are written.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
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


def write_card(tree: Path, hf_root: Path, written: dict) -> None:
    """Copy the record's card with the configs block as YAML front matter.

    HuggingFace reads the front matter and nothing else to locate the data files, so a
    card copied without it renders but does not load.
    """
    body = (tree / "README.md").read_text()
    (hf_root / "README.md").write_text(f"---\n{configs_block(written)}---\n\n{body}")
    (hf_root / "LICENSE").write_text((tree / "LICENSE").read_text())


def copy_assets(hf_root: Path) -> list[str]:
    """Copy the reader that ships with the record into the mirror."""
    assets = Path(l1.__file__).resolve().parent
    copied = [p for p in sorted(assets.glob("*.py")) if p.name != "__init__.py"]
    for asset in copied:
        (hf_root / asset.name).write_text(asset.read_text())

    return [p.name for p in copied]


def read_labels(summary_path: Path) -> dict:
    """Sample labels, taken from the frozen split summary."""
    return labels_for(json.loads(summary_path.read_text()))


def _prefixed_columns(renamed: dict) -> dict:
    """One column per object field, named ``<collection>_<field>``."""
    return {
        f"{name}_{field}": renamed[name][field]
        for name in MAIN_OBJECTS
        if name in renamed
        for field in renamed[name].fields
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


def finish(tree: Path, hf_root: Path, written: dict) -> None:
    """Write the card, copy the reader, and clear the stray files before upload."""
    write_card(tree, hf_root, written)
    copy_assets(hf_root)
    export.prune_stray(hf_root)
