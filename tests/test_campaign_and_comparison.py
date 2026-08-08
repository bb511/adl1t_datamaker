"""The campaign aggregate and the two-folder comparison, from summaries alone.

Both consume what summarise_folder already produced, so regenerating a campaign report
or comparing two summarised folders reads no parquet at all.
"""

import numpy as np
import pytest

import awkward as ak

from adl1t_datamaker import report
from adl1t_datamaker import summary

EVENTS = 20


def build(folder, seed: int, seeds: list[str], jet_shift: int = 0):
    """A minimal but complete conversion: jets, event_info and a seeds table.

    :param seed: Fixes every draw below, so the same arguments always give the same
        data set.
    :param seeds: Seed column names, which is what decides whether two samples look
        like they came from one menu.
    :param jet_shift: Added to every jetIEt code, giving the comparison a known shift
        to find.
    """
    rng = np.random.default_rng(seed)
    counts = rng.integers(1, 4, EVENTS)
    (folder / "jets").mkdir(parents=True)
    ak.to_parquet(
        ak.Array({
            "jetIEt": ak.unflatten(
                rng.integers(10, 100, int(counts.sum())) + jet_shift, counts
            ),
            "jetIEta": ak.unflatten(rng.integers(-40, 40, int(counts.sum())), counts),
        }),
        folder / "jets" / "L1Ntuple_1.parquet", compression="snappy",
    )
    (folder / "event_info").mkdir(parents=True)
    ak.to_parquet(
        ak.singletons(ak.Array({
            "run": np.full(EVENTS, 1), "lumi": np.ones(EVENTS, dtype=np.int64),
            "event": np.arange(EVENTS), "bx": rng.integers(1, 3564, EVENTS),
            "orbit": np.arange(EVENTS), "time": np.zeros(EVENTS, dtype=np.int64),
            "nPV_True": np.zeros(EVENTS, dtype=np.float32),
        })),
        folder / "event_info" / "L1Ntuple_1.parquet", compression="snappy",
    )
    (folder / "seeds").mkdir(parents=True)
    fired = {name: rng.random(EVENTS) < 0.3 for name in seeds}
    fired["L1bit"] = np.logical_or.reduce(list(fired.values()))
    ak.to_parquet(
        ak.singletons(ak.Array(fired)),
        folder / "seeds" / "L1Ntuple_1.parquet", compression="snappy",
    )

    return folder


@pytest.fixture
def two_samples(tmp_path):
    first = build(tmp_path / "SampleA", 1, ["L1_SingleMu22", "L1_SingleJet180"])
    second = build(tmp_path / "SampleB", 2, ["L1_SingleMu22", "L1_SingleJet180"], 25)

    return [summary.measure_folder(path, batch_size=8, checksums=False)
            for path in (first, second)]


def test_campaign_lists_every_sample_and_totals_them(two_samples, tmp_path):
    campaign = summary.summarise_campaign(
        two_samples, tmp_path / "campaign", experiment="TestCampaign",
        config="paths:\n  input_root_path: somewhere\n", generated_at="fixed",
    )
    text = (tmp_path / "campaign" / "REPORT.md").read_text()

    assert [entry["dataset"] for entry in campaign["datasets"]] == ["SampleA", "SampleB"]
    assert "TestCampaign" in text
    assert "`SampleA`" in text and "`SampleB`" in text
    assert f"**{2 * EVENTS:,}**" in text, "totals row missing"
    assert "input_root_path: somewhere" in text, "resolved config not recorded"


def test_campaign_records_which_inputs_were_merged(two_samples, tmp_path):
    """Several input directories can feed one output folder; only the config knows."""
    first, second = two_samples
    first["provenance"] = {"inputs": ["eos://a/0000", "eos://a/0001"]}
    second["provenance"] = {"inputs": ["eos://b/0000"]}
    summary.summarise_campaign(
        [first, second], tmp_path / "campaign", experiment="Merged", generated_at="fixed"
    )
    text = (tmp_path / "campaign" / "REPORT.md").read_text()

    assert "## Input folders" in text
    assert "eos://a/0000" in text and "eos://a/0001" in text


def test_campaign_report_links_back_to_each_data_set(two_samples, tmp_path):
    """The campaign report lands two levels below the output root.

    It is written to <output root>/SUMMARY/<experiment>, so its links to the per-data-set
    reports have to climb back out to reach them.
    """
    summary.summarise_campaign(
        two_samples, tmp_path / "campaign", experiment="TestCampaign", generated_at="fixed"
    )
    text = (tmp_path / "campaign" / "REPORT.md").read_text()

    assert "../../SampleA/SUMMARY/REPORT.md" in text


def test_a_differing_seed_set_is_reported_as_a_campaign_inconsistency(tmp_path):
    """A menu that changes part way through a campaign leaves no other trace.

    Each sample converts and validates cleanly on its own, so only a comparison across
    the campaign shows that the samples no longer share a trigger menu.
    """
    odd = summary.measure_folder(
        build(tmp_path / "SampleC", 3, ["L1_SingleMu22"]), batch_size=8, checksums=False
    )
    same = summary.measure_folder(
        build(tmp_path / "SampleD", 4, ["L1_SingleMu22", "L1_SingleJet180"]),
        batch_size=8, checksums=False,
    )
    campaign = summary.summarise_campaign(
        [odd, same], tmp_path / "campaign", experiment="Mixed", generated_at="fixed"
    )

    assert campaign["consistency"]["seed_sets"], "the differing seed set went unnoticed"
    assert "differ" in report.campaign_consistency(campaign)


def test_comparison_reports_the_shift_between_two_samples(two_samples, tmp_path):
    first, second = two_samples
    comparison = summary.summarise_comparison(
        first, second, tmp_path / "diff", labels=("A", "B"), generated_at="fixed"
    )
    text = (tmp_path / "diff" / "COMPARISON.md").read_text()
    shifted = next(row for row in comparison["features"] if row["column"] == "jets.jetIEt")

    # The two samples are drawn with different seeds and hold 20 events each, so the
    # +25 shift sits on several units of sampling noise: hence the loose tolerance.
    assert shifted["difference"] == pytest.approx(25, abs=12), "the +25 shift was missed"
    assert "## Feature differences" in text and "`jets.jetIEt`" in text
    assert (tmp_path / "diff" / "figures" / "jets" / "jetIEt.png").is_file()


def test_comparison_names_columns_present_on_one_side_only(two_samples, tmp_path):
    first, second = two_samples
    del second["objects"]["jets"]["features"]["jetIEta"]
    comparison = summary.compare(first, second, ("A", "B"))

    assert comparison["schema"]["only_in_first"] == ["jets.jetIEta"]
    assert comparison["schema"]["only_in_second"] == []


def test_comparison_reads_a_stored_summary_rather_than_the_parquet(tmp_path):
    """Once a folder is summarised, comparing it must not touch the data again."""
    folder = build(tmp_path / "SampleE", 5, ["L1_SingleMu22"])
    summary.summarise_folder(folder, batch_size=8, checksums=False, generated_at="fixed")
    for parquet in folder.rglob("*.parquet"):
        parquet.unlink()

    assert summary.load_or_measure(folder)["totals"]["events"] == EVENTS
