"""The pile-up overlay: its merge rules, the files it writes and the map it re-ranks.

The fixtures are shaped like the real thing rather than sized like it. Five simulated
events meet a pool of five recorded events per split, row 0 overflows both the jet and
the muon capacity, row 3 already sits on the saturation code, and row 2 is pushed onto
it by its partner, which is the case the re-ranked map exists for.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import awkward as ak
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from adl1t_datamaker.publish import export, huggingface, overlay

RUNS = ("ZB_a", "ZB_b")

# The all-ones codes a conversion writes where the ntuple carries no value.
BX_NONE = int(np.iinfo(np.uint32).max)
ORBIT_NONE = int(np.iinfo(np.uint64).max)

SIG_EVENTS = [1, 2, 3, 4, 5]

# Row 3 is saturated before the overlay, row 2 is pushed there by the partner's 2000.
SIG_ET = [100, 200, 3000, 4095, 300]

# Row 0 fills eleven of the twelve jet slots and seven of the eight muon ones, so the
# partner's objects have to displace some of them.
SIG_JETS = [[90, 82, 74, 66, 58, 52, 44, 36, 28, 18, 10], [40, 20], [], [30], [15]]
SIG_MUONS = [[70, 60, 50, 45, 35, 25, 15], [5], [], [], []]

# L1_sim_only is in the simulated menu alone. L1_shared is in both menus and fires in no
# simulated event, so an OR-ed decision on it can only have come from the partner.
SIG_SEEDS = {
    "L1_shared": [False, False, False, False, False],
    "L1_sim_only": [True, False, False, False, True],
    "L1bit": [True, False, False, False, True],
}

# Distinct per split, so a merged event_info row names the pool it was drawn from.
ZB_EVENTS = {
    "valid": [1000, 1001, 1002, 1003, 1004],
    "test": [2000, 2001, 2002, 2003, 2004],
}

SUMMARY = {
    "split_seed": 42,
    "datasets": {
        "haa": {
            "category": "signal",
            "counts": {"test": 1, "valid": 4},
            "events_passing_filter": 4,
            "objects": [
                "ET",
                "FET",
                "FHT",
                "HT",
                "MET",
                "MHT",
                "egammas",
                "event_info",
                "jets",
                "muons",
                "seeds",
                "taus",
            ],
            "raw_events": 5,
        }
    },
}


def i16(rows: list[list[int]]) -> ak.Array:
    """A jagged collection column, in the width the record stores it at."""
    return ak.values_astype(ak.Array(rows), np.int16)


def u16(rows: list[list[int]]) -> ak.Array:
    return ak.values_astype(ak.Array(rows), np.uint16)


def one(dtype: type, values: list | np.ndarray) -> ak.Array:
    """One value per event, as the length-1 lists every converted column is.

    The lists are variable length, which is what the converter's ak.singletons makes of
    them and what every file of the release holds. ak.unflatten(values, 1) would write
    fixed-size lists instead, a different arrow type for the same numbers.
    """
    return ak.singletons(ak.Array(np.asarray(values, dtype)))


def _like(rows: list[list[int]], value: int) -> list[list[int]]:
    """A column of the same jaggedness holding one value throughout."""
    return [[value] * len(row) for row in rows]


def jets(et: list[list[int]], raw_et: int) -> ak.Array:
    """Jets carrying the given Et pattern; the other branches only have to be there.

    raw_et labels where a jet came from, so a merged collection can be traced back.
    """
    return ak.Array(
        {
            "jetIEt": i16(et),
            "jetIEta": i16(_like(et, 5)),
            "jetIPhi": i16(_like(et, 10)),
            "jetHwQual": i16(_like(et, 0)),
            "jetRawEt": i16(_like(et, raw_et)),
        }
    )


def egammas(et: list[list[int]]) -> ak.Array:
    return ak.Array(
        {
            "egIEt": i16(et),
            "egIEta": i16(_like(et, 5)),
            "egIPhi": i16(_like(et, 10)),
            "egIso": i16(_like(et, 1)),
        }
    )


def taus(et: list[list[int]]) -> ak.Array:
    return ak.Array(
        {
            "tauIEt": i16(et),
            "tauIEta": i16(_like(et, 5)),
            "tauIPhi": i16(_like(et, 10)),
            "tauIso": i16(_like(et, 1)),
        }
    )


def muons(et: list[list[int]]) -> ak.Array:
    """Muons, the two unsigned branches included."""
    return ak.Array(
        {
            "muonIPhiAtVtx": i16(_like(et, 40)),
            "muonIEt": i16(et),
            "muonIEtaAtVtx": i16(_like(et, 8)),
            "muonChg": i16(_like(et, 1)),
            "muonIPhi": i16(_like(et, 40)),
            "muonIEta": i16(_like(et, 8)),
            "muonIEtUnconstrained": i16(_like(et, 0)),
            "muonQual": u16(_like(et, 12)),
            "muonTfMuonIdx": u16(_like(et, 3)),
        }
    )


def pair(first: list[int], second: list[int], names: tuple[str, str]) -> ak.Array:
    """An energy sum, which is two one-per-event columns."""
    return ak.Array({names[0]: one(np.int16, first), names[1]: one(np.int16, second)})


def seeds(columns: dict[str, list[bool]]) -> ak.Array:
    return ak.Array({name: one(np.bool_, values) for name, values in columns.items()})


def event_info(
    events: list[int], run: int, npv: np.ndarray, extra: dict | None = None
) -> ak.Array:
    """The seven per-event columns, plus the flat pair the release tree adds."""
    fields = _event_columns(events, run)
    fields["nPV_True"] = one(npv.dtype, npv)
    fields.update(extra or {})

    return ak.Array(fields)


def _event_columns(events: list[int], run: int) -> dict:
    rows = len(events)

    return {
        "run": one(np.uint32, [run] * rows),
        "lumi": one(np.uint32, [1] * rows),
        "event": one(np.uint64, events),
        "bx": one(np.uint32, [BX_NONE] * rows),
        "orbit": one(np.uint64, [ORBIT_NONE] * rows),
        "time": one(np.uint64, [7] * rows),
    }


def _write(array: ak.Array, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ak.to_parquet(array, path, compression="snappy")


def _raw_sums() -> dict[str, ak.Array]:
    """The six energy sums of the simulated sample."""
    return {
        "ET": pair(SIG_ET, [50, 60, 70, 80, 90], ("Et", "ETTEM")),
        "HT": pair(
            [10, 20, 30, 40, 50], [100, 200, 300, 400, 500], ("Et", "tower_count")
        ),
        "MET": pair([0, 100, 200, 300, 400], [0, 0, 36, 72, 108], ("Et", "phi")),
        "MHT": pair([10, 110, 210, 310, 410], [0, 18, 36, 54, 72], ("Et", "phi")),
        "FET": pair([20, 120, 220, 320, 420], [0, 0, 0, 0, 0], ("Et", "phi")),
        "FHT": pair([30, 130, 230, 330, 430], [12, 24, 36, 48, 60], ("Et", "phi")),
    }


def _raw_collections() -> dict[str, ak.Array]:
    return {
        "jets": jets(SIG_JETS, raw_et=9),
        "muons": muons(SIG_MUONS),
        "egammas": egammas([[20], [], [], [], []]),
        "taus": taus([[15, 5], [], [], [], []]),
    }


def raw_arrays() -> dict[str, ak.Array]:
    """The twelve objects a conversion writes, five events each."""
    arrays = {**_raw_sums(), **_raw_collections()}
    arrays["event_info"] = event_info(SIG_EVENTS, 1, np.zeros(5, np.int32))
    arrays["seeds"] = seeds(SIG_SEEDS)

    return arrays


def write_raw(raw: Path) -> None:
    """The converted simulation, its jets split over two shards as a real one is."""
    arrays = raw_arrays()
    shards = arrays.pop("jets")
    for obj, array in arrays.items():
        _write(array, raw / obj / "00000.parquet")

    _write(shards[:3], raw / "jets" / "00000.parquet")
    _write(shards[3:], raw / "jets" / "00001.parquet")


def _pool_sums(rows: int) -> dict[str, ak.Array]:
    """Every partner carries the same sums, MET opposite the signal's row 1."""
    return {
        "ET": pair([2000] * rows, [500] * rows, ("Et", "ETTEM")),
        "HT": pair([1000] * rows, [8000] * rows, ("Et", "tower_count")),
        "MET": pair([100] * rows, [72] * rows, ("Et", "phi")),
        "MHT": pair([200] * rows, [36] * rows, ("Et", "phi")),
        "FET": pair([300] * rows, [0] * rows, ("Et", "phi")),
        "FHT": pair([400] * rows, [108] * rows, ("Et", "phi")),
    }


def _pool_collections(rows: int) -> dict[str, ak.Array]:
    """The partner's muons arrive out of Et order, as a recorded event's do."""
    return {
        "jets": jets([[95, 50, 5]] * rows, raw_et=0),
        "muons": muons([[10, 40, 20]] * rows),
        "egammas": egammas([[30]] * rows),
        "taus": taus([[25]] * rows),
    }


def _pool_seeds(split: str, rows: int) -> dict[str, list[bool]]:
    """L1_shared fires throughout the valid pool and nowhere in the test one."""
    return {
        "L1_shared": [split == "valid"] * rows,
        "L1_zb_only": [True] * rows,
        "L1bit": [True] * rows,
    }


def _write_pool(
    split_dir: Path, events: list[int], run: int, split: str, start: int
) -> None:
    """One run's share of one split's pool, partners identical bar the event number."""
    rows = len(events)
    # The two flat columns the export writes beside the per-event ones.
    order = np.arange(start, start + rows, dtype=np.int64)
    extra = {"split": [split] * rows, "order": order}
    arrays = {**_pool_sums(rows), **_pool_collections(rows)}
    npv = np.full(rows, 60.0, np.float32)
    arrays["event_info"] = event_info(events, run, npv, extra)
    arrays["seeds"] = seeds(_pool_seeds(split, rows))
    for obj, array in arrays.items():
        _write(array, split_dir / obj / "00000.parquet")


def write_tree(tree: Path) -> None:
    """The release tree's zero-bias half: two runs, each holding part of every pool."""
    for split, events in ZB_EVENTS.items():
        _write_pool(tree / "zerobias" / "ZB_a" / split, events[:2], 396102, split, 0)
        _write_pool(tree / "zerobias" / "ZB_b" / split, events[2:], 398183, split, 2)


def write_splitmap(splitmap: Path, raw: Path) -> None:
    """The frozen map: four valid rows, one test row, one of them already dropped."""
    splitmap.mkdir(parents=True)
    entry = {
        "category": "signal",
        "raw_dir": str(raw),
        "fingerprint": export.event_fingerprint(raw),
    }
    (splitmap / "index.json").write_text(json.dumps({"haa": entry}, indent=2) + "\n")
    np.savez_compressed(
        splitmap / "signal__haa.npz",
        names=np.array(["test", "valid"]),
        split=np.array([1, 0, 1, 1, 1], np.int8),
        order=np.array([0, 0, 2, -1, 1], np.int64),
    )


@pytest.fixture
def env(tmp_path) -> SimpleNamespace:
    """A converted sample, a zero-bias tree and the frozen files describing them."""
    paths = SimpleNamespace(
        raw=tmp_path / "raw",
        tree=tmp_path / "tree",
        splitmap=tmp_path / "splitmap",
        summary=tmp_path / "split_summary.json",
        out=tmp_path / "overlaid",
    )
    write_raw(paths.raw)
    write_tree(paths.tree)
    write_splitmap(paths.splitmap, paths.raw)
    paths.summary.write_text(json.dumps(SUMMARY, sort_keys=True, indent=2) + "\n")

    return paths


@pytest.fixture
def overlaid(env) -> dict:
    """One overlay of the whole fixture, as the script runs it."""
    return overlay.run(
        env.raw, env.tree, env.out, "haa", RUNS, 42, env.splitmap, env.summary
    )


def read_object(out: Path, obj: str) -> ak.Array:
    """One overlaid object, read back the way the release reads it."""
    return ak.from_parquet(out / obj / "00000.parquet")


def flat(array: ak.Array, field: str) -> np.ndarray:
    """One value per event, out of the length-1 lists the column stores."""
    return np.asarray(ak.to_numpy(array[field][:, 0]))



def test_collections_are_merged_hardest_first_and_clipped(env, overlaid):
    """Row 0 overflows both collections, so the merge sorts and then clips."""
    merged_jets = ak.to_list(read_object(env.out, "jets")["jetIEt"][0])
    merged_muons = ak.to_list(read_object(env.out, "muons")["muonIEt"][0])
    tied = overlay.merge_collection(
        jets([[50]], raw_et=9), jets([[50]], raw_et=0), "jetIEt", 12
    )

    # The signal's eleven jets and the partner's three, hardest first, the softest two
    # (the signal's 10 and the partner's 5) beyond the twelve slots and gone.
    assert merged_jets == [95, 90, 82, 74, 66, 58, 52, 50, 44, 36, 28, 18]
    assert merged_muons == [70, 60, 50, 45, 40, 35, 25, 20]
    # Equal Et: the stable sort leaves the simulated jet in front.
    assert ak.to_list(tied["jetRawEt"][0]) == [9, 0]


def _summed(et_a: int, phi_a: int, et_b: int, phi_b: int) -> tuple[int, int]:
    """One pair of missing-energy sums added, as hardware codes."""
    et, phi = overlay.vector_sum(
        np.array([et_a], np.int16),
        np.array([phi_a], np.int16),
        np.array([et_b], np.int16),
        np.array([phi_b], np.int16),
    )
    assert et.dtype == np.int16 and phi.dtype == np.int16

    return int(et[0]), int(phi[0])


def test_sums_add_and_saturate(env, overlaid):
    """Scalars clip at their all-ones code, vectors add as vectors and wrap in phi."""
    total = flat(read_object(env.out, "ET"), "Et")
    met = read_object(env.out, "MET")
    counted = overlay.merge_scalars(
        pair([1000], [8000], ("Et", "tower_count")),
        pair([1000], [8000], ("Et", "tower_count")),
        overlay.SCALARS["HT"],
    )

    # Row 2 is tipped over the twelve-bit ceiling by its partner, row 3 was there.
    assert list(total) == [2100, 2200, 4095, 4095, 2300]
    assert total.dtype == np.int16
    assert flat(counted, "tower_count")[0] == 8191  # the thirteen-bit ceiling
    assert _summed(100, 0, 100, 72) == (0, 0)  # back to back
    assert _summed(100, 10, 50, 10) == (150, 10)  # aligned
    assert _summed(100, 143, 100, 1) == (200, 0)  # phi wraps at 144
    assert _summed(4095, 0, 10, 72) == (4095, 0)  # saturated stays saturated
    # Row 1's MET and every partner's are equal and opposite.
    assert (flat(met, "Et")[1], flat(met, "phi")[1]) == (0, 0)


def test_seeds_and_event_info_come_from_both_menus_and_the_partner(env, overlaid):
    """Shared seeds are OR-ed, the partner adds none, and its coordinates are kept."""
    merged = read_object(env.out, "seeds")
    info = read_object(env.out, "event_info")
    events = flat(info, "event")
    npv = flat(info, "nPV_True")

    assert merged.fields == ["L1_shared", "L1_sim_only", "L1bit"]
    # Rows 0, 2, 3 and 4 are valid, so their partner fired L1_shared and they did not.
    assert list(flat(merged, "L1_shared")) == [True, False, True, True, True]
    assert list(flat(merged, "L1_sim_only")) == [True, False, False, False, True]
    assert list(flat(merged, "L1bit")) == [True, False, True, True, True]
    assert info.fields == list(overlay.EVENT_FIELDS)
    assert set(events[[0, 2, 3, 4]]) <= set(ZB_EVENTS["valid"])
    assert len(set(events[[0, 2, 3, 4]])) == 4  # drawn without replacement
    assert events[1] in ZB_EVENTS["test"]
    assert set(flat(info, "run")) <= {396102, 398183}
    assert npv.dtype == np.float32 and (npv == 60.0).all()


def test_partners_are_drawn_once_and_reproducibly():
    """The seed is what makes an overlay repeatable, and no partner is used twice."""
    split_of = np.array(["valid"] * 30 + ["test"] * 20)
    pools = {"valid": 50, "test": 50}
    drawn = overlay.draw_partners(split_of, pools, 42)

    assert (drawn == overlay.draw_partners(split_of, pools, 42)).all()
    assert (drawn != overlay.draw_partners(split_of, pools, 7)).any()
    assert drawn.min() >= 0 and drawn.max() < 50
    assert len(set(drawn[:30].tolist())) == 30
    assert len(set(drawn[30:].tolist())) == 20


def _types(schema: pa.Schema) -> dict[str, pa.DataType]:
    """Column types, without the two flat columns only the release tree carries."""
    return {
        name: schema.field(name).type
        for name in schema.names
        if name not in ("split", "order")
    }


def _source_schema(env: SimpleNamespace, obj: str) -> pa.Schema:
    """Where an overlaid object's types have to come from."""
    if obj == "event_info":
        pool = env.tree / "zerobias" / "ZB_a" / "valid" / "event_info"
        return pq.read_schema(pool / "00000.parquet")

    return pq.read_schema(sorted((env.raw / obj).glob("*.parquet"))[0])


def test_run_rewrites_the_map_and_the_registry(env, overlaid, tmp_path):
    """Row 2 leaves the order, the index moves, the summary keeps the raw sample."""
    split_of, order = export.read_split_map(env.splitmap / "signal__haa.npz")
    entry = json.loads((env.splitmap / "index.json").read_text())["haa"]
    summary = json.loads(env.summary.read_text())

    assert list(split_of) == ["valid", "test", "valid", "valid", "valid"]
    assert list(order) == [0, 0, -1, -1, 1]
    assert (overlaid["dropped_before"], overlaid["dropped_after"]) == (1, 2)
    assert summary["datasets"]["haa"]["events_passing_filter"] == 3
    assert summary["datasets"]["haa"]["counts"] == {"test": 1, "valid": 4}
    assert entry == {
        "category": "signal",
        "raw_dir": str(env.out),
        "fingerprint": export.event_fingerprint(env.out),
    }
    assert entry["fingerprint"] == overlaid["fingerprint"]
    assert summary["overlay"]["haa"] == {
        "source": "zerobias",
        "runs": ["ZB_a", "ZB_b"],
        "tree": env.tree.name,
        "seed": 42,
        "raw_dir": str(env.raw),
        "raw_fingerprint": export.event_fingerprint(env.raw),
    }
    # No column may widen: event_info follows the partner, everything else the raw.
    for obj in export.raw_objects(env.raw):
        written = pq.read_schema(env.out / obj / "00000.parquet")
        assert _types(written) == _types(_source_schema(env, obj)), obj

    # A conversion is never written twice, and a rerun checks the raw sample against
    # the fingerprint the summary kept once the index no longer names it.
    args = (env.raw, env.tree, env.out, "haa", RUNS, 42, env.splitmap, env.summary)
    with pytest.raises(FileExistsError):
        overlay.run(*args)
    summary["overlay"]["haa"]["raw_fingerprint"] = "0" * 64
    env.summary.write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n")
    with pytest.raises(ValueError, match="event order"):
        overlay.run(*args[:2], tmp_path / "again", *args[3:])


def test_written_from_reads_a_mirror_back(tmp_path):
    """A partial rebuild keeps the configs it did not touch, read off the shards."""
    data = tmp_path / "data" / "a"
    (data / "seeds").mkdir(parents=True)
    for name in ("valid-00000-of-00001.parquet", "test-00000-of-00001.parquet"):
        (data / name).touch()
    (data / "seeds" / "valid-00000-of-00001.parquet").touch()

    assert huggingface.written_from(tmp_path) == {
        "a": {"valid": "data/a/valid-*.parquet", "test": "data/a/test-*.parquet"},
        "a-seeds": {"valid": "data/a/seeds/valid-*.parquet"},
    }
