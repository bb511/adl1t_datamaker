"""Campaign aggregation, axis labels and the CSV export of the plot data.

All three read the summary dictionaries core.py assembles and never touch parquet, so
the fixtures here are hand-written summaries rather than converted folders.
"""

import csv
import importlib.util
import json
from pathlib import Path

import pytest

from adl1t_datamaker.summary import core
from adl1t_datamaker.summary import figures


def summary_of(name: str, *, mc: bool, seeds: dict, events: int, accepted: int) -> dict:
    """A summary carrying just what a campaign reads out of one."""
    return {
        "dataset": name,
        "provenance": {"mc": mc},
        "totals": {"events": events, "objects": ["jets", "seeds"]},
        "objects": {
            "jets": {
                "capacity": 12,
                "multiplicity": {"counts": {"values": [0, 1], "counts": [3, 7]}},
                "features": {
                    "jetIEt": {
                        "scale": [0.5, "GeV"],
                        "counts": {"values": [1, 2, 3], "counts": [10, 5, 1]},
                    }
                },
            }
        },
        "trigger": {
            "n_seeds": len(seeds),
            "l1bit_accepted": accepted,
            "never_fired": [n for n, fraction in seeds.items() if not fraction],
            "multiplicity": {"counts": {"values": [0, 1], "counts": [9, 1]}},
            "seeds": [
                {"name": name, "fired": int(fraction * events), "fraction": fraction}
                for name, fraction in sorted(seeds.items())
            ],
        },
    }


@pytest.fixture
def campaign_summaries() -> list[dict]:
    return [
        summary_of(
            "sample_a",
            mc=True,
            seeds={"L1_A": 0.5, "L1_B": 0.0},
            events=100,
            accepted=50,
        ),
        summary_of(
            "sample_b",
            mc=True,
            seeds={"L1_A": 0.25, "L1_C": 0.75},
            events=200,
            accepted=20,
        ),
    ]


def test_seed_matrix_ranks_by_the_best_sample(campaign_summaries):
    """A seed absent from a sample reads zero there, and the ranking uses the maximum."""
    names, samples, matrix = figures.seed_matrix(campaign_summaries)

    assert samples == ["sample_a", "sample_b"]
    assert names == ["L1_C", "L1_A", "L1_B"]
    assert matrix[names.index("L1_C")].tolist() == [0.0, 0.75]
    assert matrix[names.index("L1_B")].tolist() == [0.0, 0.0]


def test_campaign_writes_report_figures_and_every_seed(tmp_path, campaign_summaries):
    campaign = core.summarise_campaign(campaign_summaries, tmp_path, experiment="test")

    assert (tmp_path / "REPORT.md").is_file()
    assert (tmp_path / "campaign_summary.json").is_file()
    assert campaign["figures"], "no campaign figure was drawn"
    rows = list(csv.reader((tmp_path / "figures" / "seed_fractions.csv").open()))
    assert rows[0] == ["seed", "sample_a", "sample_b"]
    # Every seed of either menu, not only the ones the heatmap has room for.
    assert {row[0] for row in rows[1:]} == {"L1_A", "L1_B", "L1_C"}


def test_campaign_json_drops_what_each_summary_already_holds(tmp_path, campaign_summaries):
    core.summarise_campaign(campaign_summaries, tmp_path)
    stored = json.loads((tmp_path / "campaign_summary.json").read_text())

    assert all("objects" not in entry for entry in stored["datasets"])
    assert [entry["dataset"] for entry in stored["datasets"]] == ["sample_a", "sample_b"]


def test_campaign_consistency_names_the_odd_sample(campaign_summaries):
    """The samples run different menus here, so neither seed set is the common one."""
    consistency = core._campaign_consistency(campaign_summaries)

    assert consistency["seed_sets"], "differing seed sets went unreported"


def test_seeds_that_never_fire_still_draw_their_multiplicity(tmp_path):
    """A data set where nothing fired has no rate chart, and must not take the run down.

    The ranked chart is drawn on a logarithmic axis, which an empty selection has no
    origin for; the figure is dropped rather than linked and left undrawn.
    """
    trigger = {
        "seeds": [{"name": "L1_A", "fired": 0, "fraction": 0.0}],
        "multiplicity": {"counts": {"values": [0, 1], "counts": [5, 0]}},
    }
    figures.use_cms_style()
    drawn = figures._seed_figures(trigger, tmp_path, "png")

    assert [Path(figure["path"]).name for figure in drawn] == ["seed_multiplicity.png"]
    assert all(Path(figure["path"]).is_file() for figure in drawn)


def test_pileup_axis_is_not_labelled_in_hardware_units():
    """nPV_True counts interactions, so the hardware-code note would be wrong."""
    label = figures._feature_label("event_info", "nPV_True", None)

    assert "hardware" not in label
    assert "interactions per crossing" in label


def test_documented_scale_reaches_the_axis():
    label = figures._feature_label("jets", "jetIEt", [0.5, "GeV"])

    assert "0.5" in label and "GeV" in label


def test_a_feature_without_a_scale_keeps_the_hardware_note():
    assert figures._units(None) == "[hardware units]"


def load_exporter():
    """scripts/export_plot_data, which has no .py suffix to import by name."""
    path = Path(__file__).resolve().parent.parent / "scripts" / "export_plot_data"
    spec = importlib.util.spec_from_loader("export_plot_data", loader=None)
    module = importlib.util.module_from_spec(spec)
    exec(compile(path.read_text(), str(path), "exec"), module.__dict__)

    return module


def test_export_writes_the_counts_and_the_physical_value(tmp_path, campaign_summaries):
    exporter = load_exporter()
    exporter.export_summary(campaign_summaries[0], tmp_path)
    rows = list(csv.DictReader(_without_note(tmp_path / "jets" / "jetIEt.csv")))

    assert [row["count"] for row in rows] == ["10", "5", "1"]
    # The documented factor is 0.5 GeV per code, so code 2 is 1 GeV.
    assert rows[1]["physical"] == "1.0"


def test_export_totals_match_the_summary(tmp_path, campaign_summaries):
    """A count table that does not sum to the measured entries would misplot."""
    exporter = load_exporter()
    exporter.export_summary(campaign_summaries[0], tmp_path)
    rows = list(csv.DictReader(_without_note(tmp_path / "jets" / "jetIEt.csv")))

    assert sum(int(row["count"]) for row in rows) == 16


def test_export_overlay_covers_the_union_of_both_value_sets(tmp_path):
    exporter = load_exporter()
    left = {"counts": {"values": [1, 2], "counts": [4, 4]}}
    right = {"counts": {"values": [2, 3], "counts": [1, 9]}}
    rows = exporter.overlay_rows(left, right)

    assert [row[0] for row in rows] == [1, 2, 3]
    assert rows[0][1:3] == [4, 0]
    assert rows[2][3] == 0.0 and rows[2][4] == 0.9


def _without_note(path: Path):
    """The CSV lines without the leading '# ...' note write_csv puts above the header."""
    return [line for line in path.read_text().splitlines() if not line.startswith("#")]
