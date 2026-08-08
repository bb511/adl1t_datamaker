"""Summarising a folder end to end against a synthetic conversion. No ROOT, no EOS.

The synthetic tree copies the shapes the converter writes, including the irregular one:
cica is stored flat, without ak.singletons, so code that assumes every object is jagged
raises on it. The old scripts/plot called ak.num(..., axis=1) on every object and did
exactly that.
"""

import json

import awkward as ak
import numpy as np
import pytest

from adl1t_datamaker import summary
from adl1t_datamaker.components import l1_seeds

EVENTS = 40
SHARDS = ("L1Ntuple_1", "L1Ntuple_2")
# The smallest menu in scripts/L1Menus, so the seed columns are a real unprescaled set
# at 150 columns rather than the 190 of the 2025 menus.
MENU = "Prescale_2022_v0_1_1.csv"


def jagged(rng, columns: dict) -> ak.Array:
    """Variable length entries per event, the way the particle collections arrive.

    :param columns: Column name to the ``(low, high)`` bounds its integer codes are
        drawn between, high exclusive as numpy's integers takes them.
    :returns: A record array of shape (EVENTS, 0..3 entries), every column of one call
        sharing the same per-event counts.
    """
    counts = rng.integers(0, 4, EVENTS)
    return ak.Array({
        name: ak.unflatten(rng.integers(low, high, int(counts.sum())), counts)
        for name, (low, high) in columns.items()
    })


def singletons(columns: dict) -> ak.Array:
    """One entry per event, wrapped as the converter wraps seeds and event_info.

    :param columns: Column name to a flat array of one value per event. ak.singletons
        adds the list layer, so the result has shape (EVENTS, 1).
    """
    return ak.singletons(ak.Array(columns))


def write(folder, name: str, array: ak.Array) -> None:
    """Write one object folder, the same array under each of the two shard names.

    Repeating the array is what gives the data set its duplicated event identifiers.
    """
    (folder / name).mkdir(parents=True, exist_ok=True)
    for shard in SHARDS:
        ak.to_parquet(array, folder / name / f"{shard}.parquet", compression="snappy")


@pytest.fixture
def dataset(tmp_path, menus):
    """A folder shaped like a real conversion, with every object kind represented."""
    rng = np.random.default_rng(11)
    folder = tmp_path / "SyntheticRun"
    write(folder, "muons", jagged(rng, {
        "muonIEt": (0, 60), "muonIEta": (-100, 100), "muonIPhi": (0, 576),
        "muonQual": (0, 16), "muonChg": (-1, 2),
    }))
    write(folder, "jets", jagged(rng, {
        "jetIEt": (0, 300), "jetIEta": (-60, 60), "jetIPhi": (0, 144),
    }))
    write(folder, "ET", jagged(rng, {"Et": (0, 900), "ETTEM": (0, 400)}))
    write(folder, "HT", jagged(rng, {"Et": (0, 900), "tower_count": (0, 700)}))
    # time is packed as docs/README.md specifies, Unix seconds shifted left by 32 bits;
    # 1716486000 decodes to 2024-05-23, which the wall clock test reads back.
    write(folder, "event_info", singletons({
        "run": np.full(EVENTS, 392642), "lumi": rng.integers(10, 14, EVENTS),
        "event": np.arange(EVENTS) + 1_000, "bx": rng.integers(1, 3564, EVENTS),
        "orbit": np.arange(EVENTS) * 7, "time": np.full(EVENTS, 1716486000 << 32),
        "nPV_True": rng.uniform(30, 60, EVENTS).astype(np.float32),
    }))
    write(folder, "cica", ak.Array({"CICADAScore": rng.uniform(0, 40, EVENTS)}))
    write(folder, "seeds", singletons(seed_columns(rng, menus)))

    return folder


def seed_columns(rng, menus) -> dict:
    """One boolean column per unprescaled seed of MENU, plus the synthesised L1bit.

    :param menus: The scripts/L1Menus directory, so identify_menu has a real menu to
        match the column names against.
    :returns: Per seed, a per-event mask firing on roughly 5% of events, with L1bit the
        OR of the rest as l1_seeds builds it.
    """
    names = sorted(set(l1_seeds.unprescaled_names(menus / MENU)))
    fired = {name: rng.random(EVENTS) < 0.05 for name in names}
    fired["L1bit"] = np.logical_or.reduce(list(fired.values()))

    return fired


@pytest.fixture
def measured(dataset):
    return summary.measure_folder(dataset, batch_size=16, checksums=True)


def status_of(measured: dict, check: str) -> str:
    return next(entry["status"] for entry in measured["validation"] if entry["check"] == check)


def test_every_object_is_measured(measured):
    expected = {"muons", "jets", "ET", "HT", "event_info", "cica", "seeds"}

    assert set(measured["objects"]) == expected
    assert measured["totals"]["events"] == EVENTS * len(SHARDS)
    assert measured["totals"]["cicada"] is True


def test_flat_cica_is_one_entry_per_event(measured):
    """No list layer on cica, so counts_per_event assumes one entry per event."""
    multiplicity = measured["objects"]["cica"]["multiplicity"]["stats"]

    assert (multiplicity["min"], multiplicity["max"]) == (1, 1)
    assert measured["objects"]["cica"]["features"]["CICADAScore"]["stats"]["exact"]


def test_statistics_match_the_data_they_were_taken_from(dataset, measured):
    """Check the streaming accumulator against the column read back whole.

    Everything else in the summary trusts it, so it is checked here once.
    """
    from adl1t_datamaker.loader import Parquet2Awkward

    raw = ak.to_numpy(ak.flatten(Parquet2Awkward(str(dataset))["jets"]["jetIEt"], axis=None))
    stats_ = measured["objects"]["jets"]["features"]["jetIEt"]["stats"]

    assert stats_["entries"] == raw.size
    assert stats_["mean"] == pytest.approx(raw.mean())
    assert stats_["std"] == pytest.approx(raw.std())
    assert stats_["min"] == raw.min() and stats_["max"] == raw.max()


def test_event_identifiers_are_seen_as_duplicated_across_shards(measured):
    """Both shards hold the same array, which is the duplication the check exists for."""
    assert measured["event_coverage"]["duplicate_identifiers"] == EVENTS
    assert status_of(measured, "no duplicate event identifiers") == "FAIL"


def test_wall_clock_is_decoded_from_the_packed_time_field(measured):
    assert measured["event_coverage"]["wall_clock"]["start"].startswith("2024-05-23")


def test_the_menu_is_identified_from_the_seed_columns(measured):
    trigger = measured["trigger"]

    assert trigger["menu"] == MENU
    assert trigger["menu_mismatch"] == 0
    assert status_of(measured, "seed columns match the menu") == "PASS"


def test_seed_table_is_ranked_and_complete(measured):
    seeds = measured["trigger"]["seeds"]
    fractions = [seed["fraction"] for seed in seeds]

    assert len(seeds) == measured["trigger"]["n_seeds"]
    assert fractions == sorted(fractions, reverse=True)
    assert measured["trigger"]["l1bit_accepted"] > 0


def test_occupancy_is_only_built_for_the_particle_objects(measured):
    assert measured["objects"]["muons"]["occupancy"]
    assert not measured["objects"]["ET"]["occupancy"]


def test_a_truncated_shard_fails_the_row_count_check(dataset):
    """Half a conversion must not pass silently as a complete data set."""
    short = ak.Array({"jetIEt": [[1], [2]], "jetIEta": [[0], [1]], "jetIPhi": [[3], [4]]})
    ak.to_parquet(short, dataset / "jets" / "L1Ntuple_2.parquet", compression="snappy")
    measured = summary.measure_folder(dataset, batch_size=16, checksums=False)

    assert status_of(measured, "rows match across objects") == "FAIL"


def test_a_missing_shard_fails_the_shard_name_check(dataset):
    (dataset / "jets" / "L1Ntuple_2.parquet").unlink()
    measured = summary.measure_folder(dataset, batch_size=16, checksums=False)

    assert status_of(measured, "shard names match across objects") == "FAIL"


def test_report_and_json_are_written_with_figures(dataset, tmp_path):
    written = summary.summarise_folder(
        dataset, tmp_path / "out", batch_size=16, checksums=False, generated_at="fixed"
    )
    report = (tmp_path / "out" / "REPORT.md").read_text()

    assert (tmp_path / "out" / "summary.json").is_file()
    for heading in ("# Data summary", "## Data records", "## Technical validation",
                    "## Trigger content", "## Event coverage", "## Figures"):
        assert heading in report
    assert written["figures"], "no figures were drawn"
    for figure in written["figures"]:
        assert (tmp_path / "out" / figure["path"]).is_file()
        assert figure["path"] in report


def test_provenance_from_a_campaign_config_is_rendered(dataset, tmp_path):
    """Only this test exercises the provenance table.

    The summary_run path passes provenance; the bare-folder path never does.
    """
    written = summary.summarise_folder(
        dataset, tmp_path / "out", batch_size=16, checksums=False, generated_at="fixed",
        provenance={
            "inputs": ["root://eoscms.cern.ch//eos/cms/store/a", "root://.../b"],
            "prescale_file": f"scripts/L1Menus/{MENU}",
            "mc": False,
            "l1_tree_name": "l1UpgradeTree/L1UpgradeTree",
        },
    )
    report = (tmp_path / "out" / "REPORT.md").read_text()

    assert written["provenance"]["mc"] is False
    assert "## Provenance" in report
    assert "`prescale_file`" in report and MENU in report
    assert "root://eoscms.cern.ch//eos/cms/store/a" in report
    assert "recorded data" in report, "the mc flag should reach the header"


def test_summary_json_carries_the_raw_counts_and_shard_rows(dataset, tmp_path):
    """The JSON is what a later consumer reads instead of the parquet.

    It carries the per-shard rows and full digests, and the value counts the figures
    were drawn from.
    """
    summary.summarise_folder(
        dataset, tmp_path / "out", batch_size=16, checksums=True, generated_at="fixed"
    )
    payload = json.loads((tmp_path / "out" / "summary.json").read_text())
    shards = payload["inventory"]["jets"]["files"]

    assert [shard["rows"] for shard in shards] == [EVENTS, EVENTS]
    assert all(len(shard["sha256"]) == 64 for shard in shards)
    assert payload["objects"]["jets"]["features"]["jetIEt"]["counts"]["values"]


def test_an_output_directory_we_did_not_write_is_refused(dataset, tmp_path):
    """Never delete somebody else's directory just because it was named as the output."""
    intruder = tmp_path / "out"
    intruder.mkdir()
    (intruder / "important.txt").write_text("keep me")

    with pytest.raises(FileExistsError, match="not written by this tool"):
        summary.summarise_folder(dataset, intruder, batch_size=16, checksums=False)


def test_an_empty_folder_is_refused(tmp_path):
    (tmp_path / "nothing").mkdir()

    with pytest.raises(ValueError, match="no object folders"):
        summary.measure_folder(tmp_path / "nothing")
