"""Shared machinery for the per-experiment conversion tests.

Each experiment gets its own test module, and they all drive the same conversion and
the same checks from here, so a module stays down to what is specific to it: the input
file, the menu, the tree names and whether the sample is simulated.
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

# scripts/configs/converter/default.yaml: emulated trees, so CICADA is available.
EMULATED = {
    "l1_tree_name": "l1UpgradeEmuTree/L1UpgradeTree",
    "uGT_tree_name": "l1uGTEmuTree/L1uGTTree",
    "event_tree_name": "l1EventTree/L1EventTree",
    "calosumm_tree_name": "l1CaloSummaryEmuTree/L1CaloSummaryTree",
}
# scripts/configs/converter/unpacked.yaml: raw trees, no calo summary and so no CICADA.
UNPACKED = {
    "l1_tree_name": "l1UpgradeTree/L1UpgradeTree",
    "uGT_tree_name": "l1uGTTree/L1uGTTree",
    "event_tree_name": "l1EventTree/L1EventTree",
    "calosumm_tree_name": None,
}


def convert(input_url, out_dir, repo_root, menu, *, mc, converter):
    """Convert one ntuple and return the folder it was written to.

    :param input_url: Local path or ``root://`` URL of a single L1TNtuple.
    :param out_dir: Gains one subfolder per object, each holding a parquet named after
        the stem of the input.
    :param repo_root: Checkout root, under which the menus and the brilcalc files are
        looked up.
    :param menu: File name of a prescale menu inside ``scripts/L1Menus``.
    :param mc: True for simulation, which leaves the brilcalc pileup lookup unused and
        keeps ``nPV_True`` as the tree wrote it.
    :param converter: Tree names to build the converter with, EMULATED or UNPACKED.
    """
    conv = root2parquet.Root2Parquet(mc=mc, silent=True, **converter)
    conv.convert_file(
        input_file=input_url,
        prescale_file=str(repo_root / "scripts" / "L1Menus" / menu),
        pileup_folder=str(repo_root / "scripts" / "pileup_files"),
        output_path=str(out_dir),
    )
    return Path(out_dir)


def assert_layout(out_dir, input_url, *, expect_cicada):
    """The expected object folders exist, each holding a parquet named for the input.

    :param input_url: Only its stem is used, that being what the converter names its
        output after.
    :param expect_cicada: True only for a converter given a calo summary tree, which is
        the only place the CICADA score lives.
    """
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

    :returns: The loader, so the caller can go on inspecting the arrays.
    """
    data = Parquet2Awkward(str(out_dir))
    expected = BASE_OBJECTS + ([CICADA_OBJECT] if expect_cicada else [])
    assert sorted(data.object_names) == sorted(expected)

    for obj in expected:
        assert len(data[obj]) > 0, f"{obj} read back empty"

    return data


def assert_seeds_and_events(data):
    """Seeds carry the computed L1bit, and event_info carries the documented fields.

    L1bit is the OR over the unprescaled seeds, so it exists in no tree and can only
    come out of the conversion. Awkward propagates .fields through the list layer that
    ak.singletons adds, so the record fields read the same either way.
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
