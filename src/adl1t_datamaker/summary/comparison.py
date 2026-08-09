# Comparing two measured data sets, which is how a reconversion gets validated: the
# original and the redo are summarised, then every shared column's statistics and every
# seed's firing fraction are set side by side.

from pathlib import Path

from adl1t_datamaker.summary import figures
from adl1t_datamaker.summary import report
from adl1t_datamaker.summary.core import generated_block, write_json
from adl1t_datamaker.terminal_colors import tcols


def summarise_comparison(
    first: dict,
    second: dict,
    outdir: str | Path,
    *,
    labels: tuple[str, str] | None = None,
    figure_format: str = "png",
    fractions: bool = True,
    generated_at: str | None = None,
) -> dict:
    """Compare two measured data sets and write COMPARISON.md beside the overlays.

    :param labels: Names the report gives the two data sets, defaulting to their folder
        names.
    :param figure_format: Suffix the figures are saved with, which is what picks the
        matplotlib writer. The scripts offer ``png`` and ``pdf``.
    :param fractions: Whether each overlay is drawn as a fraction of its own entries,
        so two samples of unequal size compare by shape rather than by height.
    :param generated_at: ISO timestamp replacing the current time, so a rerun on the
        same summaries reproduces the report byte for byte.
    """
    outdir = Path(outdir)
    comparison = compare(first, second, labels or (first["dataset"], second["dataset"]))
    comparison["generated"] = generated_block(generated_at)
    outdir.mkdir(parents=True, exist_ok=True)
    comparison["figures"] = figures.draw_comparison(
        first, second, comparison["labels"], outdir / "figures", figure_format, fractions
    )
    (outdir / "COMPARISON.md").write_text(report.render_comparison(comparison))
    write_json(comparison, outdir / "comparison.json")
    print(tcols.OKGREEN + "Comparison written: " + tcols.ENDC + str(outdir))

    return comparison


def compare(first: dict, second: dict, labels: tuple[str, str]) -> dict:
    """What differs between two data sets, computed from their summaries alone."""
    return {
        "labels": list(labels),
        "totals": [first["totals"], second["totals"]],
        "schema": _schema_difference(first, second),
        "features": _feature_deltas(first, second),
        "seeds": _seed_deltas(first, second),
    }


def _schema_difference(first: dict, second: dict) -> dict:
    """Columns held by one data set and not the other, named 'object.feature'."""
    columns = (_column_names(first), _column_names(second))

    return {
        "only_in_first": sorted(columns[0] - columns[1]),
        "only_in_second": sorted(columns[1] - columns[0]),
    }


def _column_names(summary: dict) -> set:
    return {
        f"{name}.{feature}"
        for name, obj in summary["objects"].items()
        for feature in obj["features"]
    }


def _feature_deltas(first: dict, second: dict) -> list[dict]:
    """Every shared feature, by how much its mean moved, largest relative shift first."""
    shared = sorted(_column_names(first) & _column_names(second))
    deltas = [_delta(first, second, column) for column in shared]

    return sorted(deltas, key=lambda row: -abs(row["relative"] or 0))


def _delta(first: dict, second: dict, column: str) -> dict:
    name, feature = column.split(".", 1)
    left = first["objects"][name]["features"][feature]["stats"]
    right = second["objects"][name]["features"][feature]["stats"]
    change = _difference(left.get("mean"), right.get("mean"))

    return {
        "column": column,
        "first": _quoted_stats(left),
        "second": _quoted_stats(right),
        "difference": change,
        "relative": change / left["mean"] if change is not None and left.get("mean") else None,
    }


def _quoted_stats(entry: dict) -> dict:
    """The three numbers the comparison table quotes for one column.

    The quantile keys are the str() of the levels in stats.QUANTILES, so the median is
    "0.5" and not "0.50", and a key that misses gives None rather than an error. A column
    too widely spread to count exactly carries no quantiles at all.
    """
    quantiles = entry.get("quantiles", {})

    return {
        "mean": entry.get("mean"),
        "median": quantiles.get("0.5"),
        "p99": quantiles.get("0.99"),
    }


def _seed_deltas(first: dict, second: dict) -> list[dict]:
    """Seeds by how much their firing fraction moved between the two data sets."""
    rates = [{seed["name"]: seed["fraction"] for seed in entry["trigger"].get("seeds", [])}
             for entry in (first, second)]
    shared = sorted(set(rates[0]) & set(rates[1]))
    deltas = [
        {"name": name, "first": rates[0][name], "second": rates[1][name],
         "difference": rates[1][name] - rates[0][name]}
        for name in shared
    ]

    return sorted(deltas, key=lambda row: -abs(row["difference"]))


def _difference(left, right):
    return None if left is None or right is None else right - left
