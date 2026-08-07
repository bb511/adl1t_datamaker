"""Shared machinery for the per-experiment conversion tests.

Each experiment gets its own test module; they all drive the same three steps from
here so that the individual tests stay down to the facts specific to their config.
"""

from pathlib import Path

from adl1t_datamaker import root2parquet
from adl1t_datamaker.loader import Parquet2Awkward

# Folders Root2Parquet writes for every conversion, in _store_objects order.
BASE_OBJECTS = [
    "seeds", "event_info", "muons", "jets", "egammas", "taus",
    "ET", "HT", "MET", "MHT", "FET", "FHT",
]
CICADA_OBJECT = "cica"

# scripts/configs/converter/default.yaml -- emulated trees, CICADA available.
EMULATED = {
    "l1_tree_name": "l1UpgradeEmuTree/L1UpgradeTree",
    "uGT_tree_name": "l1uGTEmuTree/L1uGTTree",
    "event_tree_name": "l1EventTree/L1EventTree",
    "calosumm_tree_name": "l1CaloSummaryEmuTree/L1CaloSummaryTree",
}
# scripts/configs/converter/unpacked.yaml -- raw trees, no calo summary, no CICADA.
UNPACKED = {
    "l1_tree_name": "l1UpgradeTree/L1UpgradeTree",
    "uGT_tree_name": "l1uGTTree/L1uGTTree",
    "event_tree_name": "l1EventTree/L1EventTree",
    "calosumm_tree_name": None,
}


def convert(input_url, out_dir, repo_root, menu, *, mc, converter):
    """Convert one ntuple and return the output folder."""
    conv = root2parquet.Root2Parquet(mc=mc, silent=True, **converter)
    conv.convert_file(
        input_file=input_url,
        prescale_file=str(repo_root / "scripts" / "L1Menus" / menu),
        pileup_folder=str(repo_root / "scripts" / "pileup_files"),
        output_path=str(out_dir),
    )
    return Path(out_dir)


def assert_layout(out_dir, input_url, *, expect_cicada):
    """Every expected object folder holds exactly one parquet named for the input."""
    stem = Path(input_url).stem
    expected = BASE_OBJECTS + ([CICADA_OBJECT] if expect_cicada else [])

    present = sorted(p.name for p in out_dir.iterdir() if p.is_dir())
    assert present == sorted(expected), f"folders {present} != expected {sorted(expected)}"

    for obj in expected:
        assert (out_dir / obj / f"{stem}.parquet").is_file(), f"{obj}/{stem}.parquet missing"

    if not expect_cicada:
        assert not (out_dir / CICADA_OBJECT).exists(), "cica written without a calo tree"


def assert_readable(out_dir, *, expect_cicada):
    """Read the conversion back and check every object carries events.

    Uses the no-argument form on purpose: select_feats=None is the documented
    read-everything mode and must keep working.
    """
    data = Parquet2Awkward(str(out_dir))
    expected = BASE_OBJECTS + ([CICADA_OBJECT] if expect_cicada else [])
    assert sorted(data.object_names) == sorted(expected)

    for obj in expected:
        assert len(data[obj]) > 0, f"{obj} read back empty"

    return data


def assert_seeds_and_events(data):
    """Seeds carry the synthetic L1bit, and event_info carries the documented fields.

    Awkward propagates .fields through the list layers that ak.singletons adds, so
    this reads the record fields regardless of the singleton wrapping.
    """
    assert "L1bit" in data["seeds"].fields, "seeds is missing the combined L1bit"

    fields = data["event_info"].fields
    missing = {"run", "lumi", "event", "bx", "orbit", "nPV_True"} - set(fields)
    assert not missing, f"event_info is missing {missing}"


def assert_pileup_present(data):
    """Real data must come out with a genuine pileup value, not the 0 fallback.

    lookup_pileup defaults to 0 for any (run, lumi) it cannot find, so an all-zero
    column is how a broken run to brilcalc-file mapping shows up.
    """
    import awkward as ak

    pileup = ak.flatten(data["event_info"]["nPV_True"], axis=None)
    assert ak.max(pileup) > 0, "every event got pileup 0; run/lumi lookup failed"
