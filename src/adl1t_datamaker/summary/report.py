# Rendering a measured data set as Markdown.
#
# No parquet is read here: every number comes from the summary dictionary core.py
# assembles, and the renderers only arrange it, in the order a Nature Scientific Data
# descriptor uses: how the data was made, what the records are, what is in them, and what
# was checked.

from adl1t_datamaker import schema

# Above this many shards the per-file table stops being readable, so the report points at
# summary.json instead, which always carries the full listing.
MAX_SHARD_ROWS = 25


def render_report(summary: dict) -> str:
    """The whole REPORT.md for one produced data folder."""
    return (
        "\n\n".join(
            [title_block(summary)] + [section(summary) for section in SECTIONS]
        ).rstrip()
        + "\n"
    )


def render_campaign(campaign: dict) -> str:
    """The aggregate report for one conversion campaign."""
    return (
        "\n\n".join(
            [f"# Conversion campaign: {campaign['experiment']}"]
            + [section(campaign) for section in CAMPAIGN_SECTIONS]
        ).rstrip()
        + "\n"
    )


def campaign_overview(campaign: dict) -> str:
    """One row per data set, which is the table a Data Records section prints."""
    rows = [_campaign_row(entry) for entry in campaign["datasets"]]
    header = ["Sample", "Events", "Seeds", "L1 accept", "Never fired", "Mean fired"]

    return "## Data sets\n\n" + markdown_table(header, rows)


def _campaign_row(entry: dict) -> list:
    trigger = entry.get("trigger", {})
    events = entry["totals"]["events"]
    accepted = trigger.get("l1bit_accepted")

    return [
        f"`{entry['dataset']}`",
        f"{events:,}",
        fmt(trigger.get("n_seeds")),
        _percent(accepted / events if accepted is not None and events else None),
        fmt(len(trigger.get("never_fired", []))),
        fmt(trigger.get("multiplicity", {}).get("stats", {}).get("mean"), 3),
    ]


def campaign_consistency(campaign: dict) -> str:
    """Whether the samples agree on objects, seed columns and prescale menu."""
    consistency = campaign["consistency"]
    rows = [
        ["Object sets", _odd_note(consistency["object_sets"])],
        ["Seed sets", _odd_note(consistency["seed_sets"])],
        ["Menus", ", ".join(f"`{menu}`" for menu in consistency["menus"]) or "-"],
    ]

    return "## Consistency\n\n" + markdown_table(["Check", "Outcome"], rows)


def _odd_note(odd: dict) -> str:
    """The data sets that differ from the largest set, or a note that none does."""
    if not odd:
        return "all samples agree"

    return ", ".join(f"`{name}` differs by {count}" for name, count in sorted(odd.items()))


def campaign_reproducibility(campaign: dict) -> str:
    """What produced this aggregate."""
    generated = campaign["generated"]
    rows = [
        ["Generated", generated["at"]],
        ["Commit", f"`{generated['commit']}`"],
        ["Python", generated["python"]],
    ]

    return "## Reproducibility\n\n" + markdown_table(["Item", "Value"], rows)


def render_comparison(comparison: dict) -> str:
    """COMPARISON.md for two data sets, which is how a reproduction gets validated."""
    first, second = comparison["labels"]

    return (
        "\n\n".join(
            [f"# Comparison: `{first}` against `{second}`"]
            + [section(comparison) for section in COMPARISON_SECTIONS]
        ).rstrip()
        + "\n"
    )


def comparison_totals(comparison: dict) -> str:
    """Whether the two data sets hold the same amount of data at all."""
    first, second = comparison["totals"]
    rows = [
        ["Events", f"{first['events']:,}", f"{second['events']:,}"],
        ["Shards", f"{first['shards']:,}", f"{second['shards']:,}"],
        ["Size", _human_size(first["bytes"]), _human_size(second["bytes"])],
        ["Objects", len(first["objects"]), len(second["objects"])],
    ]

    return "## Totals\n\n" + markdown_table(["Quantity", *comparison["labels"]], rows)


def comparison_schema(comparison: dict) -> str:
    """Which columns one data set carries and the other lacks."""
    schema_ = comparison["schema"]
    rows = [
        [f"`{column}`", comparison["labels"][0]] for column in schema_["only_in_first"]
    ]
    rows += [
        [f"`{column}`", comparison["labels"][1]] for column in schema_["only_in_second"]
    ]

    return "## Schema differences\n\n" + markdown_table(
        ["Column", "Present only in"], rows
    )


def comparison_features(comparison: dict) -> str:
    """Which shared columns moved, the largest relative shift in the mean first."""
    first, second = comparison["labels"]
    rows = [
        [
            f"`{row['column']}`",
            fmt(row["first"]["mean"]),
            fmt(row["second"]["mean"]),
            fmt(row["difference"]),
            _percent(row["relative"]),
            fmt(row["first"]["median"]),
            fmt(row["second"]["median"]),
            fmt(row["first"]["p99"]),
            fmt(row["second"]["p99"]),
        ]
        for row in comparison["features"]
    ]
    header = [
        "Column",
        f"Mean {first}",
        f"Mean {second}",
        "Difference",
        "Relative",
        f"Median {first}",
        f"Median {second}",
        f"p99 {first}",
        f"p99 {second}",
    ]

    return "## Feature differences\n\n" + markdown_table(header, rows)


def comparison_seeds(comparison: dict) -> str:
    """Each shared seed's firing fraction on both data sets, largest shift first."""
    first, second = comparison["labels"]
    rows = [
        [
            f"`{row['name']}`",
            _percent(row["first"]),
            _percent(row["second"]),
            _percent(row["difference"]),
        ]
        for row in comparison["seeds"]
    ]
    header = ["Seed", f"Fraction {first}", f"Fraction {second}", "Difference"]

    return "## Seed firing differences\n\n" + markdown_table(header, rows)


def markdown_table(header: list[str], rows: list[list]) -> str:
    """A pipe table, or a note when there is nothing to put in it."""
    if not rows:
        return "_Nothing to report._"
    lines = [f"| {' | '.join(header)} |", f"|{'|'.join(['---'] * len(header))}|"]

    return "\n".join(
        lines + [f"| {' | '.join(str(cell) for cell in row)} |" for row in rows]
    )


def fmt(value, digits: int = 4) -> str:
    """One formatter for every number a table cell holds; `-` marks an unmeasured one.

    Integral values print without a decimal point, so a hardware code that reaches here
    as a float (the quantiles are computed in float64) still reads as a code. Booleans
    take the plain `str` path instead, since `bool` is an `int` and `True` would
    otherwise print as 1.

    :param digits: Significant digits, not decimal places, kept for the rest.
    """
    if value is None:
        return "-"
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, int) or float(value).is_integer():
        return f"{int(value):,}"

    return f"{value:.{digits}g}"


def title_block(summary: dict) -> str:
    """What this data set is, in the counts that come before any table."""
    totals = summary["totals"]

    return "\n".join(
        [
            f"# Data summary: {summary['dataset']}",
            "",
            f"- **Events**: {totals['events']:,}",
            f"- **Objects**: {len(totals['objects'])} (`{'`, `'.join(totals['objects'])}`)",
            f"- **Shards per object**: {totals['shards']:,}",
            f"- **Total size**: {_human_size(totals['bytes'])}",
            f"- **CICADA present**: {'yes' if totals['cicada'] else 'no'}",
            f"- **Source**: {'simulation' if summary['provenance'].get('mc') else 'recorded data'}",
        ]
    )


def section_provenance(summary: dict) -> str:
    """Where the data came from, which is the Methods section of a descriptor."""
    known = summary["provenance"]
    rows = [
        [f"`{key}`", _provenance_value(value)] for key, value in sorted(known.items())
    ]
    note = (
        ""
        if known
        else (
            "\n\n_Run without a campaign config, so only what the data itself reveals is "
            "recorded. Use `scripts/summary_run` with the matching `+experiment=` to capture "
            "the input paths, tree names and prescale menu._"
        )
    )

    return "## Provenance\n\n" + markdown_table(["Field", "Value"], rows) + note


def section_inventory(summary: dict) -> str:
    """What the records physically are: the Data Records section.

    A parquet row is one event in every object folder, the jagged ones included, so the
    bytes per row quoted here are bytes per event.
    """
    rows = [
        [
            f"`{name}`",
            f"{entry['shards']:,}",
            f"{entry['rows']:,}",
            len(entry["dtypes"]),
            _human_size(entry["bytes"]),
            fmt(entry["bytes"] / entry["rows"] if entry["rows"] else 0, 3),
            ", ".join(entry["compression"]),
            f"{entry['row_groups']:,}",
        ]
        for name, entry in sorted(summary["inventory"].items())
    ]
    header = [
        "Object",
        "Shards",
        "Rows",
        "Columns",
        "Size",
        "Bytes/event",
        "Codec",
        "Row groups",
    ]

    return "\n\n".join(
        [
            "## Data records",
            markdown_table(header, rows),
            _shard_table(summary),
        ]
    )


def section_schema(summary: dict) -> str:
    """What each stored column holds, measured, beside its `docs/README.md` entry.

    `Entries` counts stored values rather than events: a particle collection contributes
    one entry per object, so its count is a total object count.
    """
    blocks = ["## Schema and measured statistics", _units_note()]
    for name, obj in sorted(summary["objects"].items()):
        if name == "seeds":
            continue  # section_trigger reports the seeds, one row per seed
        blocks += [
            f"### `{name}`",
            markdown_table(_schema_header(), _schema_rows(name, obj)),
        ]

    return "\n\n".join(blocks)


def section_multiplicities(summary: dict) -> str:
    """How many entries each event carries, against the documented hardware cap.

    The cap is read out of docs/README.md, so it is blank for a collection the docs leave
    silent, CICADA among them.
    """
    rows = [
        [
            f"`{name}`",
            *[
                fmt(obj["multiplicity"]["stats"].get(key))
                for key in ("mean", "std", "min", "max")
            ],
            fmt(obj["multiplicity"]["stats"].get("quantiles", {}).get("0.99")),
            _percent(1 - obj["multiplicity"]["stats"].get("zero_fraction", 0)),
            fmt(obj["capacity"]),
        ]
        for name, obj in sorted(summary["objects"].items())
    ]
    header = [
        "Object",
        "Mean",
        "Std",
        "Min",
        "Max",
        "p99",
        "Events with >=1",
        "Documented cap",
    ]

    return "## Object multiplicities\n\n" + markdown_table(header, rows)


def section_event_coverage(summary: dict) -> str:
    """Which runs, luminosity sections and beam conditions the data spans.

    `LS gaps` counts the sections missing between the first and last one seen in a run,
    since nothing in the parquet says where the run itself began or ended.
    """
    coverage = summary["event_coverage"]
    if not coverage:
        return "## Event coverage\n\n_No `event_info` object in this data set._"
    rows = [
        [
            f"`{run}`",
            f"{entry['events']:,}",
            entry["first"],
            entry["last"],
            f"{entry['present']:,}",
            f"{entry['missing']:,}",
        ]
        for run, entry in sorted(coverage["lumi_sections"].items())
    ]
    header = ["Run", "Events", "First LS", "Last LS", "LS with events", "LS gaps"]

    return "\n\n".join(
        ["## Event coverage", markdown_table(header, rows), _beam_lines(coverage)]
    )


def section_trigger(summary: dict) -> str:
    """What the level 1 menu did, seed by seed, ranked by how often each fired."""
    trigger = summary["trigger"]
    if not trigger:
        return "## Trigger content\n\n_No `seeds` object in this data set._"
    rows = [
        [
            index + 1,
            f"`{seed['name']}`",
            f"{seed['fired']:,}",
            _percent(seed["fraction"]),
            _percent(_of_accepts(seed["fired"], trigger)),
        ]
        for index, seed in enumerate(trigger["seeds"])
    ]
    header = [
        "Rank",
        "Seed",
        "Events fired",
        "Fraction of events",
        "Fraction of L1 accepts",
    ]

    return "\n\n".join(
        ["## Trigger content", _trigger_lines(trigger), markdown_table(header, rows)]
    )


def section_validation(summary: dict) -> str:
    """The Technical Validation section: what was checked, and what it found."""
    rows = [
        [f"**{check['status']}**", check["check"], check["detail"]]
        for check in summary["validation"]
    ]
    saturating = _saturating(summary)
    note = (
        "Saturation is reported, not cut on: these are hardware counter ceilings, so what "
        "fraction of entries sits at the all-ones code is a property of the data that "
        "downstream selections should be justified against."
    )
    table = (
        markdown_table(["Feature", "At the all-ones code"], saturating)
        if saturating
        else "No column has a single entry at its all-ones code."
    )

    return "\n\n".join(
        [
            "## Technical validation",
            markdown_table(["Status", "Check", "Detail"], rows),
            note,
            table,
        ]
    )


def section_figures(summary: dict) -> str:
    """What the data looks like.

    figures.py stores the paths relative to the directory the report sits in, so the
    Markdown links resolve.
    """
    figures = summary.get("figures", [])
    blocks = ["## Figures"] + [
        f"**{figure['caption']}**\n\n![{figure['caption']}]({figure['path']})"
        for figure in figures
    ]

    return "\n\n".join(blocks) if figures else "## Figures\n\n_None drawn._"


def section_usage(summary: dict) -> str:
    """How to read the data back, and what produced this report."""
    generated = summary.get("generated", {})
    versions = ", ".join(
        f"{name} {value}"
        for name, value in sorted(generated.get("packages", {}).items())
    )

    return "\n".join(
        [
            "## Reading the data",
            "",
            "```python",
            "from adl1t_datamaker.loader import Parquet2Awkward",
            "",
            f"data = Parquet2Awkward({summary['path']!r})",
            "jets = data['jets']            # everything at once",
            "for batch in data('jets'):     # or one batch at a time",
            "    ...",
            "```",
            "",
            "Values are the trigger's own integer hardware codes; nothing is scaled. The "
            "schema tables above give the factor and unit for each column.",
            "",
            "## Reproducibility",
            "",
            f"- **Generated**: {generated.get('at', '-')}",
            f"- **Commit**: `{generated.get('commit', '-')}`",
            f"- **Python**: {generated.get('python', '-')}",
            f"- **Libraries**: {versions or '-'}",
            "",
            "Every number above is exact, not sampled: the summary counts how often each "
            "value occurs and derives the statistics from those counts. Standard deviations "
            "are population (`ddof=0`) and quantiles use the `inverted_cdf` convention. "
            "Columns marked as not exact are too widely spread to enumerate, so only their "
            "count, extremes and mean are given.",
        ]
    )


def comparison_reproducibility(comparison: dict) -> str:
    """Which commit and interpreter produced this comparison."""
    generated = comparison.get("generated", {})

    return "\n".join(
        [
            "## Reproducibility",
            "",
            f"- **Generated**: {generated.get('at', '-')}",
            f"- **Commit**: `{generated.get('commit', '-')}`",
            f"- **Python**: {generated.get('python', '-')}",
        ]
    )


SECTIONS = (
    section_provenance,
    section_inventory,
    section_schema,
    section_multiplicities,
    section_event_coverage,
    section_trigger,
    section_validation,
    section_figures,
    section_usage,
)

CAMPAIGN_SECTIONS = (
    campaign_overview,
    campaign_consistency,
    section_figures,
    campaign_reproducibility,
)

COMPARISON_SECTIONS = (
    comparison_totals,
    comparison_schema,
    comparison_features,
    comparison_seeds,
    section_figures,
    comparison_reproducibility,
)


def _schema_header() -> list[str]:
    return [
        "Feature",
        "Type",
        "Bits",
        "Entries",
        "Min",
        "Max",
        "Mean",
        "Std",
        "Median",
        "p1",
        "p99",
        "Distinct",
        "Zero",
        "Saturated",
        "Physical range",
    ]


def _schema_rows(name: str, obj: dict) -> list[list]:
    return [
        _schema_row(name, feature, entry)
        for feature, entry in sorted(obj["features"].items())
    ]


def _schema_row(name: str, feature: str, entry: dict) -> list:
    stats_, doc = entry["stats"], entry["doc"]
    quantiles = stats_.get("quantiles", {})

    return [
        f"`{feature}`",
        _dtype(entry),
        fmt(doc.get("bits")),
        f"{stats_['entries']:,}",
        fmt(stats_["min"]),
        fmt(stats_["max"]),
        fmt(stats_["mean"]),
        fmt(stats_.get("std")),
        fmt(quantiles.get("0.5")),
        fmt(quantiles.get("0.01")),
        fmt(quantiles.get("0.99")),
        fmt(stats_.get("distinct")),
        _percent(stats_.get("zero_fraction")),
        _percent(stats_.get("saturated_fraction")),
        _physical(entry),
    ]


def _dtype(entry: dict) -> str:
    """The `Type` cell: how the statistics were made, not the stored parquet type."""
    return "exact" if entry["stats"]["exact"] else "counters"


def _physical(entry: dict) -> str:
    """The measured range converted to GeV, radians or pseudorapidity.

    `scale` is the (factor, unit label) pair schema.unit_scale gives, so the stored
    hardware code times the factor is the physical quantity. A column carrying no
    physical unit, such as a quality flag or an event identifier, gives `-`, as does one
    with nothing measured in it.
    """
    scale = entry.get("scale")
    stats_ = entry["stats"]
    if not scale or stats_["min"] is None:
        return "-"

    return (
        f"{stats_['min'] * scale[0]:.3g} .. {stats_['max'] * scale[0]:.3g} {scale[1]}"
    )


def _units_note() -> str:
    return (
        "`Bits` and the documented ranges come from `docs/README.md`, which specifies "
        "what the converter stores. `Saturated` is the fraction of entries sitting at "
        "the all-ones code of an unsigned field, so it is blank for signed and angular "
        "quantities where that pattern is an ordinary value. Columns whose type reads "
        "`counters` hold identifiers too widely spread to enumerate, so they carry no "
        "quantiles."
    )


def _provenance_value(value) -> str:
    """One config value as a table cell; a list becomes `<br>`-separated lines in it."""
    if isinstance(value, (list, tuple)):
        return "<br>".join(f"`{item}`" for item in value) or "-"
    if isinstance(value, bool):
        return "yes" if value else "no"

    return "-" if value in (None, "") else f"`{value}`"


def _shard_table(summary: dict) -> str:
    """The per-shard listing, or a pointer to summary.json when it grows too long.

    One object stands for all of them: the converter writes one parquet per object per
    input ntuple, naming it after the input stem, so the objects share their shard names.
    """
    shards = max(entry["shards"] for entry in summary["inventory"].values())
    if shards > MAX_SHARD_ROWS:
        return (
            f"Each object is sharded into up to {shards:,} parquet files, one per input "
            "ntuple. The full per-shard listing, with row counts, sizes and checksums, "
            "is in `summary.json` under `inventory`."
        )
    name = sorted(summary["inventory"])[0]
    rows = [
        [
            f"`{shard['name']}`",
            f"{shard['rows']:,}",
            f"{shard['bytes']:,}",
            f"`{shard.get('sha256', '-')[:16]}`",
        ]
        for shard in summary["inventory"][name]["files"]
    ]

    return f"Shards of `{name}`:\n\n" + markdown_table(
        ["Shard", "Rows", "Bytes", "sha256 (first 16)"], rows
    )


def _beam_lines(coverage: dict) -> str:
    pileup, clock = coverage.get("pileup") or {}, coverage.get("wall_clock")
    lines = [
        f"- **Runs**: {', '.join(str(run) for run in coverage['runs']) or '-'}",
        f"- **Recorded**: {_wall_clock(clock)}",
        f"- **Orbit range**: {_extent(coverage.get('orbit'))}",
        f"- **Bunch crossings**: {_extent(coverage.get('bx'))}",
    ]
    if pileup:
        lines.append(
            f"- **Pileup**: mean {fmt(pileup.get('mean'))}, "
            f"range {fmt(pileup.get('min'))} to {fmt(pileup.get('max'))}, "
            f"{_percent(coverage.get('zero_pileup_fraction'))} of events at zero"
        )
    lines.append(
        f"- **Duplicate identifiers**: {fmt(coverage.get('duplicate_identifiers'))}"
    )

    return "\n".join(lines)


def _trigger_lines(trigger: dict) -> str:
    accepted, events = trigger.get("l1bit_accepted"), trigger.get("events", 0)
    multiplicity = trigger["multiplicity"]["stats"]

    return "\n".join(
        [
            f"- **Unprescaled seeds stored**: {trigger['n_seeds']:,}",
            f"- **Prescale menu**: `{trigger.get('menu') or 'not identified'}` "
            f"({fmt(trigger.get('menu_mismatch'))} names differing)",
            f"- **L1 accept**: {_percent(accepted / events if events and accepted else 0)} "
            f"({fmt(accepted)} of {fmt(events)} events)",
            f"- **Seeds firing per event**: mean {fmt(multiplicity.get('mean'))}, "
            f"max {fmt(multiplicity.get('max'))}, "
            f"{_percent(multiplicity.get('zero_fraction'))} of events fire none",
            f"- **Seeds that never fired**: {len(trigger.get('never_fired', []))} of "
            f"{trigger['n_seeds']}",
            f"- **Seeds that fired on every event**: {len(trigger.get('always_fired', []))}",
            "",
            "`L1bit` is a logical OR of seeds, synthesised at conversion time, and is "
            "excluded from the counts above. The full menu is listed; seeds that never "
            "fired sit at the bottom.",
        ]
    )


def _saturating(summary: dict) -> list[list]:
    """Only the features that saturate somewhere: a table of zeroes says nothing."""
    return sorted(
        [f"`{name}.{feature}`", _percent(entry["stats"]["saturated_fraction"])]
        for name, obj in summary["objects"].items()
        for feature, entry in obj["features"].items()
        if entry["stats"].get("saturated_fraction")
    )


def _of_accepts(fired: int, trigger: dict) -> float | None:
    accepted = trigger.get("l1bit_accepted")

    return fired / accepted if accepted else None


def _wall_clock(clock: dict | None) -> str:
    """When the data was taken, which simulation does not record."""
    if not clock:
        return "not recorded (simulation leaves the time field unset)"

    return f"{clock['start']} to {clock['end']} ({clock['seconds']:,} s of wall clock)"


def _extent(extent: dict | None) -> str:
    if not extent:
        return "-"

    return f"{fmt(extent['min'])} to {fmt(extent['max'])} (span {fmt(extent['span'])})"


def _percent(fraction) -> str:
    """Four decimals, so a seed firing on one event in a million still reads non-zero."""
    return "-" if fraction is None else f"{fraction:.4%}"


def _human_size(size: float) -> str:
    """Powers of 1000, matching how a data descriptor quotes file sizes."""
    for unit in ("B", "kB", "MB", "GB"):
        if size < 1000 or unit == "GB":
            return f"{size} B" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1000

    return f"{size:.1f} GB"
