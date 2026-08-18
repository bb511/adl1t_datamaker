# Every figure in a summary or a comparison, drawn from the accumulated counts.
#
# Because stats.py counts exactly, a spectrum is a weighted histogram over the counted
# values. No value axis is converted: it is labelled in hardware units, so a bar spans
# whole codes. A spectrum also quotes the factor to GeV, radians or eta in that label
# wherever the schema documents one; the comparison overlays quote no factor.
#
# Guessed bin widths ('doane' and its relatives) suit bounded integers badly: fractional
# edges across a flag such as `egIso`, whose two bits hold four codes, give bars that no
# longer stand for the codes.

from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import mplhep as hep
import numpy as np

# The most bars a spectrum draws: a wider integer range is coarsened by a whole factor,
# so a bin still spans whole codes.
MAX_BINS = 256
# The most bars the ranked seed chart draws; the report tabulates the whole menu anyway.
TOP_SEEDS = 40
DPI = 150

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

    The CMS style is taken with its default, so every overlay carries the simulation
    label whatever the two summaries say about ``mc``.

    :param labels: The two legend names, in the order (first, second).
    :param fractions: Divide each series by its own entry count, so two data sets of
        unequal size compare by shape.
    """
    use_cms_style()
    outdir.mkdir(parents=True, exist_ok=True)
    drawn = []
    for name, obj in sorted(first["objects"].items()):
        other = second["objects"].get(name, {}).get("features", {})
        drawn += _overlay_object(
            name, obj, other, labels, outdir / name, fmt, fractions
        )

    return _relative(drawn, outdir.parent)


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
            f"{name} {feature}",
            path,
            fractions,
        ):
            drawn.append(_record(path, f"`{name}.{feature}` in both data sets."))

    return drawn


def _overlay(
    left: dict, right: dict, labels: list, label: str, path: Path, fractions: bool
) -> bool:
    """Two spectra on edges spanning both, so their shapes compare bin for bin.

    A column carrying no counts on either side, such as the event and time counters,
    draws nothing and returns False, so no report links a figure that does not exist.
    """
    pairs = [_arrays(left), _arrays(right)]
    populated = [values for values, _ in pairs if values.size]
    if not populated:
        return False
    edges = bin_edges(np.concatenate(populated))
    fig, axes = plt.subplots()
    for index, (values, weights) in enumerate(pairs):
        _filled(axes, values, weights, edges, labels[index], f"C{index}", fractions)
    axes.legend(fontsize=9)
    _label(
        axes,
        f"{label} [hardware units]",
        "Fraction of entries" if fractions else "Entries",
    )
    _save(fig, path)

    return True


def _filled(
    axes, values, weights, edges, label: str, colour: str, fractions: bool
) -> None:
    """One filled series, scaled to fractions on request.

    A series with no entries keeps a scale of 1 rather than dividing by zero.
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


def spectrum(values, weights, label: str, path: Path, scale=None) -> None:
    """A one-dimensional spectrum with one bin per value wherever that fits.

    :param values: The distinct values counted, not raw samples.
    :param weights: How often each value occurred, aligned element by element with
        ``values``.
    :param scale: The ``(factor, unit)`` pair from ``schema.unit_scale``, which goes into
        the axis label; None for a feature with no documented conversion.
    """
    edges = bin_edges(values)
    counts, _ = np.histogram(values, bins=edges, weights=weights)
    fig, axes = plt.subplots()
    hep.histplot(counts, bins=edges, ax=axes, histtype="fill", alpha=0.6, color="C0")
    hep.histplot(counts, bins=edges, ax=axes, color="C0")
    _finish_axes(axes, counts, label, weights.sum(), scale)
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
    outdir.mkdir(parents=True, exist_ok=True)
    drawn = []
    for feature, entry in sorted(obj["features"].items()):
        values, weights = _arrays(entry["counts"])
        # A seed is two bars and the ranked chart says more; a constant column is one
        # bar and the schema table already gives its value.
        if values.size < 2 or name == "seeds":
            continue
        path = outdir / f"{feature}.{fmt}"
        spectrum(values, weights, f"{name} {feature}", path, entry.get("scale"))
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
    image = axes.imshow(
        grid.T,
        origin="lower",
        aspect="auto",
        extent=extent,
        cmap="inferno",
        interpolation="nearest",
    )
    fig.colorbar(image, ax=axes, label="Entries")
    _label(axes, f"{name} eta (hardware)", "phi (hardware)")
    _save(fig, path)

    return _record(path, f"Occupancy of `{name}` in hardware eta and phi.")


def _seed_figures(trigger: dict, outdir: Path, fmt: str) -> list:
    outdir.mkdir(parents=True, exist_ok=True)
    # core.py ranks the seeds by firing fraction, so the head of the list is the top.
    top = [seed for seed in trigger["seeds"] if seed["fired"]][:TOP_SEEDS]
    rates = outdir / f"firing_rates.{fmt}"
    _seed_rate_chart(top, rates)
    values, weights = _arrays(trigger["multiplicity"]["counts"])
    multiplicity = outdir / f"seed_multiplicity.{fmt}"
    spectrum(values, weights, "seeds firing per event", multiplicity)

    return [
        _record(rates, f"The {len(top)} most frequently firing unprescaled seeds."),
        _record(multiplicity, "Number of unprescaled seeds firing per event."),
    ]


def _seed_rate_chart(top: list, path: Path) -> None:
    # Just over a quarter inch of figure height per seed, so a long list stretches the
    # figure rather than crowding the seed names.
    fig, axes = plt.subplots(figsize=(10, max(4.0, 0.28 * len(top) + 2)))
    positions = np.arange(len(top))
    axes.barh(positions, [seed["fraction"] for seed in top], color="C0")
    axes.set_yticks(positions, [seed["name"] for seed in top], fontsize=7)
    # barh numbers positions upwards, so the axis is flipped to leave the most frequent
    # seed at the top.
    axes.invert_yaxis()
    axes.set_xscale("log")
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
    """One line per run, from the ``[run, lumi, events]`` rows core.py writes out."""
    fig, axes = plt.subplots()
    for index, run in enumerate(sorted({entry[0] for entry in profile})):
        points = sorted((entry[1], entry[2]) for entry in profile if entry[0] == run)
        # The CN colour spec takes a single digit, so an eleventh run reuses C0.
        axes.plot(
            *zip(*points), label=f"run {run}", color=f"C{index % 10}", linewidth=1
        )
    axes.legend(fontsize=9)
    _label(axes, "Luminosity section", "Events")
    _save(fig, path)


def _finish_axes(axes, counts: np.ndarray, label: str, entries: float, scale) -> None:
    """A logarithmic vertical axis once the filled bins span more than three decades."""
    filled = counts[counts > 0]
    if filled.size and filled.max() / filled.min() > 1e3:
        axes.set_yscale("log")
    _label(axes, f"{label} {_units(scale)}", "Entries")
    axes.legend([f"N = {int(entries):,}"], handlelength=0, fontsize=10, frameon=False)


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
