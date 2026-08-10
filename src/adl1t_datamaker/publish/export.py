# Partitioning a converted data set into the published train/valid/test tree.
#
# The split is a frozen map in the scripts/publish folder, one (split, order) pair per
# raw row, drawn once by the study this data was produced for and carried with the data
# ever since.
#
# Each object's thousands of shards are consolidated into a single file, in the
# lexicographic order the map was built against.

import hashlib
import subprocess
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.dataset as pds
import pyarrow.parquet as pq
from joblib import Parallel, delayed

# Size a shard reaches on disk before the writer rolls over to the next one. Parquet is
# snappy-compressed, so the table in memory that produced it is several times larger.
SHARD_BYTES = 500 * 1024**2

# Rows taken out of a consolidated file at once. Bounds peak memory, not output layout.
TAKE_CHUNK = 1_000_000

SPLITS = ("train", "valid", "test")

# Directories a converted data set holds that are not object collections. PLOTS and
# SUMMARY are the datamaker's own output about the data. cica is the CICADA score, which
# is another anomaly trigger's verdict rather than detector input, and is excluded from
# the release along with the L1_CICADA_* seed bits.
SKIP_OBJECTS = {"PLOTS", "SUMMARY", "cica"}

# Fixed timestamp, stripped ownership. Repeating a pack then gives byte-identical
# archives, which is what lets a reader who rebuilds one check it against the published
# sha256sums.
SOURCE_DATE = "UTC 2026-01-01"

STRAY_GLOBS = (".DS_Store", "._*", ".AppleDouble", "Thumbs.db")


def raw_objects(dataset_dir: Path) -> list[str]:
    """Object collections to publish from one converted data set."""
    return sorted(
        p.name
        for p in dataset_dir.iterdir()
        if p.is_dir() and p.name not in SKIP_OBJECTS and any(p.glob("*.parquet"))
    )


def dataset_rows(dataset_dir: Path) -> int:
    """Events in one converted data set, counted on its event_info shards."""
    return pds.dataset(
        _shards(dataset_dir, "event_info"), format="parquet"
    ).count_rows()


def event_fingerprint(dataset_dir: Path) -> str:
    """sha256 over the event numbers of one data set, in raw row order.

    The frozen map addresses raw rows by position, so it holds only for the row order
    consolidate reproduces. Reconverting the same ntuples preserves that order and
    converting a different set of files does not, and no other column in the tree would
    reveal the difference.
    """
    digest = hashlib.sha256()
    dataset = pds.dataset(_shards(dataset_dir, "event_info"), format="parquet")
    for batch in dataset.to_batches(columns=["event"]):
        digest.update(batch["event"].flatten().to_numpy(zero_copy_only=False).tobytes())

    return digest.hexdigest()


def check_dataset(
    name: str, raw_dir: Path, expected: int, fingerprint: str | None
) -> None:
    """Refuse a data set the frozen map no longer describes.

    :param expected: Rows the map covers.
    :param fingerprint: Event fingerprint recorded when the map was built, or ``None``
        for a map predating them, which leaves only the row count to check.
    :raises ValueError: If either the row count or the event order disagrees.
    """
    rows = dataset_rows(raw_dir)
    if rows != expected:
        raise ValueError(
            f"{name} holds {rows} rows but its split map covers {expected}."
        )

    if fingerprint and event_fingerprint(raw_dir) != fingerprint:
        raise ValueError(
            f"{name} has the row count its split map expects but not the event order it "
            "was built against, so the map would scramble it."
        )


def read_split_map(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Per-raw-row split name and position within that split, from a frozen map.

    Two encodings are read. The original stores the names directly in a ``<U5`` array;
    the compact one stores ``int8`` indices into a ``names`` codebook, which holds the
    same content in a twentieth of the bytes.
    """
    with np.load(path, allow_pickle=False) as data:
        if "names" not in data:
            return data["split"], data["order"]

        return np.asarray(data["names"])[data["split"]], data["order"]


def split_row_order(split_of: np.ndarray, order: np.ndarray, name: str) -> np.ndarray:
    """Raw row numbers of one split, in the order the release writes them.

    Rows the study saw come first, in its permutation order, so reading a split front to
    back reproduces its input. The events its cut removed carry ``order = -1``, were
    never permuted, and are appended afterwards in raw order.
    """
    in_split = np.flatnonzero(split_of == name)
    seen = in_split[order[in_split] >= 0]
    seen = seen[np.argsort(order[seen], kind="stable")]

    return np.concatenate([seen, in_split[order[in_split] < 0]])


def consolidate(dataset_dir: Path, obj: str, out_path: Path) -> int:
    """Stream one object's shards into a single file, preserving raw row order.

    Idempotent: an existing file counts as already consolidated, so a rerun after a
    failure resumes instead of starting over.
    """
    if out_path.is_file():
        return pq.ParquetFile(out_path).metadata.num_rows

    out_path.parent.mkdir(parents=True, exist_ok=True)

    return _stream_into(_shards(dataset_dir, obj), out_path)


def consolidate_dataset(
    name: str, raw_dir: Path, work: Path, ncores: int
) -> dict[str, Path]:
    """Consolidate every published object of one data set, one job per object."""
    objects = raw_objects(raw_dir)
    paths = [work / name / f"{obj}.parquet" for obj in objects]
    Parallel(n_jobs=ncores)(
        delayed(consolidate)(raw_dir, obj, path) for obj, path in zip(objects, paths)
    )

    return dict(zip(objects, paths))


def export_dataset(
    name: str,
    category: str,
    raw_dir: Path,
    split_map: Path,
    work: Path,
    tree: Path,
    ncores: int = 1,
) -> dict[str, int]:
    """Partition every object of one data set into its split directories."""
    split_of, order = read_split_map(split_map)
    objects = consolidate_dataset(name, raw_dir, work, ncores)

    counts = {}
    for split in sorted(set(split_of.tolist())):
        rows = split_row_order(split_of, order, split)
        counts[split] = len(rows)
        _write_objects(objects, rows, order, tree / category / name / split)

    return counts


def export_all(
    index: dict,
    split_summary: dict,
    splitmap: Path,
    work: Path,
    tree: Path,
    ncores: int = 1,
) -> dict[str, dict]:
    """Check every data set against its frozen map, then partition them all.

    Checking runs to completion first, so a stale map is reported before hours of
    writing rather than after them.
    """
    for name, entry in sorted(index.items()):
        expected = split_summary["datasets"][name]["raw_events"]
        check_dataset(name, Path(entry["raw_dir"]), expected, entry.get("fingerprint"))

    counts = {}
    for name, entry in sorted(index.items()):
        counts[name] = export_dataset(
            name,
            entry["category"],
            Path(entry["raw_dir"]),
            splitmap / f"{entry['category']}__{name}.npz",
            work,
            tree,
            ncores,
        )
        print(f"  {name:46s} {counts[name]}")

    prune_stray(tree)

    return counts


def write_manifest(path: Path, version: str, counts: dict, index: dict) -> dict:
    """Record what the release is beyond the data: per-split counts and its provenance."""
    # Imported here rather than at module scope, because summary reaches matplotlib
    # through figures and an export has no use for it.
    from adl1t_datamaker import summary

    payload = {
        "dataset_version": version,
        "generated": summary.generated_block(),
        "datasets": {
            name: {"category": index[name]["category"], "counts": counts[name]}
            for name in sorted(counts)
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    summary.write_json(payload, path)

    return payload


def write_split(
    source: Path, rows: np.ndarray, out_dir: Path, extra: dict | None = None
) -> int:
    """Take rows out of a consolidated object file and write them as sharded parquet.

    :param extra: Per-row columns appended to every chunk, keyed by column name and
        indexed the same way as ``rows``.
    """
    _clear_shards(out_dir)
    dataset = pds.dataset(source, format="parquet")
    tables = (
        _take(dataset, rows[start : start + TAKE_CHUNK], extra, start)
        for start in range(0, len(rows), TAKE_CHUNK)
    )

    return _write_shards(tables, out_dir)


def drop_excluded_columns(table: pa.Table) -> pa.Table:
    """Remove the CICADA trigger bits from a table.

    The menu carries L1_CICADA_* decisions at several working points. Those are another
    anomaly trigger's output rather than detector input, so they leave the release along
    with the CICADA score itself.
    """
    keep = [n for n in table.schema.names if "cicada" not in n.lower()]
    if len(keep) == len(table.schema.names):
        return table

    # The inherited metadata still names the dropped columns, and awkward refuses a file
    # whose metadata lists a column the data lacks, so it has to go with them. These
    # tables are flat, so nothing is lost.
    return table.select(keep).replace_schema_metadata(None)


def tar_cmd(tree: Path, members, out_path: Path) -> list[str]:
    """GNU tar invocation recording no owner, no timestamp and no absolute path.

    :param tree: Directory tar runs from, which the members are relative to.
    """
    return [
        "tar",
        "--sort=name",
        "--owner=0",
        "--group=0",
        "--numeric-owner",
        f"--mtime={SOURCE_DATE}",
        "--format=pax",
        "--pax-option=delete=atime,delete=ctime",
        "--no-acls",
        "--no-xattrs",
        "--no-selinux",
        "-C",
        str(tree),
        "-cf",
        str(out_path),
        *[str(m) for m in members],
    ]


def split_members(tree: Path) -> dict[str, list[str]]:
    """Split directories of the exported tree, relative to it, grouped by split."""
    members = {}
    for split_dir in sorted(tree.glob("*/*/*")):
        if split_dir.is_dir():
            members.setdefault(split_dir.name, []).append(
                str(split_dir.relative_to(tree))
            )

    return members


def pack(tree: Path, payload: Path) -> list[Path]:
    """Assemble the upload: one archive per split, plus the card and the licence.

    A reader who wants only the training data then downloads one archive. Each archive
    spans every data set, since zero bias is the only source of train while the
    simulated samples supply valid and test.
    """
    payload.mkdir(parents=True, exist_ok=True)
    members = split_members(tree)
    written = [
        _pack_split(tree, split, members[split], payload)
        for split in SPLITS
        if split in members
    ]
    _copy_loose(tree, payload)

    return written


def write_checksums(payload: Path) -> Path:
    """sha256 every payload file, in the format ``sha256sum -c`` reads."""
    lines = [
        f"{sha256(path)}  ./{path.name}"
        for path in sorted(payload.iterdir())
        if path.is_file() and path.name != "sha256sums.txt"
    ]
    out_path = payload / "sha256sums.txt"
    out_path.write_text("\n".join(lines) + "\n")

    return out_path


def sha256(path: Path) -> str:
    """sha256 of a file, read a megabyte at a time so a 1.5 GB archive fits in memory."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024**2), b""):
            digest.update(block)

    return digest.hexdigest()


def prune_stray(root: Path) -> list[Path]:
    """Delete the macOS and Windows files that record directory listings and download URLs."""
    removed = []
    for pattern in STRAY_GLOBS:
        for path in root.rglob(pattern):
            path.unlink()
            removed.append(path)

    return removed


def _shards(dataset_dir: Path, obj: str) -> list[Path]:
    """One object's parquet shards, in the order the frozen map was built against."""
    return sorted((dataset_dir / obj).glob("*.parquet"))


def _stream_into(shards: list[Path], out_path: Path) -> int:
    """Append every shard to one file, taking the schema from the first.

    The seeds schema differs between recorded data and simulation, which run different
    menus, but it is fixed within a data set, so one schema serves all of its shards.
    """
    writer, rows = None, 0
    try:
        for shard in shards:
            table = pq.read_table(shard)
            if writer is None:
                writer = pq.ParquetWriter(out_path, table.schema, compression="snappy")
            writer.write_table(table)
            rows += table.num_rows
    finally:
        if writer is not None:
            writer.close()

    return rows


def _write_objects(
    objects: dict, rows: np.ndarray, order: np.ndarray, split_dir: Path
) -> None:
    """Write one split of every object, giving event_info its two extra columns."""
    for obj, consolidated in objects.items():
        extra = None
        if obj == "event_info":
            # So a file separated from its directory still says which split it belongs
            # to and where in that split's row order it sits.
            extra = {
                "split": [split_dir.name] * len(rows),
                "order": order[rows].tolist(),
            }
        write_split(consolidated, rows, split_dir / obj, extra)


def _take(
    dataset: pds.Dataset, chunk: np.ndarray, extra: dict | None, offset: int
) -> pa.Table:
    """One chunk of rows, with the per-row extra columns appended."""
    table = drop_excluded_columns(dataset.take(pa.array(chunk)))
    if not extra:
        return table

    for column, values in extra.items():
        table = table.append_column(
            column, pa.array(values[offset : offset + len(chunk)])
        )

    return table.replace_schema_metadata(None)


def _write_shards(tables, out_dir: Path) -> int:
    """Write tables into out_dir, rolling to a new shard once one passes SHARD_BYTES."""
    writer, index, path, written = None, 0, None, 0
    for table in tables:
        if writer is None:
            path = out_dir / f"{index:05d}.parquet"
            writer = pq.ParquetWriter(path, table.schema, compression="snappy")
        writer.write_table(table)
        written += table.num_rows
        if path.stat().st_size >= SHARD_BYTES:
            writer.close()
            writer, index = None, index + 1

    if writer is not None:
        writer.close()

    return written


def _clear_shards(out_dir: Path) -> None:
    """Drop shards an earlier run left, which a rerun writing fewer would not overwrite."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for shard in out_dir.glob("*.parquet"):
        shard.unlink()


def _pack_split(tree: Path, split: str, members: list[str], payload: Path) -> Path:
    """Write one split's archive."""
    out_path = payload / f"{split}.tar"
    subprocess.run(tar_cmd(tree, sorted(members), out_path), check=True)
    size = out_path.stat().st_size / 1024**3
    print(f"  packed {out_path.name} ({len(members)} data sets, {size:.1f} GB)")

    return out_path


def _copy_loose(tree: Path, payload: Path) -> None:
    """Copy the files that travel beside the archives rather than inside them."""
    for loose in ("README.md", "LICENSE"):
        if (tree / loose).is_file():
            (payload / loose).write_bytes((tree / loose).read_bytes())
