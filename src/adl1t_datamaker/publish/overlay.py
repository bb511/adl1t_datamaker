# Giving a pile-up-free simulation the trigger objects of a recorded zero-bias event.
#
# The signal sample was digitised without pile-up (142XnoPU), so its events hold the
# hard scatter alone, while every recorded event beside them in the release sits on top
# of the simultaneous collisions of its own bunch crossing. Mixing the two at detector
# level would need the hits a re-digitisation reads, which the ntuples do not carry, so
# the overlay works at object level instead: each simulated event is paired with one
# recorded zero-bias event, their collections are concatenated and re-sorted by Et,
# their sums are added and clipped at the hardware codes, and their seeds are OR-ed.

import json
from pathlib import Path

import awkward as ak
import numpy as np
import pyarrow as pa
import pyarrow.dataset as pds
import pyarrow.parquet as pq

from adl1t_datamaker import schema
from adl1t_datamaker.publish import export

# Collections that hold several objects, each with the Et field its order is decided by.
COLLECTIONS = {
    "jets": "jetIEt",
    "egammas": "egIEt",
    "taus": "tauIEt",
    "muons": "muonIEt",
}

# Sums that add as plain scalars, with the all-ones code each field saturates at: twelve
# bits for the energies, thirteen for the tower count.
SCALARS = {
    "ET": {"Et": 4095, "ETTEM": 4095},
    "HT": {"Et": 4095, "tower_count": 8191},
}

# Sums carrying an angle as well, which add as two-dimensional vectors.
VECTORS = ("MET", "MHT", "FET", "FHT")

FULL = 4095
PHI_CODES = 144  # 2 * pi / schema.CALO_PHI_STEP

# What a converted event_info holds. The exported tree adds flat split and order columns
# beside them, which describe the release layout and not the event, so they are dropped.
EVENT_FIELDS = ("run", "lumi", "event", "bx", "orbit", "time", "nPV_True")

# The zero-bias runs, in the order their splits are concatenated into one pool. This is
# the order the card quotes as zb_order, and the partner indices address it.
ZEROBIAS = ("ZB_run396102", "ZB_run398183")


def read_raw(raw_dir: Path, obj: str) -> ak.Array:
    """One object of a converted data set, in raw row order."""
    table = pq.read_table(sorted((raw_dir / obj).glob("*.parquet")))

    # A conversion older than 2026-08-18 still carries the L1_AXO_* seeds, which are
    # another anomaly trigger's verdict and must not reach the OR below.
    return ak.from_arrow(export.drop_excluded_columns(table))


def zerobias_files(
    tree: Path, runs: tuple[str, ...], split: str, obj: str
) -> list[Path]:
    """One object's zero-bias shards of a split, run by run and then shard by shard."""
    return [
        shard
        for run in runs
        for shard in sorted((tree / "zerobias" / run / split / obj).glob("*.parquet"))
    ]


def pool_sizes(tree: Path, runs: tuple[str, ...], splits: list[str]) -> dict[str, int]:
    """Zero-bias events available to draw from, split by split."""
    return {
        split: pds.dataset(
            zerobias_files(tree, runs, split, "event_info"), format="parquet"
        ).count_rows()
        for split in splits
    }


def draw_partners(split_of: np.ndarray, pools: dict[str, int], seed: int) -> np.ndarray:
    """One zero-bias partner per raw row, drawn without replacement within its split.

    Drawing without replacement keeps the pile-up of two simulated events independent,
    and drawing within the split keeps a validation event away from the recorded events
    the test split holds.

    :param pools: Zero-bias events per split, which the drawn indices point into.
    :returns: Pool index per raw row, into the pool of that row's own split.
    """
    rng = np.random.default_rng(seed)
    partner = np.zeros(len(split_of), dtype=np.int64)
    for split in sorted(pools):
        rows = np.flatnonzero(split_of == split)
        partner[rows] = rng.choice(pools[split], size=len(rows), replace=False)

    return partner


def partner_rows(files: list[Path], idx: np.ndarray) -> pa.Table:
    """Rows of one zero-bias object, in the order idx names them."""
    return pds.dataset(files, format="parquet").take(pa.array(idx))


def partners_in_raw_order(
    tree: Path,
    runs: tuple[str, ...],
    split_of: np.ndarray,
    partner: np.ndarray,
    obj: str,
) -> ak.Array:
    """The drawn partners of one object, one per raw row and in raw row order.

    The rows are taken split by split, since a partner index means nothing outside its
    own pool, and put back into raw order afterwards.
    """
    splits = sorted(set(split_of.tolist()))
    rows = [np.flatnonzero(split_of == split) for split in splits]
    tables = [
        partner_rows(zerobias_files(tree, runs, split, obj), partner[in_split])
        for split, in_split in zip(splits, rows)
    ]
    table = _concat(tables).take(pa.array(np.argsort(np.concatenate(rows))))

    return ak.from_arrow(table.replace_schema_metadata(None))


def merge_collection(
    sig: ak.Array, zb: ak.Array, et_field: str, capacity: int
) -> ak.Array:
    """Both events' objects of one collection, hardest first and clipped to capacity.

    Clipping is what the global trigger does to a crowded event: it reads out a fixed
    number of objects and the softest ones beyond that are lost. The sort is stable, so
    a simulated object precedes a zero-bias object of equal Et.
    """
    both = ak.concatenate([sig, zb[sig.fields]], axis=1)
    idx = ak.argsort(both[et_field], axis=1, ascending=False, stable=True)

    return both[idx][:, :capacity]


def merge_scalars(sig: ak.Array, zb: ak.Array, limits: dict[str, int]) -> ak.Array:
    """Two events' scalar sums added and clipped at the all-ones hardware code.

    Added in int32, since two 12-bit codes overflow an int16 before the clip sees them.
    """
    merged = {}
    for field in sig.fields:
        total = _flat(sig, field).astype(np.int32) + _flat(zb, field).astype(np.int32)
        clipped = np.minimum(total, limits[field]).astype(np.int16)
        merged[field] = _singleton(clipped)

    return ak.Array(merged)


def vector_sum(
    et_a: np.ndarray, phi_a: np.ndarray, et_b: np.ndarray, phi_b: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Add two missing-energy sums as vectors, in and out in hardware codes.

    Phi is a code over PHI_CODES bins of the full 2*pi, so the addition runs in float64
    radians and is rounded back to a code. An input already at the saturation code
    leaves the result saturated, because the energy behind an all-ones code is unknown,
    and a null sum is given phi 0, the value an event with no missing energy carries.
    """
    x_a, y_a = _components(et_a, phi_a)
    x_b, y_b = _components(et_b, phi_b)
    x, y = x_a + x_b, y_a + y_b
    et = np.minimum(np.rint(np.hypot(x, y)), FULL)
    et[(et_a == FULL) | (et_b == FULL)] = FULL
    phi = np.rint(np.arctan2(y, x) / schema.CALO_PHI_STEP) % PHI_CODES
    phi[et == 0] = 0

    return et.astype(np.int16), phi.astype(np.int16)


def merge_vector(sig: ak.Array, zb: ak.Array) -> ak.Array:
    """Two missing-energy sums of one kind, added as vectors."""
    et, phi = vector_sum(
        _flat(sig, "Et"), _flat(sig, "phi"), _flat(zb, "Et"), _flat(zb, "phi")
    )

    return ak.Array({"Et": _singleton(et), "phi": _singleton(phi)})


def merge_seeds(sig: ak.Array, zb: ak.Array) -> ak.Array:
    """Both events' seed decisions OR-ed, with L1bit rebuilt over the result.

    An overlaid event fires an algorithm if either of its two halves did. The recorded
    events ran the 2025 menu against the simulation's 2024 one, so a seed the recorded
    menu lacks keeps the simulation's own decision. L1bit is the OR over the seeds
    present, which is how components.l1_seeds.get_level1_seeds defines it.
    """
    algos = [name for name in sig.fields if name != "L1bit"]
    merged = {name: _seed(sig, zb, name) for name in algos}
    merged["L1bit"] = np.logical_or.reduce([merged[name] for name in algos])

    return ak.Array({name: _singleton(merged[name]) for name in sig.fields})


def merge_event_info(sig: ak.Array, zb: ak.Array) -> ak.Array:
    """The partner's event information, which is the one the overlaid event carries.

    The pile-up an overlaid event holds is the pile-up of the recorded event that
    supplied it, and the run, luminosity section and bunch crossing that identify that
    pile-up are the partner's too. The simulated event has no such coordinates.
    """
    return zb[list(sig.fields)]


def merge(obj: str, sig: ak.Array, zb: ak.Array) -> ak.Array:
    """One object of a simulated event overlaid with its zero-bias partner's."""
    if obj in COLLECTIONS:
        capacity = schema.documented_capacities()[obj]
        return merge_collection(sig, zb, COLLECTIONS[obj], capacity)
    if obj in SCALARS:
        return merge_scalars(sig, zb, SCALARS[obj])
    if obj in VECTORS:
        return merge_vector(sig, zb)
    if obj == "seeds":
        return merge_seeds(sig, zb)
    if obj == "event_info":
        return merge_event_info(sig, zb)

    raise ValueError(f"{obj} has no overlay rule.")


def reranked_order(
    order: np.ndarray, split_of: np.ndarray, saturated: np.ndarray
) -> np.ndarray:
    """The frozen row order with the events the overlay saturated taken out of it.

    Adding pile-up pushes some events onto the ET saturation code, which the release
    drops. The survivors keep the relative order the study drew and are renumbered
    contiguously within their split, so reading a split front to back still reproduces
    that permutation.

    :param saturated: Per raw row, whether the overlaid ET.Et reached the all-ones code.
    :returns: Position within the split, -1 for a row the release drops.
    """
    new = np.full_like(order, -1)
    for split in sorted(set(split_of.tolist())):
        kept = np.flatnonzero((split_of == split) & (order >= 0) & ~saturated)
        new[kept[np.argsort(order[kept], kind="stable")]] = np.arange(len(kept))

    return new


def write_object(array: ak.Array, out_dir: Path, obj: str) -> Path:
    """Write one merged object the way a conversion writes it, in a single shard."""
    path = out_dir / obj / "00000.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    ak.to_parquet(array, path, compression="snappy")

    return path


def overlay_dataset(
    raw_dir: Path,
    tree: Path,
    runs: tuple[str, ...],
    split_of: np.ndarray,
    out_dir: Path,
    seed: int,
) -> np.ndarray:
    """Overlay every object of one data set into a converted-style directory.

    :returns: The overlaid ET.Et per raw row, which is what decides the rows the split
        map now drops.
    """
    _refuse_existing(out_dir)
    pools = pool_sizes(tree, runs, sorted(set(split_of.tolist())))
    partner = draw_partners(split_of, pools, seed)
    for obj in export.raw_objects(raw_dir):
        zb = partners_in_raw_order(tree, runs, split_of, partner, obj)
        write_object(merge(obj, read_raw(raw_dir, obj), zb), out_dir, obj)

    # Read back rather than kept from the loop, so the saturation the map is
    # re-ranked against is the one the written file holds.
    return _flat(read_raw(out_dir, "ET"), "Et")


def write_split_map(path: Path, order: np.ndarray) -> None:
    """Rewrite a frozen map with a new row order, in the encoding it was read from."""
    with np.load(path, allow_pickle=False) as data:
        names, split = data["names"], data["split"]

    np.savez_compressed(path, split=split, order=order, names=names)


def update_index(path: Path, name: str, raw_dir: Path) -> str:
    """Point one data set's index entry at another converted directory.

    :returns: The event fingerprint of that directory, as now recorded in the index.
    """
    index = json.loads(path.read_text())
    fingerprint = export.event_fingerprint(raw_dir)
    index[name]["raw_dir"] = str(raw_dir)
    index[name]["fingerprint"] = fingerprint
    path.write_text(json.dumps(index, indent=2) + "\n")

    return fingerprint


def update_summary(path: Path, name: str, passing: int, overlay: dict) -> None:
    """Record an overlay in the frozen summary, with the events it leaves behind.

    The sorted keys and indent are summary.write_json's format, spelled out here because
    importing that module reaches matplotlib through the figures it also writes.
    """
    summary = json.loads(path.read_text())
    summary["datasets"][name]["events_passing_filter"] = passing
    summary.setdefault("overlay", {})[name] = overlay
    path.write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n")


def run(
    raw_dir: Path,
    tree: Path,
    out_dir: Path,
    name: str,
    runs: tuple[str, ...],
    seed: int,
    splitmap: Path,
    summary_path: Path,
) -> dict:
    """Overlay one data set and update the three frozen files that describe it.

    :returns: Rows per split, rows the map dropped before and after the overlay, and the
        fingerprint of the overlaid data set.
    """
    index = json.loads((splitmap / "index.json").read_text())
    summary = json.loads(summary_path.read_text())
    expected = summary["datasets"][name]["raw_events"]
    known = _raw_fingerprint(index, summary, name, raw_dir)
    export.check_dataset(name, raw_dir, expected, known)

    map_path = splitmap / f"{index[name]['category']}__{name}.npz"
    split_of, order = export.read_split_map(map_path)
    et = overlay_dataset(raw_dir, tree, runs, split_of, out_dir, seed)
    new_order = reranked_order(order, split_of, et == FULL)
    write_split_map(map_path, new_order)

    fingerprint = update_index(splitmap / "index.json", name, out_dir)
    record = _overlay_record(raw_dir, tree, runs, seed)
    update_summary(summary_path, name, int((new_order >= 0).sum()), record)

    return _report(split_of, order, new_order, fingerprint)


def _flat(array: ak.Array, field: str) -> np.ndarray:
    """One field of a one-object-per-event collection, as a flat numpy array."""
    return ak.to_numpy(array[field][:, 0])


def _singleton(values: np.ndarray) -> ak.Array:
    """Wrap one value per event in a list of its own, as the converter's layout has it.

    The counts are spelled out rather than given as the integer 1, which would build a
    regular array and write a parquet fixed_size_list where every other column of the
    release is a large_list.
    """
    return ak.unflatten(values, np.ones(len(values), dtype=np.int64))


def _seed(sig: ak.Array, zb: ak.Array, name: str) -> np.ndarray:
    """One algorithm's decision, OR-ed with the partner's where both menus hold it."""
    decision = _flat(sig, name)

    return decision | _flat(zb, name) if name in zb.fields else decision


def _components(et: np.ndarray, phi: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Cartesian components, in Et units, of a sum stored as an Et and a phi code."""
    angle = phi.astype(np.float64) * schema.CALO_PHI_STEP

    return et * np.cos(angle), et * np.sin(angle)


def _concat(tables: list[pa.Table]) -> pa.Table:
    """Concatenate tables holding the same columns, which may be ordered differently."""
    names = tables[0].schema.names

    return pa.concat_tables([table.select(names) for table in tables])


def _refuse_existing(out_dir: Path) -> None:
    """Refuse a directory an earlier overlay wrote, as the converter refuses one."""
    if any(out_dir.glob("*/*.parquet")):
        raise FileExistsError(f"{out_dir} already holds converted parquet.")


def _raw_fingerprint(
    index: dict, summary: dict, name: str, raw_dir: Path
) -> str | None:
    """The fingerprint recorded for a converted data set, from wherever it now sits.

    Once the index points at an overlaid directory it no longer describes the raw
    sample, so a rerun reads the raw fingerprint the overlay block kept and checks that.
    """
    if index[name]["raw_dir"] == str(raw_dir):
        return index[name].get("fingerprint")

    return summary.get("overlay", {}).get(name, {}).get("raw_fingerprint")


def _overlay_record(
    raw_dir: Path, tree: Path, runs: tuple[str, ...], seed: int
) -> dict:
    """What the summary keeps about how an overlaid data set was made."""
    return {
        "source": "zerobias",
        "runs": list(runs),
        "tree": tree.name,
        "seed": seed,
        "raw_dir": str(raw_dir),
        "raw_fingerprint": export.event_fingerprint(raw_dir),
    }


def _report(
    split_of: np.ndarray, order: np.ndarray, new: np.ndarray, fingerprint: str
) -> dict:
    """What the overlay did, for the script that ran it to print."""
    return {
        "rows": {s: int((split_of == s).sum()) for s in sorted(set(split_of.tolist()))},
        "dropped_before": int((order < 0).sum()),
        "dropped_after": int((new < 0).sum()),
        "fingerprint": fingerprint,
    }
