# Every figure in a summary or a comparison, drawn from the accumulated counts.
#
# Because stats.py counts exactly, a spectrum is a weighted histogram over the counted
# values. No value axis is converted: it is labelled in hardware units, so a bar spans
# whole codes. Every axis quotes the factor to GeV, radians or eta wherever the schema
# documents one, the comparison and campaign overlays included.
#
# Guessed bin widths ('doane' and its relatives) suit bounded integers badly: fractional
# edges across a flag such as `egIso`, whose two bits hold four codes, give bars that no
# longer stand for the codes.

from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import mplhep as hep
import numpy as np
from matplotlib.colors import LogNorm

# The most bars a spectrum draws: a wider integer range is coarsened by a whole factor,
# so a bin still spans whole codes.
MAX_BINS = 256
# The most bars the ranked seed chart draws; the report tabulates the whole menu anyway.
TOP_SEEDS = 40
DPI = 150

# The transverse energies a campaign overlays across its samples, which is where a
# signal separates from the zero-bias background.
ET_OVERLAY = (
    ("muons", "muonIEt"),
    ("jets", "jetIEt"),
    ("egammas", "egIEt"),
    ("taus", "tauIEt"),
    ("ET", "Et"),
    ("HT", "Et"),
    ("MET", "Et"),
)

# Features holding a physical quantity rather than a hardware code, for which the note
# _units writes would be wrong. Pileup is brilcalc's per-section mean in recorded data
# and the generated count in simulation, so it is an interaction count either way.
UNIT_LABELS = {("event_info", "nPV_True"): "[interactions per crossing]"}

# Dashes distinguish the series a colour cycle has to repeat: a campaign overlays 21
# samples over the six colours the CMS style defines.
LINESTYLES = ("-", "--", ":", "-.")

# Every seed of every sample, written beside the campaign figures because the heatmap
# has room for the head of the ranking alone.
SEED_TABLE = "seed_fractions.csv"

# Whether the data set was recorded or simulated: a module-level default that
# use_cms_style overwrites for the rest of the process.
STYLE = {"data": False}


def use_cms_style(data: bool = False) -> None:
    """Adopt the CMS plotting style.

    A function rather than an import side effect: importing a module should not
    reconfigure matplotlib for the rest of the process. Any rcParams the caller had set
    are discarded, since the defaults are restored before the CMS style is applied.

    :param data: False labels every figure drawn afterwards as simulation.
    """
    matplotlib.rcParams.update(matplotlib.rcParamsDefault)
    hep.style.use("CMS")
    STYLE["data"] = data


def draw_all(
    summary: dict, outdir: Path, fmt: str = "png", clean: bool = False
) -> list:
    """Every figure for one data set.

    Sets the CMS style for the rest of the process, labelling the figures as simulation
    when ``provenance["mc"]`` is true and as recorded data when it is false or absent.

    :param clean: Delete every file under ``outdir`` this run did not draw, so no figure
        of an earlier schema survives beside the new ones.
    :returns: One ``{path, caption}`` record per figure, the paths relative to
        ``outdir.parent``, where the report that links to them is written.
    """
    use_cms_style(data=not summary["provenance"].get("mc", False))
    outdir.mkdir(parents=True, exist_ok=True)
    drawn = _object_figures(summary, outdir, fmt)
    drawn += _event_figures(summary, outdir, fmt)
    if clean:
        _prune(outdir, {figure["path"] for figure in drawn})

    return _relative(drawn, outdir.parent)


def draw_comparison(
    first: dict, second: dict, labels: list, outdir: Path, fmt: str, fractions: bool
) -> list:
    """Overlays of every shared feature except the seeds, which the report tabulates.

    An overlay carries the simulation label only where both data sets are simulated:
    the comparison that matters here puts recorded zero bias against its simulation,
    and calling that pair simulation would be wrong.

    :param labels: The two legend names, in the order (first, second).
    :param fractions: Divide each series by its own entry count, so two data sets of
        unequal size compare by shape.
    """
    recorded = [not side["provenance"].get("mc", False) for side in (first, second)]
    use_cms_style(data=any(recorded))
    outdir.mkdir(parents=True, exist_ok=True)
    drawn = []
    for name, obj in sorted(first["objects"].items()):
        other = second["objects"].get(name, {}).get("features", {})
        drawn += _overlay_object(
            name, obj, other, labels, outdir / name, fmt, fractions
        )

    return _relative(drawn, outdir.parent)


def draw_campaign(
    campaign: dict, outdir: Path, fmt: str = "png", clean: bool = False
) -> list:
    """Cross-sample figures, built from the per-data-set counts already in hand.

    No parquet is read: everything comes from the summaries the campaign collected.

    :param clean: Delete every file under ``outdir`` this run did not draw. The seed
        table written beside the figures is kept, since it is this run's output too.
    """
    recorded = [not e["provenance"].get("mc", False) for e in campaign["datasets"]]
    use_cms_style(data=any(recorded))
    outdir.mkdir(parents=True, exist_ok=True)
    drawn = [_campaign_accept_rates(campaign, outdir, fmt)]
    drawn.append(_campaign_seed_heatmap(campaign, outdir, fmt))
    for obj, feature in ET_OVERLAY:
        drawn.append(_campaign_overlay(campaign, obj, feature, outdir, fmt))
    figures = [figure for figure in drawn if figure]
    if clean:
        _prune(outdir, {f["path"] for f in figures} | {str(outdir / SEED_TABLE)})

    return _relative(figures, outdir.parent)


def seed_matrix(datasets: list) -> tuple[list, list, np.ndarray]:
    """Firing fraction of every seed in every sample, ranked by each seed's best.

    A sample whose menu lacks a seed reads zero, since the seed did not fire in it
    either way. The heatmap draws the head of this; the CSV beside it carries all of it.

    :returns: The seed names in ranked order, the sample names in the order given, and
        the fractions indexed [seed, sample].
    """
    rates = [_seed_rates(entry) for entry in datasets]
    names = sorted({name for row in rates for name in row})
    matrix = np.array([[row.get(name, 0.0) for row in rates] for name in names])
    if not names:
        return [], [entry["dataset"] for entry in datasets], matrix
    order = np.argsort(-matrix.max(axis=1))

    return [names[i] for i in order], [e["dataset"] for e in datasets], matrix[order]


def _seed_rates(entry: dict) -> dict:
    return {seed["name"]: seed["fraction"] for seed in entry["trigger"].get("seeds", [])}


def _campaign_accept_rates(campaign: dict, outdir: Path, fmt: str) -> dict | None:
    """What fraction of each sample the menu in force already accepts."""
    rates = [_accept_rate(entry) for entry in campaign["datasets"]]
    rates = [row for row in rates if row]
    if not rates:
        return None
    path = outdir / f"l1bit_accept.{fmt}"
    _accept_chart(rates, path)

    return _record(path, "Fraction of events the level 1 trigger accepted, per sample.")


def _accept_rate(entry: dict) -> tuple | None:
    """One sample's accept fraction, or None where it carries no L1bit to divide."""
    accepted = entry["trigger"].get("l1bit_accepted")
    events = entry["totals"]["events"]

    return (
        (entry["dataset"], accepted / events)
        if accepted is not None and events
        else None
    )


def _accept_chart(rates: list, path: Path) -> None:
    # Three tenths of an inch per sample, so the names stay legible as samples are added.
    fig, axes = plt.subplots(figsize=(10, max(4.0, 0.3 * len(rates) + 2)))
    positions = np.arange(len(rates))
    axes.barh(positions, [rate for _, rate in rates], color="C0")
    axes.set_yticks(positions, [name[:44] for name, _ in rates], fontsize=7)
    axes.invert_yaxis()
    _label(axes, "L1 accept fraction", "")
    _save(fig, path)


def _campaign_seed_heatmap(campaign: dict, outdir: Path, fmt: str) -> dict | None:
    """The most active seeds against every sample, which is the seed study in one panel.

    Only the head of the ranking is drawn; seed_fractions.csv beside it holds the rest.
    """
    names, samples, matrix = seed_matrix(campaign["datasets"])
    if not names or not matrix.size or matrix.max() <= 0:
        return None
    path = outdir / f"seed_fractions.{fmt}"
    shown = min(len(names), TOP_SEEDS)
    _seed_heatmap(names[:shown], samples, matrix[:shown], path)

    return _record(path, f"Firing fraction of the {shown} most active seeds, per sample.")


def _seed_heatmap(names: list, samples: list, matrix: np.ndarray, path: Path) -> None:
    """Seeds down the rows, samples across the columns, on a logarithmic colour scale.

    A seed that never fires in a sample is masked rather than clamped, so a blank cell
    reads as silence instead of as the lowest rate on the scale.
    """
    fig, axes = plt.subplots(
        figsize=(max(8.0, 0.5 * len(samples) + 4), max(4.0, 0.28 * len(names) + 2))
    )
    image = axes.imshow(
        np.ma.masked_equal(matrix, 0), aspect="auto", cmap="inferno", norm=LogNorm()
    )
    fig.colorbar(image, ax=axes, label="Fraction of events firing")
    axes.set_xticks(np.arange(len(samples)), samples, rotation=90, fontsize=6)
    axes.set_yticks(np.arange(len(names)), names, fontsize=6)
    _save(fig, path)


def _campaign_overlay(campaign: dict, obj: str, feature: str, outdir: Path, fmt: str):
    """One feature across every sample, each normalised so the shapes compare."""
    series = _campaign_series(campaign, obj, feature)
    if not series:
        return None
    path = outdir / f"{obj}_{feature}.{fmt}"
    _overlaid_steps(series, path, _feature_label(obj, feature, series[0][2]))

    return _record(path, f"`{obj}.{feature}` across every sample in the campaign.")


def _campaign_series(campaign: dict, obj: str, feature: str) -> list:
    """Per-sample ``(label, counts, scale)`` for one feature, samples lacking it left out."""
    found = []
    for entry in campaign["datasets"]:
        holder = entry["objects"].get(obj, {}).get("features", {}).get(feature)
        if holder and holder["counts"].get("values"):
            found.append((entry["dataset"][:28], holder["counts"], holder.get("scale")))

    return found


def _overlaid_steps(series: list, path: Path, xlabel: str) -> None:
    """Every sample as an area-normalised step, all of them on edges spanning the lot.

    Shared edges are what makes the shapes comparable; binning each sample on its own
    range would put the same code in different bins from one sample to the next.
    """
    edges = bin_edges(np.concatenate([_arrays(counts)[0] for _, counts, _ in series]))
    fig, axes = plt.subplots()
    for index, (label, counts, _) in enumerate(series):
        _step_fraction(axes, counts, edges, label, index)
    axes.set_yscale("log")
    axes.legend(fontsize=6, ncol=2)
    _label(axes, xlabel, "Fraction of entries")
    _save(fig, path)


def _step_fraction(axes, counts: dict, edges, label: str, index: int) -> None:
    """One sample's shape, divided by its own entries so any two samples compare."""
    values, weights = _arrays(counts)
    heights, _ = np.histogram(values, bins=edges, weights=weights / weights.sum())
    hep.histplot(heights, bins=edges, ax=axes, label=label, **_series_style(index))


def _overlay_object(name, obj, other, labels, outdir, fmt, fractions) -> list:
    drawn = []
    for feature, entry in sorted(obj["features"].items()):
        if feature not in other or name == "seeds":
            continue
        path = outdir / f"{feature}.{fmt}"
        if _overlay(
            entry["counts"],
            other[feature]["counts"],
            labels,
            _feature_label(name, feature, entry.get("scale")),
            path,
            fractions,
        ):
            drawn.append(_record(path, f"`{name}.{feature}` in both data sets."))

    return drawn


def _overlay(
    left: dict, right: dict, labels: list, xlabel: str, path: Path, fractions: bool
) -> bool:
    """Two spectra on edges spanning both, so their shapes compare bin for bin.

    A column carrying no counts on either side, such as the event and time counters,
    draws nothing and returns False, so no report links a figure that does not exist.

    :param xlabel: The finished axis label, units and all, as _feature_label builds it.
    """
    pairs = [_arrays(left), _arrays(right)]
    populated = [values for values, _ in pairs if values.size]
    if not populated:
        return False
    edges = bin_edges(np.concatenate(populated))
    fig, axes = plt.subplots()
    heights = [
        _filled(axes, values, weights, edges, labels[index], f"C{index}", fractions)
        for index, (values, weights) in enumerate(pairs)
    ]
    _log_if_steep(axes, np.concatenate(heights))
    axes.legend(fontsize=9)
    _label(axes, xlabel, "Fraction of entries" if fractions else "Entries")
    _save(fig, path)

    return True


def _filled(
    axes, values, weights, edges, label: str, colour: str, fractions: bool
) -> np.ndarray:
    """One filled series, scaled to fractions on request.

    A series with no entries keeps a scale of 1 rather than dividing by zero.

    :returns: The bin heights, which the caller needs to judge the vertical scale.
    """
    scale = weights.sum() if fractions and weights.sum() else 1.0
    heights, _ = np.histogram(values, bins=edges, weights=weights / scale)

    hep.histplot(
        heights,
        bins=edges,
        ax=axes,
        label=label,
        histtype="fill",
        alpha=0.45,
        color=colour,
    )

    return heights


def spectrum(values, weights, xlabel: str, path: Path) -> None:
    """A one-dimensional spectrum with one bin per value wherever that fits.

    :param values: The distinct values counted, not raw samples.
    :param weights: How often each value occurred, aligned element by element with
        ``values``.
    :param xlabel: The finished axis label. A caller counting hardware codes passes what
        _feature_label builds; one counting objects per event passes its own words,
        since a count carries no units to quote.
    """
    edges = bin_edges(values)
    counts, _ = np.histogram(values, bins=edges, weights=weights)
    fig, axes = plt.subplots()
    hep.histplot(counts, bins=edges, ax=axes, histtype="fill", alpha=0.6, color="C0")
    hep.histplot(counts, bins=edges, ax=axes, color="C0")
    _finish_axes(axes, counts, xlabel, weights.sum())
    _save(fig, path)


def bin_edges(values: np.ndarray) -> np.ndarray:
    """One bin per integer value, coarsened by a whole factor when there are too many.

    The integer edges fall on half-integers, so a bin covers whole codes instead of
    splitting one. Evenly spaced edges are used instead for floats, and for integers so
    large that float64 cannot hold an edge half a step away from a value. Nothing drawn
    comes near that second case: the wide identifiers, such as the packed time field near
    7e18 where consecutive doubles are about a thousand apart, go through stats.Extremes
    and carry no counts to bin.

    :returns: At least two strictly increasing edges for any input, empty or constant
        included, since np.histogram accepts nothing less.
    """
    if values.size == 0:
        return np.array([0.0, 1.0])
    low, high = float(values.min()), float(values.max())
    step = max(1, int(np.ceil((high - low + 1) / MAX_BINS)))
    if not _is_integral(values) or np.spacing(max(abs(low), abs(high))) > step / 2:
        return _even_edges(low, high)

    return np.arange(low - 0.5, high + 0.5 + step, step)


def _even_edges(low: float, high: float) -> np.ndarray:
    """Evenly spaced edges, cut back to the number float64 can keep apart.

    The pad is the larger of half a unit, which leaves a constant input spanning one bin,
    and twice the spacing between doubles, which keeps the padded ends distinct from the
    data. A span narrower than that spacing collapses to a single edge, which
    np.histogram cannot use; the fallback is one bin a single representable step wide.
    """
    pad = max(0.5, np.spacing(max(abs(low), abs(high))) * 2)
    start, stop = low - pad, high + pad
    resolvable = int((stop - start) / np.spacing(max(abs(start), abs(stop))))
    edges = np.unique(np.linspace(start, stop, min(MAX_BINS, max(1, resolvable)) + 1))

    return edges if edges.size > 1 else np.array([start, np.nextafter(start, np.inf)])


def _object_figures(summary: dict, outdir: Path, fmt: str) -> list:
    drawn = []
    for name, obj in sorted(summary["objects"].items()):
        drawn += _feature_figures(name, obj, outdir / name, fmt)
        drawn.append(_multiplicity_figure(name, obj, outdir / name, fmt))
        drawn.append(_occupancy_figure(name, obj, outdir / name, fmt))
    if summary.get("trigger", {}).get("seeds"):
        drawn += _seed_figures(summary["trigger"], outdir / "seeds", fmt)

    return [figure for figure in drawn if figure]


def _feature_figures(name: str, obj: dict, outdir: Path, fmt: str) -> list:
    drawn = []
    for feature, entry in sorted(obj["features"].items()):
        values, weights = _arrays(entry["counts"])
        # A seed is two bars and the ranked chart says more; a constant column is one
        # bar and the schema table already gives its value.
        if values.size < 2 or name == "seeds":
            continue
        path = outdir / f"{feature}.{fmt}"
        spectrum(values, weights, _feature_label(name, feature, entry.get("scale")), path)
        drawn.append(_record(path, f"Distribution of `{feature}` in `{name}`."))

    return drawn


def _multiplicity_figure(name: str, obj: dict, outdir: Path, fmt: str) -> dict | None:
    """Entries per event, skipped for the objects whose multiplicity never varies."""
    values, weights = _arrays(obj["multiplicity"]["counts"])
    if values.size < 2:
        return None
    path = outdir / f"multiplicity.{fmt}"
    spectrum(values, weights, f"{name} per event", path)

    return _record(path, f"Number of `{name}` entries per event.")


def _occupancy_figure(name: str, obj: dict, outdir: Path, fmt: str) -> dict | None:
    """The eta-phi map, which is where masked regions and detector gaps show up.

    The occupancy pairs are keyed (eta, phi) in that order, since measure.py counts them
    over schema.OCCUPANCY_COLUMNS; transposing the grid puts eta along x. Both axes are
    hardware codes, whose step differs between the muon and the calorimeter objects.
    """
    if not obj.get("occupancy"):
        return None
    path = outdir / f"occupancy.{fmt}"
    grid, extent = _grid(obj["occupancy"])
    fig, axes = plt.subplots()
    # Occupancy spans several decades between the busy barrel and the sparse forward
    # cells, which a linear scale renders as one bright band on black. Cells nothing
    # landed in are masked rather than clamped, so they stay blank instead of reading as
    # the lowest populated value.
    image = axes.imshow(
        np.ma.masked_equal(grid.T, 0),
        origin="lower",
        aspect="auto",
        extent=extent,
        cmap="inferno",
        norm=LogNorm(vmin=1),
        interpolation="nearest",
    )
    fig.colorbar(image, ax=axes, label="Entries")
    _label(axes, f"{name} eta (hardware)", "phi (hardware)")
    _save(fig, path)

    return _record(path, f"Occupancy of `{name}` in hardware eta and phi.")


def _seed_figures(trigger: dict, outdir: Path, fmt: str) -> list:
    outdir.mkdir(parents=True, exist_ok=True)
    values, weights = _arrays(trigger["multiplicity"]["counts"])
    multiplicity = outdir / f"seed_multiplicity.{fmt}"
    spectrum(values, weights, "seeds firing per event", multiplicity)
    drawn = [_record(multiplicity, "Number of unprescaled seeds firing per event.")]
    # core.py ranks the seeds by firing fraction, so the head of the list is the top.
    # A data set where nothing fired leaves no rate to put on a logarithmic axis, and
    # returning early keeps the report from linking a figure that was never drawn.
    top = [seed for seed in trigger["seeds"] if seed["fired"]][:TOP_SEEDS]
    if not top:
        return drawn
    rates = outdir / f"firing_rates.{fmt}"
    _seed_rate_chart(top, rates)

    return drawn + [
        _record(rates, f"The {len(top)} most frequently firing unprescaled seeds.")
    ]


def _seed_rate_chart(top: list, path: Path) -> None:
    """Firing fraction of the most frequent seeds, spanning several decades.

    Markers rather than bars, because a bar on a logarithmic axis starts at the clipped
    left limit rather than at zero: its length would then be set by the smallest rate
    plotted and would change with the sample, while carrying no meaning of its own.
    """
    # Just over a quarter inch of figure height per seed, so a long list stretches the
    # figure rather than crowding the seed names.
    fig, axes = plt.subplots(figsize=(10, max(4.0, 0.28 * len(top) + 2)))
    positions = np.arange(len(top))
    fractions = [seed["fraction"] for seed in top]
    axes.hlines(positions, min(fractions) / 2, fractions, color="C0", linewidth=0.8)
    axes.plot(fractions, positions, "o", color="C0", markersize=4)
    axes.set_yticks(positions, [seed["name"] for seed in top], fontsize=7)
    # Positions number upwards, so the axis is flipped to leave the most frequent seed
    # at the top.
    axes.invert_yaxis()
    axes.set_xscale("log")
    axes.grid(axis="x", alpha=0.3)
    _label(axes, "Fraction of events firing", "")
    _save(fig, path)


def _event_figures(summary: dict, outdir: Path, fmt: str) -> list:
    """Events against luminosity section, which is where a gap in a run shows up."""
    profile = summary.get("event_coverage", {}).get("run_lumi")
    if not profile:
        return []
    (outdir / "event_info").mkdir(parents=True, exist_ok=True)
    path = outdir / "event_info" / f"lumi_profile.{fmt}"
    _lumi_profile(profile, path)

    return [_record(path, "Events recorded in each luminosity section, per run.")]


def _lumi_profile(profile: list, path: Path) -> None:
    """One line per run, from the ``[run, lumi, events]`` rows core.py writes out.

    The vertical axis reaches zero. Events per section vary by a few per cent within a
    fill, and an axis autoscaled to that range magnifies the ripple into an apparent
    collapse.
    """
    fig, axes = plt.subplots()
    for index, run in enumerate(sorted({entry[0] for entry in profile})):
        points = sorted((entry[1], entry[2]) for entry in profile if entry[0] == run)
        axes.plot(*zip(*points), label=f"run {run}", linewidth=1, **_series_style(index))
    axes.set_ylim(bottom=0)
    axes.legend(fontsize=9)
    _label(axes, "Luminosity section", "Events")
    _save(fig, path)


def _series_style(index: int) -> dict:
    """Colour and dash pattern for one series of an overlay.

    The colour advances first and the dash pattern only once the colours run out, so
    the first few series differ in the way a reader notices soonest.
    """
    colours = plt.rcParams["axes.prop_cycle"].by_key()["color"]

    return {
        "color": colours[index % len(colours)],
        "linestyle": LINESTYLES[(index // len(colours)) % len(LINESTYLES)],
    }


def _finish_axes(axes, counts: np.ndarray, xlabel: str, entries: float) -> None:
    _log_if_steep(axes, counts)
    _label(axes, xlabel, "Entries")
    axes.legend([f"N = {int(entries):,}"], handlelength=0, fontsize=10, frameon=False)


def _log_if_steep(axes, counts: np.ndarray) -> None:
    """A logarithmic vertical axis once the filled bins span more than three decades."""
    filled = counts[counts > 0]
    if filled.size and filled.max() / filled.min() > 1e3:
        axes.set_yscale("log")


def _feature_label(name: str, feature: str, scale) -> str:
    """The finished x axis of one feature, whichever units it is counted in."""
    return f"{name} {feature} {UNIT_LABELS.get((name, feature)) or _units(scale)}"


def _units(scale) -> str:
    """The conversion goes in the axis label: a secondary axis overlaps the CMS label."""
    if not scale:
        return "[hardware units]"

    return f"[hardware units, $\\times${scale[0]:.4g} = {scale[1]}]"


def _label(axes, xlabel: str, ylabel: str) -> None:
    axes.set_xlabel(xlabel)
    axes.set_ylabel(ylabel)
    # mplhep reads com in TeV: 13.6 is the Run 3 collision energy.
    hep.cms.label("Preliminary", data=STYLE["data"], com=13.6, ax=axes)


def _save(fig, path: Path) -> None:
    """Write one figure, without the version string matplotlib stamps into it.

    That stamp would change the bytes of an unchanged figure on every upgrade.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI, bbox_inches="tight", metadata=_metadata(path))
    plt.close(fig)


def _metadata(path: Path) -> dict:
    """The metadata key each writer stamps the matplotlib version into.

    PNG carries it under 'Software' and PDF under 'Creator'; None drops the entry.
    """
    return {"Software": None} if path.suffix == ".png" else {"Creator": None}


def _arrays(counts: dict) -> tuple[np.ndarray, np.ndarray]:
    """Values and weights of one count map, as float64.

    A stored code past 2**53 arrives rounded, which is why bin_edges stops trusting
    integer edges once the spacing between doubles exceeds half a bin.
    """
    values = np.asarray(counts.get("values", []), dtype=np.float64)

    return values, np.asarray(counts.get("counts", []), dtype=np.float64)


def _grid(triples: list) -> tuple[np.ndarray, list]:
    """A sparse list of (x, y, count) as a dense array indexed (x, y), with its extent.

    The keys are integers and each pair occurs once, so a cell is assigned rather than
    accumulated, and a cell nothing landed in stays zero. The extent is imshow's
    [left, right, bottom, top], reaching half a unit past the extreme keys, which centres
    every cell on its integer pair; callers transpose, because imshow indexes
    (row, column).
    """
    first, second, weights = (np.array([row[i] for row in triples]) for i in range(3))
    lows, highs = (first.min(), second.min()), (first.max(), second.max())
    grid = np.zeros((highs[0] - lows[0] + 1, highs[1] - lows[1] + 1))
    grid[first - lows[0], second - lows[1]] = weights

    return grid, [lows[0] - 0.5, highs[0] + 0.5, lows[1] - 0.5, highs[1] + 0.5]


def _record(path: Path, caption: str) -> dict:
    return {"path": str(path), "caption": caption}


def _relative(drawn: list, root: Path) -> list:
    """Paths relative to the report written beside them, so the Markdown links resolve."""
    relative = [
        figure | {"path": str(Path(figure["path"]).relative_to(root))}
        for figure in drawn
    ]

    return sorted(relative, key=lambda figure: figure["path"])


def _is_integral(values: np.ndarray) -> bool:
    return bool(np.all(values == np.rint(values)))


def _prune(outdir: Path, keep: set) -> None:
    """Delete every file under ``outdir`` this run did not draw.

    ``keep`` holds paths as ``str(Path)`` and is matched literally, so it has to be built
    from the same ``outdir``.
    """
    for stale in sorted(outdir.rglob("*")):
        if stale.is_file() and str(stale) not in keep:
            stale.unlink()
