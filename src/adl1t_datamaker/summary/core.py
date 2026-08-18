# Summarising a converted data set: assemble the numbers, then write them out.
#
# The converter writes parquet and nothing else, so a data descriptor has to recover
# everything about a produced folder from the files themselves. This module drives that
# recovery: measure.py counts, validate.py judges, figures.py draws and report.py
# renders. The output is a REPORT.md for a reader, a summary.json for a program, raw
# value counts included, and the figures both of them list, written into a SUMMARY
# directory inside the data folder unless the caller names another.

import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from adl1t_datamaker import schema
from adl1t_datamaker.components import l1_seeds
from adl1t_datamaker.summary import figures
from adl1t_datamaker.summary import measure
from adl1t_datamaker.summary import report
from adl1t_datamaker.summary import stats
from adl1t_datamaker.summary import validate
from adl1t_datamaker.terminal_colors import tcols

SUMMARY_DIR = "SUMMARY"
MENU_FOLDER = Path(__file__).resolve().parents[3] / "scripts" / "L1Menus"

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
    :param batch_size: Events held in memory at once, which bounds what the streaming
        pass allocates.
    :param checksums: Whether to sha256 every shard, which reads each file in full
        rather than its footer alone and is the slowest step of a summary.
    :param objects: Object folders to stream, or ``None`` for all of them. The file
        inventory covers the whole folder either way.
    :param figure_format: Suffix the figures are saved with, which is what picks the
        matplotlib writer. The scripts offer ``png`` and ``pdf``.
    :param provenance: Facts from the conversion config that the parquet cannot carry.
        The checks and the figures read ``mc`` from it to tell recorded data from
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
    summary["figures"] = figures.draw_all(
        summary, outdir / "figures", figure_format, clean
    )
    (outdir / "REPORT.md").write_text(report.render_report(summary))
    write_json(summary, outdir / "summary.json")

    return summary


def write_json(payload: dict, path: Path) -> None:
    """Sorted keys and a trailing newline, so one payload always gives the same bytes."""
    path.write_text(json.dumps(payload, sort_keys=True, indent=2, default=float) + "\n")


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
    quote, and that is a line missing from a report rather than a reason to stop. A git
    that hangs counts as no answer too: the timeout raises, and the same handler catches
    it.
    """
    try:
        head = subprocess.run(
            ["git", "-C", str(Path(__file__).resolve().parent), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
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
    # run_checks indexes event_coverage and trigger, so validation comes last.
    summary["validation"] = validate.run_checks(summary)

    return summary


def _object(counts: measure.ObjectCounts) -> dict:
    return {
        "features": {name: _feature(counts, name) for name in sorted(counts.features)},
        "multiplicity": _store(counts.multiplicity),
        "capacity": schema.documented_capacities().get(counts.name),
        "occupancy": _pairs_to_json(counts.occupancy),
    }


def _feature(counts: measure.ObjectCounts, name: str) -> dict:
    """One feature's documentation, statistics and count map.

    The numbers stay in the hardware units the parquet stores: ``scale`` carries the
    factor and label that convert them to GeV, radians or eta, and nothing here applies
    it.
    """
    doc = counts.documented.get(name, {})
    store = counts.features[name]

    return {
        "doc": doc,
        "scale": schema.unit_scale(counts.name, name),
        "stats": stats.summarise(store, schema.saturation_code(doc)),
        "counts": stats.counts_to_json(store.counts),
    }


def _store(store: stats.ValueCounts) -> dict:
    return {
        "stats": stats.summarise(store),
        "counts": stats.counts_to_json(store.counts),
    }


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
    """Which events the data set covers, or ``{}`` without an event_info folder.

    The runs are read off the keys of an exact count map, which orbit and time do not
    have: measure.py accumulates those two through their extremes alone. The ``time``
    extent is therefore in the packed units of the column, and ``wall_clock`` is the
    decoded pair.
    """
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


def _wall_clock(store) -> dict | None:
    """When the data was taken, decoded from the packed time field.

    docs/README.md gives the packing: Unix seconds shifted left by 32 bits, with the
    microseconds in the low word. The seconds sit above the microseconds, so the packed
    integers order as the times do and the extremes measure.py keeps are the first and
    last event; the microseconds are dropped with the shift. Simulation records no time,
    and an unfilled field is zero, which decodes to 1970 and so sits below the lower
    bound of PLAUSIBLE_EPOCH: a decoded time outside that window gives no wall clock
    rather than a date.
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

    return {
        str(run): _run_sections(sections) for run, sections in sorted(per_run.items())
    }


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


def _pileup(store, rows: int) -> dict:
    """The pileup summary, and the share of events sitting at zero pileup.

    That share is taken over events, unlike the ``zero_fraction`` inside the summary,
    which stats.summarise takes over the finite entries counted. A non-finite nPV_True
    never reaches the count map, so such an event counts in the denominator here and
    never in the numerator, leaving the share a lower bound. The 0.0 key finds an
    integer zero as well, which it has to: the column is float32 in recorded data and
    int32 in simulation.
    """
    if store is None:
        return {"pileup": None, "zero_pileup_fraction": None}
    summary = stats.summarise(store)

    return {
        "pileup": summary,
        "zero_pileup_fraction": stats.fraction_equal(store.counts, 0.0, rows),
    }


def _extent(store) -> dict | None:
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
        "always_fired": sorted(
            name for name, count in fired.items() if count == counts.rows
        ),
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


def _pairs_to_json(pairs: dict) -> list:
    """Pair-keyed counts as ``[first, second, count]`` rows, JSON having no tuple key.

    The pairs are (eta, phi) hardware codes for an occupancy map and (run, lumi) for
    event coverage, in the order measure.py counted them.
    """
    return [[first, second, count] for (first, second), count in sorted(pairs.items())]


def _guard_output(outdir: Path) -> None:
    """Refuse a directory this tool did not write.

    root2parquet rejects an overwrite because a clash there destroys the conversion of a
    different input file. A summary destroys nothing, since every number in it can be
    measured again from the parquet beside it, so summaries are rewritten in place. An
    existing summary.json is the only evidence that the directory came from here.
    """
    if (
        outdir.is_dir()
        and any(outdir.iterdir())
        and not (outdir / "summary.json").is_file()
    ):
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
