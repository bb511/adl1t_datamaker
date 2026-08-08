"""The two pure halves of the publish tooling, which an export cannot check cheaply.

Everything else about a release costs hours and a converted data set to exercise. The
row ordering and the card are pure functions over small inputs, and they are also where
a silent mistake is most expensive: a wrong ordering scrambles a published split, and a
wrong card is a wrong number in a citable record.
"""

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from adl1t_datamaker import schema
from adl1t_datamaker.publish import card
from adl1t_datamaker.publish import export
from adl1t_datamaker.publish.assets import adl1t_l1ad

REPO_ROOT = Path(__file__).resolve().parent.parent


def flat(text: str) -> str:
    """The card with its line breaks collapsed, so a claim can be sought as one string.

    Prose is reflowed after the numbers are substituted, so where a phrase breaks
    depends on the counts around it and is no business of a test.
    """
    return " ".join(text.split())


@pytest.fixture
def summary():
    """One zero-bias run and one signal sample, with the keys the card reads."""
    return {
        "split_seed": 42,
        "dataset_version": "adl1t-l1ad-v1",
        "datasets": {
            "ZB_run396102": {
                "category": "zerobias",
                "raw_events": 1000,
                "events_passing_filter": 990,
                "counts": {"train": 600, "valid": 200, "test": 200},
            },
            "haa-4b-ma15": {
                "category": "signal",
                "raw_events": 100,
                "events_passing_filter": 100,
                "counts": {"valid": 60, "test": 40},
            },
        },
    }


def test_seen_rows_come_back_in_the_studys_order():
    """`order` is a position within the split, not a raw row number."""
    split_of = np.array(["train", "train", "valid", "train"])
    order = np.array([2, 0, 0, 1])

    assert export.split_row_order(split_of, order, "train").tolist() == [1, 3, 0]


def test_cut_rows_are_appended_in_raw_order():
    """The study never permuted them, so they follow the rows it did see."""
    split_of = np.array(["train"] * 5)
    order = np.array([1, -1, 0, -1, 2])

    assert export.split_row_order(split_of, order, "train").tolist() == [2, 0, 4, 1, 3]


def test_every_row_of_a_split_is_placed_exactly_once():
    rng = np.random.default_rng(0)
    split_of = rng.choice(["train", "valid"], 200)
    order = np.where(rng.random(200) < 0.1, -1, rng.permutation(200))

    rows = np.concatenate([export.split_row_order(split_of, order, s) for s in ("train", "valid")])

    assert sorted(rows.tolist()) == list(range(200))


def test_a_coded_split_map_reads_back_as_names(tmp_path):
    """The compact encoding stores int8 indices into a codebook, not the names."""
    path = tmp_path / "zerobias__run.npz"
    np.savez(
        path, split=np.array([0, 1, 0], dtype=np.int8), order=np.array([0, 0, 1]),
        names=np.array(["train", "valid"]),
    )

    split_of, order = export.read_split_map(path)

    assert split_of.tolist() == ["train", "valid", "train"]
    assert order.tolist() == [0, 0, 1]


def test_a_plain_split_map_still_reads(tmp_path):
    """Maps frozen before the codebook existed have to keep working."""
    path = tmp_path / "zerobias__run.npz"
    np.savez(path, split=np.array(["train", "valid"], dtype="U5"), order=np.array([0, 0]))

    split_of, _ = export.read_split_map(path)

    assert split_of.tolist() == ["train", "valid"]


def test_the_tar_command_fixes_everything_that_would_vary(tmp_path):
    """Owner, timestamp and member order are what stop two packs matching."""
    command = export.tar_cmd(tmp_path, ["train"], tmp_path / "train.tar")

    for flag in ("--sort=name", "--owner=0", "--group=0", f"--mtime={export.SOURCE_DATE}"):
        assert flag in command, flag
    assert str(tmp_path) in command


def test_the_summary_directory_is_not_published(tmp_path):
    """Every converted data set now carries one, and it describes the data rather than
    being data."""
    for name in ("jets", "SUMMARY", "cica", "PLOTS"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "00000.parquet").touch()

    assert export.raw_objects(tmp_path) == ["jets"]


def test_the_card_quotes_the_documented_calorimeter_eta_step(summary):
    """Version 1 of the card carried 0.5 here, which puts a jet at |eta| = 57."""
    text = card.render(summary)

    assert f"| jets | 0.5 GeV | {schema.CALO_ETA_STEP:.6g} |" in text
    assert "0.0435" in text


def test_the_card_separates_the_hardware_limit_from_the_studys_threshold(summary):
    """511 saturates a 9-bit muon Et, and does not saturate an 11-bit jet Et."""
    text = card.render(summary)

    assert "9 bits wide" in flat(text)
    assert "11 bits wide and saturates at 2047" in flat(text)


def test_the_card_states_the_counts_it_pads_to_and_the_ones_it_holds(summary):
    """Two different sets of per-object counts, and confusing them is easy."""
    text = card.render(summary)

    assert "Keep 4 muons, 10 jets" in flat(text), "the study's padding"
    assert "capacity of 8 muons, 12 jets" in flat(text), "what the files hold"


def test_the_card_points_at_no_code_the_record_does_not_contain(summary):
    text = card.render(summary)

    for absent in ("adl1t_l1ad", "read_splits", "fit_norm_params", "to_model_tensor"):
        assert absent not in text, absent


def test_the_card_layout_matches_the_archives(summary):
    """The archives unpack straight to zerobias/, so a wrapper path would not resolve."""
    text = card.render(summary)

    assert "zerobias/<run>/{train,valid,test}/<object>/*.parquet" in text
    assert "adl1t-l1ad-v1" not in text


def test_the_card_carries_no_dashes_that_should_be_punctuation(summary):
    """An em dash or a `--` stand-in is a house-style defect in a published document."""
    prose = [
        line for line in card.render(summary).splitlines()
        if not line.startswith(("|", "```"))
    ]

    assert not [line for line in prose if "—" in line or "--" in line]


def test_the_card_renders_the_same_bytes_twice(summary):
    """Nothing in it may depend on a clock, a hash seed or a set ordering."""
    assert card.render(summary) == card.render(summary)


def test_the_card_and_the_shipped_reader_agree_on_the_cuts(summary):
    """The card documents the thresholds the reader applies, so they cannot drift."""
    text = card.render(summary)

    assert f"`ET.Et < {adl1t_l1ad.EVENT_CUT[2]}`" in flat(text)
    assert f"`Et < {adl1t_l1ad.OBJECT_CUTS['muons']}`" in flat(text)


def test_packing_alone_needs_no_split_map(tmp_path):
    """Repacking after a failed archive must not demand the inputs that built the tree.

    The point of running one stage is to redo it cheaply. Reading index.json and the
    split summary up front made `--stage pack` fail on a release folder whose metadata
    had moved, which is exactly when a repack is wanted.
    """
    tree = tmp_path / "work" / "adl1t-l1ad-v2"
    (tree / "zerobias" / "run" / "train" / "ET").mkdir(parents=True)
    (tree / "zerobias" / "run" / "train" / "ET" / "00000.parquet").write_bytes(b"x")

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "publish" / "publish"),
         "--out", str(tmp_path / "release"), "--work", str(tmp_path / "work"),
         "--stage", "pack"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "release" / "train.tar").is_file()
    assert (tmp_path / "release" / "sha256sums.txt").is_file()


def test_the_publish_script_starts():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "publish" / "publish"), "--help"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )

    assert result.returncode == 0, result.stderr
    assert "usage" in result.stdout.lower()


def test_the_hf_exporter_starts():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "publish" / "export_hf"), "--help"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )

    assert result.returncode == 0, result.stderr
    assert "usage" in result.stdout.lower()
