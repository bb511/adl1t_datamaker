# Summarising a converted data set: assemble the numbers, then write them out.
#
# The converter writes parquet and nothing else, so a data descriptor has to recover
# everything about a produced folder from the files themselves. This module drives that
# recovery: measure.py counts, validation.py judges, figures.py draws and report.py
# renders. What lands beside the data is a REPORT.md for a reader and a summary.json,
# raw value counts included, for a program.

import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from adl1t_datamaker import figures
from adl1t_datamaker import measure
from adl1t_datamaker import report
from adl1t_datamaker import schema
from adl1t_datamaker import stats
from adl1t_datamaker import validation
from adl1t_datamaker.components import l1_seeds
from adl1t_datamaker.terminal_colors import tcols

SUMMARY_DIR = "SUMMARY"
MENU_FOLDER = Path(__file__).resolve().parents[2] / "scripts" / "L1Menus"

# Unix seconds at 2000-01-01 and 2100-01-01, the open window a decoded event time must
# fall in to count as a wall clock.
PLAUSIBLE_EPOCH = (946_684_800, 4_102_444_800)


def summarise_folder(
    folder: str | Path,
    outdir: str | Path | None = None,
    *,
    batch_size: int = 200_000,
    checksums: bool = True,
    objects: list[str] | None = None,
    figure_format: str = "png",
    provenance: dict | None = None,
    generated_at: str | None = None,
    clean: bool = False,
) -> dict:
    """Measure one produced data folder and write its report, figures and JSON.

    :param outdir: Where the report, the figures and the JSON land. Without it they go
        into a SUMMARY directory inside the data folder itself.
    :param batch_size: Events held in memory at once, which buys memory alone for every
        column narrow enough to be counted exactly. A wider batch can span more than
        stats.MAX_DENSE_SPAN and demote a column a narrower one still counts.
    :param checksums: Whether to sha256 every shard, which reads each file in full and
        is the slowest step of a summary.
    :param objects: Object folders to stream, or ``None`` for all of them. The file
        inventory covers the whole folder either way.
    :param figure_format: Suffix the figures are saved with, which is what picks the
        matplotlib writer. The scripts offer ``png`` and ``pdf``.
    :param provenance: What the conversion config knows and the parquet cannot say. The
        checks and the figures read ``mc`` from it to tell recorded data from
        simulation.
    :param generated_at: ISO timestamp replacing the current time, so a rerun on the
        same data reproduces the report byte for byte.
    :param clean: Whether to delete figures this run did not draw, which is how the
        leftovers of an earlier schema disappear.
    :raises ValueError: If the folder holds no object folder with parquet in it.
    :raises FileExistsError: If the output directory holds files but no summary.json,
        so it was not written by this tool.
    """
    folder = Path(folder)
    outdir = Path(outdir) if outdir else folder / SUMMARY_DIR
    print(tcols.HEADER + f"Summarising {folder}..." + tcols.ENDC)

    summary = measure_folder(folder, batch_size, checksums, objects, provenance)
    summary["generated"] = generated_block(generated_at)
    write_summary(summary, outdir, figure_format, clean)
    print(tcols.OKGREEN + "Summary written: " + tcols.ENDC + str(outdir))

    return summary


def measure_folder(
    folder: Path,
    batch_size: int = 200_000,
    checksums: bool = True,
    objects: list[str] | None = None,
    provenance: dict | None = None,
) -> dict:
    """Every number the report quotes, with no files written and no figures drawn.

    :raises ValueError: If the folder holds no object folder with parquet in it.
    """
    inventory = measure.inventory(folder, checksums)
    if not inventory:
        raise ValueError(f"{folder} holds no object folders with parquet in them.")
    measured = measure.measure(folder, batch_size, objects)

    return _assemble(folder, measured, inventory, provenance or {})


def write_summary(summary: dict, outdir: Path, figure_format: str, clean: bool) -> dict:
    """Write REPORT.md, summary.json and the figures into one directory.

    The summary gains its ``figures`` entry in place, so the JSON on disk lists the same
    figures the report links to.

    :raises FileExistsError: If the directory holds files but no summary.json, so it
        was not written by this tool.
    """
    _guard_output(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    summary["figures"] = figures.draw_all(summary, outdir / "figures", figure_format, clean)
    (outdir / "REPORT.md").write_text(report.render_report(summary))
    write_json(summary, outdir / "summary.json")

    return summary


def write_json(payload: dict, path: Path) -> None:
    """Sorted keys and a trailing newline, so one payload always gives the same bytes."""
    path.write_text(json.dumps(payload, sort_keys=True, indent=2, default=float) + "\n")


def summarise_campaign(
    summaries: list[dict],
    outdir: str | Path,
    *,
    config: str = "",
    experiment: str = "campaign",
    figure_format: str = "png",
    generated_at: str | None = None,
) -> dict:
    """Aggregate several per-folder summaries, reading no parquet at all.

    :param config: The resolved campaign config, quoted verbatim in the report.
    :param experiment: Name of the campaign, which titles the report.
    :param figure_format: Suffix the figures are saved with, which is what picks the
        matplotlib writer. The scripts offer ``png`` and ``pdf``.
    :param generated_at: ISO timestamp replacing the current time, so a rerun on the
        same summaries reproduces the report byte for byte.
    :returns: The whole aggregate, value counts and shard lists included, where
        campaign_summary.json keeps only what no per-data-set summary already holds.
    """
    outdir = Path(outdir)
    campaign = {
        "experiment": experiment,
        "config": config,
        "generated": generated_block(generated_at),
        "datasets": sorted(summaries, key=lambda entry: entry["dataset"]),
    }
    campaign["consistency"] = _campaign_consistency(campaign["datasets"])
    outdir.mkdir(parents=True, exist_ok=True)
    campaign["figures"] = figures.draw_campaign(campaign, outdir / "figures", figure_format)
    (outdir / "REPORT.md").write_text(report.render_campaign(campaign))
    write_json(_slim_campaign(campaign), outdir / "campaign_summary.json")
    print(tcols.OKGREEN + "Campaign report written: " + tcols.ENDC + str(outdir))

    return campaign


def load_or_measure(folder: str | Path, **kwargs) -> dict:
    """A folder's existing summary.json, or a fresh measurement when there is none.

    :param kwargs: Passed to measure_folder, and so ignored where a summary.json is
        read instead of measured.
    """
    folder = Path(folder)
    existing = folder / SUMMARY_DIR / "summary.json"
    if existing.is_file():
        return json.loads(existing.read_text())
    print(tcols.WARNING + f"No summary.json in {folder}, measuring it." + tcols.ENDC)

    return measure_folder(folder, **kwargs)


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


def generated_block(generated_at: str | None = None) -> dict:
    """The only part of a report that changes between two runs on the same data."""
    return {
        "at": generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": git_commit(),
        "python": platform.python_version(),
        "packages": _package_versions(),
    }


def git_commit() -> str:
    """The checked-out commit, or 'unknown' whenever git cannot answer.

    A summary written outside a work tree, as the Docker image is, has no commit to
    quote, and that is a line missing from a report rather than a reason to stop.
    """
    try:
        head = subprocess.run(
            ["git", "-C", str(Path(__file__).resolve().parent), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"

    return head.stdout.strip() if head.returncode == 0 else "unknown"


def identify_menu(seed_names: set[str], menu_folder: Path = MENU_FOLDER) -> tuple:
    """The checked-in menu closest to these seed columns, and how many names differ.

    No two menus in scripts/L1Menus leave the same seeds unprescaled, so a zero mismatch
    names one menu. Returning the closest menu rather than only an exact match keeps a
    near miss visible, which validation then reports as a failing check.

    :returns: The menu file name and the size of the symmetric difference in seed names,
        with an equal mismatch broken by the alphabetically first name, or
        ``(None, None)`` when the folder holds no menu at all.
    """
    scored = [
        (len(set(l1_seeds.unprescaled_names(menu)) ^ seed_names), menu.name)
        for menu in sorted(menu_folder.glob("*.csv"))
    ]

    return (None, None) if not scored else tuple(reversed(min(scored)))


def _assemble(folder: Path, measured: dict, inventory: dict, provenance: dict) -> dict:
    summary = {
        "dataset": folder.name,
        "path": str(folder),
        "provenance": provenance,
        "inventory": inventory,
        "objects": {name: _object(counts) for name, counts in sorted(measured.items())},
        "totals": _totals(inventory),
    }
    summary["event_coverage"] = _event_coverage(measured.get("event_info"))
    summary["trigger"] = _trigger(measured.get("seeds"))
    summary["pileup_towers"] = _pileup_towers(folder, summary)
    summary["validation"] = validation.run_checks(summary)

    return summary


def _object(counts: measure.ObjectCounts) -> dict:
    return {
        "features": {
            name: _feature(counts, name) for name in sorted(counts.features)
        },
        "multiplicity": _store(counts.multiplicity),
        "capacity": schema.documented_capacities().get(counts.name),
        "occupancy": _pairs_to_json(counts.occupancy),
    }


def _feature(counts: measure.ObjectCounts, name: str) -> dict:
    doc = counts.documented.get(name, {})
    store = counts.features[name]

    return {
        "doc": doc,
        "scale": schema.unit_scale(counts.name, name),
        "stats": stats.summarise(store, schema.saturation_code(doc)),
        "counts": stats.counts_to_json(store.counts),
    }


def _store(store: stats.ValueCounts) -> dict:
    return {"stats": stats.summarise(store), "counts": stats.counts_to_json(store.counts)}


def _totals(inventory: dict) -> dict:
    rows = [entry["rows"] for entry in inventory.values()]

    # Objects should agree on rows and shards, so the maximum is the complete count and
    # a short object shows up as a validation failure rather than as a smaller total.
    return {
        "events": max(rows) if rows else 0,
        "bytes": sum(entry["bytes"] for entry in inventory.values()),
        "shards": max((entry["shards"] for entry in inventory.values()), default=0),
        "objects": sorted(inventory),
        "cicada": "cica" in inventory,
    }


def _event_coverage(counts: measure.ObjectCounts | None) -> dict:
    if counts is None:
        return {}
    features = counts.features
    coverage = {
        "runs": sorted(features["run"].counts) if "run" in features else [],
        "lumi_sections": _lumi_sections(counts.pairs),
        "run_lumi": _pairs_to_json(counts.pairs),
        "duplicate_identifiers": counts.duplicate_events(),
    }
    coverage |= {key: _extent(features.get(key)) for key in ("orbit", "time", "bx")}
    coverage["wall_clock"] = _wall_clock(features.get("time"))

    return coverage | _pileup(features.get("nPV_True"), counts.rows)


def _wall_clock(store: stats.ValueCounts | None) -> dict | None:
    """When the data was taken, decoded from the packed time field.

    docs/README.md gives the packing: Unix seconds shifted left by 32 bits, with the
    microseconds in the low word. The seconds sit above the microseconds, so the packed
    integers order as the times do and the extremes of the count map are the first and
    last event; the microseconds are dropped with the shift. A field the converter never
    filled is zero and decodes to 1970, which is what PLAUSIBLE_EPOCH exists to catch:
    outside it the answer is no wall clock rather than a date.
    """
    if store is None or store.low is None:
        return None
    start, end = (int(value) >> 32 for value in (store.low, store.high))
    if not PLAUSIBLE_EPOCH[0] < start <= end < PLAUSIBLE_EPOCH[1]:
        return None

    return {
        "start": datetime.fromtimestamp(start, timezone.utc).isoformat(),
        "end": datetime.fromtimestamp(end, timezone.utc).isoformat(),
        "seconds": end - start,
    }


def _lumi_sections(pairs: dict) -> dict:
    """Per run, the luminosity sections that hold events and the gaps between them."""
    per_run: dict = {}
    for (run, lumi), events in sorted(pairs.items()):
        per_run.setdefault(run, {})[lumi] = events

    return {str(run): _run_sections(sections) for run, sections in sorted(per_run.items())}


def _run_sections(sections: dict) -> dict:
    """One run's coverage, counting gaps inside the observed span alone.

    Nothing in the parquet says where a run ended, so `missing` counts only the gaps
    between the first and last section seen, never a truncation at either end.
    """
    lows, highs = min(sections), max(sections)

    return {
        "events": sum(sections.values()),
        "first": lows,
        "last": highs,
        "present": len(sections),
        "missing": highs - lows + 1 - len(sections),
    }


def _pileup(store: stats.ValueCounts | None, rows: int) -> dict:
    if store is None:
        return {"pileup": None, "zero_pileup_fraction": None}
    summary = stats.summarise(store)

    return {
        "pileup": summary,
        "zero_pileup_fraction": stats.fraction_equal(store.counts, 0.0, rows),
    }


def _extent(store: stats.ValueCounts | None) -> dict | None:
    if store is None:
        return None

    return {"min": store.low, "max": store.high, "span": store.high - store.low}


def _trigger(counts: measure.ObjectCounts | None) -> dict:
    """The seed table, the overall accept and the menu the columns came from.

    L1bit is dropped before the menu is identified: l1_seeds synthesises it as the OR of
    the seeds, so no menu lists it and leaving it in would put every menu one name out.
    """
    if counts is None:
        return {}
    names = sorted(set(counts.features) - {measure.L1BIT})
    menu, mismatch = identify_menu(set(names))
    fired = {name: counts.features[name].counts.get(1, 0) for name in names}
    accepted = counts.features.get(measure.L1BIT)

    return {
        "n_seeds": len(names),
        "menu": menu,
        "menu_mismatch": mismatch,
        "events": counts.rows,
        "l1bit_accepted": accepted.counts.get(1, 0) if accepted else None,
        "never_fired": sorted(name for name, count in fired.items() if count == 0),
        "always_fired": sorted(name for name, count in fired.items() if count == counts.rows),
        "multiplicity": _store(counts.seed_multiplicity),
        "seeds": _ranked_seeds(fired, counts.rows),
    }


def _ranked_seeds(fired: dict, rows: int) -> list[dict]:
    """Seeds by firing fraction, name breaking ties so the order is reproducible."""
    ordered = sorted(fired.items(), key=lambda item: (-item[1], item[0]))

    return [
        {"name": name, "fired": count, "fraction": count / rows if rows else 0.0}
        for name, count in ordered
    ]


def _pileup_towers(folder: Path, summary: dict) -> list:
    """Joint pileup and tower counts, left empty where the map would say nothing.

    measure.pileup_against_towers reads the parquet a second time, so it runs only where
    some event carries non-zero pileup and an HT folder is there to read tower_count
    from. An all-zero pileup column is what an unmatched brilcalc lookup leaves behind.
    """
    zero = summary["event_coverage"].get("zero_pileup_fraction")
    if zero is None or zero == 1.0 or "HT" not in summary["inventory"]:
        return []

    return _pairs_to_json(measure.pileup_against_towers(folder))


def _pairs_to_json(pairs: dict) -> list:
    return [[first, second, count] for (first, second), count in sorted(pairs.items())]


def _campaign_consistency(datasets: list[dict]) -> dict:
    """What differs between the data sets of one campaign, which should be nothing."""
    objects = {entry["dataset"]: set(entry["totals"]["objects"]) for entry in datasets}
    seeds = {
        entry["dataset"]: {seed["name"] for seed in entry["trigger"].get("seeds", [])}
        for entry in datasets
    }

    return {
        "object_sets": _odd_ones_out(objects),
        "seed_sets": _odd_ones_out(seeds),
        "menus": sorted({entry["trigger"].get("menu") for entry in datasets} - {None}),
    }


def _odd_ones_out(per_dataset: dict) -> dict:
    """Data sets whose set differs from the largest one, and by how many names."""
    if not per_dataset:
        return {}
    common = max(per_dataset.values(), key=len)

    return {name: len(common ^ items) for name, items in per_dataset.items() if items != common}


PER_DATASET_ONLY = ("objects", "inventory")


def _slim_campaign(campaign: dict) -> dict:
    """The campaign JSON without what each data set's own summary.json already holds.

    The value counts and the per-shard file lists are most of a summary's bulk, so
    repeating them once per data set would dominate the campaign file for no gain.
    """
    return campaign | {
        "datasets": [
            {key: value for key, value in entry.items() if key not in PER_DATASET_ONLY}
            for entry in campaign["datasets"]
        ]
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


def _guard_output(outdir: Path) -> None:
    """Refuse a directory this tool did not write.

    root2parquet rejects an overwrite because a clash there destroys the conversion of a
    different input file. A summary destroys nothing, since every number in it can be
    measured again from the parquet beside it, so summaries are rewritten in place. An
    existing summary.json is the only evidence that the directory came from here.
    """
    if outdir.is_dir() and any(outdir.iterdir()) and not (outdir / "summary.json").is_file():
        raise FileExistsError(
            tcols.FAIL + f"{outdir} is not empty and holds no summary.json, so it was "
            "not written by this tool. Move it aside or pass a different output "
            "directory." + tcols.ENDC
        )


def _package_versions() -> dict:
    """Versions of the libraries the reported numbers and figures depend on."""
    import awkward
    import matplotlib
    import numpy
    import pyarrow

    return {
        "awkward": awkward.__version__,
        "matplotlib": matplotlib.__version__,
        "numpy": numpy.__version__,
        "pyarrow": pyarrow.__version__,
    }
