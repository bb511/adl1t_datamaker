# Every figure in a summary, drawn from the accumulated counts rather than from the data.
#
# Because stats.py counts exactly, a spectrum is a weighted histogram over the counted
# values: no second pass, no sampling, and one bin per hardware code where that fits.
# Guessed bin widths ('doane' and its relatives) suit bounded integers badly: fractional
# edges across a flag such as `egIso`, whose two bits hold four codes, give bars that no
# longer stand for the codes.

from pathlib import Path

import awkward as ak
import matplotlib
import matplotlib.pyplot as plt
import mplhep as hep
import numpy as np

from adl1t_datamaker import measure

MAX_BINS = 256
TOP_SEEDS = 40
DPI = 150

# The transverse energies, which the overview and campaign figures overlay on one axis.
ET_OVERLAY = (
    ("muons", "muonIEt"), ("jets", "jetIEt"), ("egammas", "egIEt"),
    ("taus", "tauIEt"), ("ET", "Et"), ("HT", "Et"), ("MET", "Et"),
)


# Whether the data set was recorded or simulated, which is all the CMS label needs.
# matplotlib already holds style as process-wide state, so a flag beside it costs less
# clarity than an argument threaded through every drawing function.
STYLE = {"data": False}


def use_cms_style(data: bool = False) -> None:
    """Adopt the CMS plotting style.

    A function rather than an import side effect: importing a module should not
    reconfigure matplotlib for the rest of the process.

    :param data: False labels every figure drawn afterwards as simulation.
    """
    matplotlib.rcParams.update(matplotlib.rcParamsDefault)
    hep.style.use("CMS")
    STYLE["data"] = data


def draw_all(summary: dict, outdir: Path, fmt: str = "png", clean: bool = False) -> list:
    """Every figure for one data set.

    :param clean: Delete every file under ``outdir`` this run did not draw, so no figure
        of an earlier schema survives beside the new ones.
    :returns: One ``{path, caption}`` record per figure, the paths relative to
        ``outdir.parent``, where the report that links to them is written.
    """
    use_cms_style(data=not summary["provenance"].get("mc", False))
    outdir.mkdir(parents=True, exist_ok=True)
    drawn = _object_figures(summary, outdir, fmt)
    drawn += _event_figures(summary, outdir, fmt)
    drawn += _overview_figures(summary, outdir, fmt)
    if clean:
        _prune(outdir, {figure["path"] for figure in drawn})

    return _relative(drawn, outdir.parent)


def draw_campaign(campaign: dict, outdir: Path, fmt: str = "png") -> list:
    """Cross-sample overlays, built from the per-data-set counts already in hand."""
    use_cms_style()
    outdir.mkdir(parents=True, exist_ok=True)
    drawn = [_campaign_accept_rates(campaign, outdir, fmt)]
    for obj, feature in ET_OVERLAY:
        drawn.append(_campaign_overlay(campaign, obj, feature, outdir, fmt))

    return _relative([figure for figure in drawn if figure], outdir.parent)


def draw_comparison(
    first: dict, second: dict, labels: list, outdir: Path, fmt: str, fractions: bool
) -> list:
    """Overlays of every shared feature except the seeds, which the report tabulates.

    :param labels: The two legend names, in the order (first, second).
    :param fractions: Divide each series by its own entry count, so two data sets of
        unequal size compare by shape.
    """
    use_cms_style()
    outdir.mkdir(parents=True, exist_ok=True)
    drawn = []
    for name, obj in sorted(first["objects"].items()):
        other = second["objects"].get(name, {}).get("features", {})
        drawn += _overlay_object(name, obj, other, labels, outdir / name, fmt, fractions)

    return _relative(drawn, outdir.parent)


def _overlay_object(name, obj, other, labels, outdir, fmt, fractions) -> list:
    drawn = []
    for feature, entry in sorted(obj["features"].items()):
        if feature not in other or name == "seeds":
            continue
        path = outdir / f"{feature}.{fmt}"
        _overlay(entry["counts"], other[feature]["counts"], labels,
                 f"{name} {feature}", path, fractions)
        drawn.append(_record(path, f"`{name}.{feature}` in both data sets."))

    return drawn


def _overlay(left: dict, right: dict, labels: list, label: str, path: Path, fractions: bool):
    """Two spectra on edges spanning both, so their shapes compare bin for bin."""
    pairs = [_arrays(left), _arrays(right)]
    combined = np.concatenate([values for values, _ in pairs if values.size])
    if combined.size == 0:
        return
    edges = bin_edges(combined)
    fig, axes = plt.subplots()
    for index, (values, weights) in enumerate(pairs):
        _filled(axes, values, weights, edges, labels[index], f"C{index}", fractions)
    axes.legend(fontsize=9)
    _label(axes, f"{label} [hardware units]", "Fraction of entries" if fractions else "Entries")
    _save(fig, path)


def _filled(axes, values, weights, edges, label: str, colour: str, fractions: bool) -> None:
    """One filled series, scaled to fractions on request.

    A series with no entries keeps a scale of 1 rather than dividing by zero.
    """
    scale = weights.sum() if fractions and weights.sum() else 1.0
    heights, _ = np.histogram(values, bins=edges, weights=weights / scale)

    hep.histplot(heights, bins=edges, ax=axes, label=label,
                 histtype="fill", alpha=0.45, color=colour)


def plot_feature_from_array(values, name: str, outdir: Path) -> None:
    """Plot a raw array by counting it first, for exploratory work in a notebook.

    The one entry point that takes an array. Everything else here draws from counts the
    measuring pass already produced.

    :param values: Any awkward array, jagged or not: it is flattened at every depth
        before counting.
    """
    from adl1t_datamaker import stats  # local: only this entry point counts anything

    use_cms_style()
    counts = stats.count_values(np.asarray(ak.to_numpy(ak.flatten(values, axis=None))))
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    spectrum(*stats.as_arrays(counts), name, outdir / f"{name}.png")


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

    Even bins take over for floats, and for integers so large that float64 cannot hold
    an edge half a step away from a value: the packed time field sits near 7e18, where
    consecutive doubles are already about a thousand apart.

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

    A span narrower than the spacing between doubles collapses to a single edge, which
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
    """The eta-phi map, which is where masked regions and detector gaps show up."""
    if not obj.get("occupancy"):
        return None
    path = outdir / f"occupancy.{fmt}"
    grid, extent = _grid(obj["occupancy"])
    fig, axes = plt.subplots()
    image = axes.imshow(
        grid.T, origin="lower", aspect="auto", extent=extent,
        cmap="inferno", interpolation="nearest",
    )
    fig.colorbar(image, ax=axes, label="Entries")
    _label(axes, f"{name} eta (hardware)", "phi (hardware)")
    _save(fig, path)

    return _record(path, f"Occupancy of `{name}` in hardware eta and phi.")


def _seed_figures(trigger: dict, outdir: Path, fmt: str) -> list:
    outdir.mkdir(parents=True, exist_ok=True)
    # summary.py ranks the seeds by firing fraction, so the head of the list is the top.
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
    fig, axes = plt.subplots(figsize=(10, max(4.0, 0.28 * len(top) + 2)))
    positions = np.arange(len(top))
    axes.barh(positions, [seed["fraction"] for seed in top], color="C0")
    axes.set_yticks(positions, [seed["name"] for seed in top], fontsize=7)
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
    fig, axes = plt.subplots()
    for index, run in enumerate(sorted({entry[0] for entry in profile})):
        points = sorted((entry[1], entry[2]) for entry in profile if entry[0] == run)
        axes.plot(*zip(*points), label=f"run {run}", color=f"C{index % 10}", linewidth=1)
    axes.legend(fontsize=9)
    _label(axes, "Luminosity section", "Events")
    _save(fig, path)


def _overview_figures(summary: dict, outdir: Path, fmt: str) -> list:
    (outdir / "overview").mkdir(parents=True, exist_ok=True)
    drawn = [_et_overlay(summary, outdir / "overview" / f"et_spectra.{fmt}")]
    drawn.append(_multiplicity_overlay(summary, outdir / "overview" / f"multiplicities.{fmt}"))
    if summary.get("pileup_towers"):
        drawn.append(_pileup_towers(summary, outdir / "overview" / f"pileup_vs_towers.{fmt}"))

    return [figure for figure in drawn if figure]


def _overlaid(draw, path: Path, xlabel: str, ylabel: str, fontsize: int = 9) -> bool:
    """Several series on one pair of axes, logarithmic in the vertical.

    Nothing is written when the callback drew no series, so a data set missing every
    object of an overlay leaves no empty figure behind.
    """
    fig, axes = plt.subplots()
    if not draw(axes):
        plt.close(fig)
        return False
    axes.legend(fontsize=fontsize)
    axes.set_yscale("log")
    _label(axes, xlabel, ylabel)
    _save(fig, path)

    return True


def _et_overlay(summary: dict, path: Path) -> dict | None:
    """Every transverse energy on one pair of axes, in GeV rather than hardware codes."""
    def draw(axes) -> int:
        drawn = 0
        for obj, feature in ET_OVERLAY:
            entry = summary["objects"].get(obj, {}).get("features", {}).get(feature)
            if entry:
                drawn += _step_in_gev(axes, entry, f"{obj}.{feature}", f"C{drawn % 10}")
        return drawn

    if not _overlaid(draw, path, "$E_T$ [GeV]", "Entries"):
        return None

    return _record(path, "Transverse energy spectra of every object, in GeV.")


def _step_in_gev(axes, entry: dict, label: str, colour: str) -> int:
    values, weights = _arrays(entry["counts"])
    if values.size == 0:
        return 0
    factor = (entry.get("scale") or [1.0])[0]
    # Bin the hardware codes and scale the edges afterwards, so a bin stays one code wide.
    edges = bin_edges(values) * factor
    counts, _ = np.histogram(values * factor, bins=edges, weights=weights)
    hep.histplot(counts, bins=edges, ax=axes, label=label, color=colour)

    return 1


def _multiplicity_overlay(summary: dict, path: Path) -> dict | None:
    def draw(axes) -> int:
        drawn = 0
        for name in ("muons", "jets", "egammas", "taus"):
            obj = summary["objects"].get(name)
            if obj:
                drawn += _step_fraction(axes, obj["multiplicity"]["counts"], name, f"C{drawn}")
        return drawn

    if not _overlaid(draw, path, "Entries per event", "Fraction of events", 10):
        return None

    return _record(path, "Object multiplicity per event, as a fraction of all events.")


def _step_fraction(axes, counts: dict, label: str, colour: str) -> int:
    values, weights = _arrays(counts)
    if values.size == 0:
        return 0
    edges = bin_edges(values)
    heights, _ = np.histogram(values, bins=edges, weights=weights / weights.sum())
    hep.histplot(heights, bins=edges, ax=axes, label=label, color=colour)

    return 1


def _pileup_towers(summary: dict, path: Path) -> dict:
    """Pileup is counted in tenths, so the horizontal extent is scaled back down.

    Cells with no events are masked rather than drawn: the colour scale is logarithmic,
    and _grid leaves every unobserved (pileup, tower) pair at zero.
    """
    grid, extent = _grid(summary["pileup_towers"])
    extent[:2] = [edge / measure.PILEUP_SCALE for edge in extent[:2]]
    fig, axes = plt.subplots()
    image = axes.imshow(
        np.ma.masked_equal(grid.T, 0), origin="lower", aspect="auto", extent=extent,
        cmap="inferno", norm="log", interpolation="nearest",
    )
    fig.colorbar(image, ax=axes, label="Events")
    _label(axes, "Pileup", "HCAL tower count")
    _save(fig, path)

    return _record(path, "Pileup against the number of HCAL towers, per event.")


def _campaign_overlay(campaign: dict, obj: str, feature: str, outdir: Path, fmt: str):
    """One feature across every sample of a campaign, normalised so the shapes compare."""
    def draw(axes) -> int:
        drawn = 0
        for entry in campaign["datasets"]:
            counts = entry["objects"].get(obj, {}).get("features", {}).get(feature, {})
            if counts:
                drawn += _step_fraction(axes, counts["counts"], entry["dataset"][:28], f"C{drawn % 10}")
        return drawn

    path = outdir / f"{obj}_{feature}.{fmt}"
    label = f"{obj} {feature} [hardware units]"
    if not _overlaid(draw, path, label, "Fraction of entries", 6):
        return None

    return _record(path, f"`{obj}.{feature}` across every sample in the campaign.")


def _campaign_accept_rates(campaign: dict, outdir: Path, fmt: str) -> dict | None:
    rates = [
        (entry["dataset"], entry["trigger"]["l1bit_accepted"] / entry["totals"]["events"])
        for entry in campaign["datasets"]
        if entry["trigger"].get("l1bit_accepted") is not None and entry["totals"]["events"]
    ]
    if not rates:
        return None
    path = outdir / f"l1bit_accept.{fmt}"
    _accept_chart(rates, path)

    return _record(path, "Fraction of events accepted by the level 1 trigger, per sample.")


def _accept_chart(rates: list, path: Path) -> None:
    fig, axes = plt.subplots(figsize=(10, max(4.0, 0.3 * len(rates) + 2)))
    positions = np.arange(len(rates))
    axes.barh(positions, [rate for _, rate in rates], color="C0")
    axes.set_yticks(positions, [name[:44] for name, _ in rates], fontsize=7)
    axes.invert_yaxis()
    _label(axes, "L1 accept fraction", "")
    _save(fig, path)


def _finish_axes(axes, counts: np.ndarray, label: str, entries: float, scale) -> None:
    """A logarithmic vertical axis once the filled bins span more than three decades."""
    filled = counts[counts > 0]
    if filled.size and filled.max() / filled.min() > 1e3:
        axes.set_yscale("log")
    _label(axes, f"{label} {_units(scale)}", "Entries")
    axes.legend([f"N = {int(entries):,}"], handlelength=0, fontsize=10, frameon=False)


def _units(scale) -> str:
    """The conversion rides in the axis label: a secondary axis overlaps the CMS label."""
    if not scale:
        return "[hardware units]"

    return f"[hardware units, $\\times${scale[0]:.4g} = {scale[1]}]"


def _label(axes, xlabel: str, ylabel: str) -> None:
    axes.set_xlabel(xlabel)
    axes.set_ylabel(ylabel)
    # mplhep reads com in TeV: 13.6 is the Run 3 collision energy.
    hep.cms.label("Preliminary", data=STYLE["data"], com=13.6, ax=axes)


def _save(fig, path: Path) -> None:
    """Written without the version string matplotlib stamps into a figure.

    The stamp would move the bytes on an upgrade, for a figure whose content is the same.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI, bbox_inches="tight", metadata=_metadata(path))
    plt.close(fig)


def _metadata(path: Path) -> dict:
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

    Each pair occurs once in the list, so a cell is assigned rather than accumulated.
    The extent reaches half a unit past the extreme keys, which centres every cell on
    its integer pair; callers transpose, because imshow indexes (row, column).
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
        figure | {"path": str(Path(figure["path"]).relative_to(root))} for figure in drawn
    ]

    return sorted(relative, key=lambda figure: figure["path"])


def _is_integral(values: np.ndarray) -> bool:
    return bool(np.all(values == np.rint(values)))


def _prune(outdir: Path, keep: set) -> None:
    """Delete figures this run did not produce, so none from an old schema survives."""
    for stale in sorted(outdir.rglob("*")):
        if stale.is_file() and str(stale) not in keep:
            stale.unlink()
