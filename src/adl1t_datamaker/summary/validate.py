# Technical validation of a converted data set.
#
# Every check reads the assembled summary dictionary and nothing else, so this section
# can be recomputed from a summary.json without touching the parquet again.
#
# PASS means the invariant holds, FAIL means the data is wrong, WARN means a finding
# worth a sentence in the data descriptor rather than a fix, and SKIP means the check
# could not be made. Nothing here raises: a report that refuses to be written is no use
# when the question being asked is what is wrong with the data.

from adl1t_datamaker import schema

PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"

# The converter writes one entry per event for these objects, so multiplicity must be 1.
SINGLETONS = ("seeds", "event_info", "ET", "HT", "MET", "MHT", "FET", "FHT")

# The seeds are one boolean column per trigger algorithm, and there are hundreds of them:
# a seed that never fires is normal and docs/README.md names no individual seed, so the
# column-level checks would report only noise. The trigger section covers the seeds.
COLUMN_CHECK_SKIP = ("seeds",)

# check_pileup_present judges pileup instead: a missing (run, lumi) leaves nPV_True at
# zero rather than unset, so the all-zero and constant column checks would misread it.
OWNED_ELSEWHERE = ("event_info.nPV_True",)

# How many offending names a check spells out before it counts the rest instead.
MAX_LISTED = 8


def run_checks(summary: dict) -> list[dict]:
    """Every check, in a fixed order, as {check, status, detail} records."""
    return [check(summary) for check in CHECKS]


def check_row_counts_match(summary: dict) -> dict:
    """Row counts that disagree across objects misalign the data set.

    Row i of every object is the same event, so counts that disagree mean no column can
    be read against another, hence a failure.
    """
    rows = {name: entry["rows"] for name, entry in summary["inventory"].items()}
    odd = {name: count for name, count in rows.items() if count != max(rows.values())}
    detail = f"all {len(rows)} objects hold {max(rows.values())} rows"

    return _record("rows match across objects", odd, FAIL, detail, f"disagree: {odd}")


def check_shard_names_match(summary: dict) -> dict:
    """Every object must be written from the same set of input files.

    An object written from a different set holds different events, so the rows stop
    lining up even where the totals happen to agree.
    """
    names = {
        name: {f["name"] for f in e["files"]}
        for name, e in summary["inventory"].items()
    }
    # The fullest set is the reference, so an object missing a shard is the odd one out.
    reference = max(names.values(), key=len)
    odd = {
        name: len(reference ^ shards)
        for name, shards in names.items()
        if shards != reference
    }

    return _record(
        "shard names match across objects",
        odd,
        FAIL,
        f"all {len(names)} objects share the same {len(reference)} shard names",
        f"objects with a differing shard set: {odd}",
    )


def check_no_empty_shards(summary: dict) -> dict:
    """An empty shard warns rather than fails.

    A zero-row shard comes from an input file that held no events, which is odd but not
    itself wrong.
    """
    empty = {
        f"{name}/{shard['name']}": 0
        for name, entry in summary["inventory"].items()
        for shard in entry["files"]
        if shard["rows"] == 0
    }

    return _record(
        "no empty shards",
        empty,
        WARN,
        "every shard holds at least one row",
        f"{len(empty)} empty shards, e.g. {_listed(sorted(empty))}",
    )


def check_singletons_hold_one_entry(summary: dict) -> dict:
    """The per-event objects must carry one entry each, never zero and never two.

    seeds and event_info go through ak.singletons and can be nothing else, so the check
    bites on the energy sums, which are selected by sumType at sumBx == 0: a zero means
    the sum was absent from an event, a two that a neighbouring bunch crossing survived
    the mask. Either way the column stops running one entry per event, hence a failure.
    """
    odd = {
        name: [obj["multiplicity"]["stats"]["min"], obj["multiplicity"]["stats"]["max"]]
        for name, obj in summary["objects"].items()
        if name in SINGLETONS and _multiplicity_range(obj) != (1, 1)
    }

    return _record(
        "per-event objects hold exactly one entry",
        odd,
        FAIL,
        "seeds, event_info and the six energy sums all hold one entry per event",
        f"objects with a multiplicity other than 1: {odd}",
    )


def check_no_duplicate_events(summary: dict) -> dict:
    """A repeated (run, lumi, event) means an input file was converted twice.

    In recorded data the triple is unique by construction, so a repeat can only come
    from the conversion, and the check fails.
    """
    duplicates = summary["event_coverage"].get("duplicate_identifiers")
    if duplicates is None:
        return _skip("no duplicate event identifiers", "identifiers too wide to pack")
    # Simulation reuses event numbers across samples, so a repeat need not be a fault.
    severity = WARN if summary["provenance"].get("mc") else FAIL

    return _record(
        "no duplicate event identifiers",
        duplicates,
        severity,
        "every (run, lumi, event) is unique",
        f"{duplicates} repeated identifiers",
    )


def check_pileup_present(summary: dict) -> dict:
    """Pileup defaults to zero when a (run, lumi) is missing from the brilcalc files.

    Zero pileup outside stable beams is genuine, so a zero can never be a hard failure.
    A large zero fraction in recorded data is nonetheless how a broken mapping shows up.
    """
    if summary["provenance"].get("mc"):
        return _skip("pileup is populated", "simulation takes pileup from the ntuple")
    zero = summary["event_coverage"].get("zero_pileup_fraction")
    if zero is None:
        return _skip("pileup is populated", "no nPV_True column")

    # One per cent is a judgement: it tolerates the odd section outside stable beams,
    # where a mapping that missed a run or a whole file zeroes far more than that.
    return _record(
        "pileup is populated",
        zero > 0.01,
        WARN,
        f"{zero:.4%} of events have nPV_True == 0",
        f"{zero:.2%} of events have nPV_True == 0, check the brilcalc coverage",
    )


def check_seed_columns_match_menu(summary: dict) -> dict:
    """The stored seeds must be the unprescaled set of one menu in scripts/L1Menus.

    identify_menu names the closest menu and counts the names that differ, so a non-zero
    count means the report would credit the columns to a menu they did not come from:
    a mislabelled data set, hence a failure.
    """
    trigger = summary["trigger"]
    if not trigger.get("menu") or trigger.get("menu_mismatch") is None:
        return _skip("seed columns match the menu", "no menu could be identified")

    return _record(
        "seed columns match the menu",
        trigger["menu_mismatch"],
        FAIL,
        f"the {trigger['n_seeds']} seeds are the unprescaled set of {trigger['menu']}",
        f"{trigger['menu_mismatch']} seeds differ from {trigger['menu']}",
    )


def check_no_all_zero_columns(summary: dict) -> dict:
    """A column zero in every entry carries no information.

    For these hardware quantities an unfilled branch is the likeliest cause, hence a
    failure.
    """
    zeroed = _features_where(summary, lambda s: s.get("zero_fraction") == 1.0)

    return _record(
        "no all-zero columns",
        zeroed,
        FAIL,
        "no column is zero in every entry",
        f"columns that are always zero: {_listed(zeroed)}",
    )


def check_constant_columns(summary: dict) -> dict:
    """A column holding one value warns rather than fails.

    The run column is legitimately constant in a data set taken from a single run.
    """
    constant = _features_where(summary, lambda s: s.get("distinct") == 1)

    return _record(
        "columns are not constant",
        constant,
        WARN,
        "no column holds a single value",
        f"columns holding one value throughout: {_listed(constant)}",
    )


def check_values_fit_documented_bits(summary: dict) -> dict:
    """A value wider than its documented field is a failure.

    It means docs/README.md and the converter have drifted apart, so one of the two is
    wrong and the published widths cannot be trusted.
    """
    over = _features_where(summary, _exceeds_documented_width)

    return _record(
        "values fit their documented bit width",
        over,
        FAIL,
        "every value fits the width docs/README.md documents",
        f"values wider than documented: {_listed(over)}",
    )


def check_multiplicity_within_capacity(summary: dict) -> dict:
    """A multiplicity above the documented cap is a failure.

    The global trigger emits at most a fixed number of objects per collection, so a
    multiplicity above the cap docs/README.md states means the docs or the conversion is
    wrong.
    """
    over = {
        name: obj["multiplicity"]["stats"]["max"]
        for name, obj in summary["objects"].items()
        if obj.get("capacity") and obj["multiplicity"]["stats"]["max"] > obj["capacity"]
    }

    return _record(
        "multiplicities respect the documented cap",
        over,
        FAIL,
        "no event holds more objects than the trigger can emit",
        f"collections exceeding their cap: {over}",
    )


def check_columns_are_documented(summary: dict) -> dict:
    """A stored column absent from docs/README.md leaves data undescribed.

    The gap is in the documentation rather than in the data, so it warns.
    """
    undocumented = _features_where(summary, lambda s: s.get("undocumented"))

    return _record(
        "every stored column is documented",
        undocumented,
        WARN,
        "docs/README.md documents every stored column",
        f"columns missing from docs/README.md: {_listed(undocumented)}",
    )


def check_no_duplicate_columns(summary: dict) -> dict:
    """Two columns with identical distributions usually means one is mislabelled.

    The filter on distinct values drops constants, which say nothing by matching one
    another, and with them the columns too spread out to count exactly, which keep no
    count map and would otherwise fingerprint alike. Identical distributions are strong
    evidence of a duplicated source rather than proof of one, so the check warns.
    """
    groups: dict = {}
    for column, entry in sorted(_columns(summary).items()):
        if entry["stats"].get("distinct", 0) > 1:
            groups.setdefault(_fingerprint(entry), []).append(column)
    clashes = sorted(group for group in groups.values() if len(group) > 1)

    return _record(
        "no two columns hold the same distribution",
        clashes,
        WARN,
        "every column has a distribution of its own",
        "columns with identical distributions: "
        + "; ".join(" == ".join(f"`{name}`" for name in group) for group in clashes),
    )


def check_no_nonfinite_values(summary: dict) -> dict:
    """NaN or infinity in a float column, which the accumulator counts and then drops.

    No quantity the trigger stores can be non-finite, so an entry that is means the
    conversion went wrong. Being dropped, such entries also leave the mean, the quantiles
    and the value counts describing the surviving entries alone, hence a failure.
    """
    dirty = _features_where(summary, lambda s: s.get("nonfinite", 0) > 0)

    return _record(
        "no non-finite values",
        dirty,
        FAIL,
        "no NaN or infinity in any column",
        f"columns holding NaN or infinity: {_listed(dirty)}",
    )


# The order the validation table prints in, which is not the definition order above.
CHECKS = (
    check_row_counts_match,
    check_shard_names_match,
    check_no_empty_shards,
    check_singletons_hold_one_entry,
    check_no_duplicate_events,
    check_pileup_present,
    check_seed_columns_match_menu,
    check_no_all_zero_columns,
    check_values_fit_documented_bits,
    check_multiplicity_within_capacity,
    check_columns_are_documented,
    check_no_nonfinite_values,
    check_no_duplicate_columns,
    check_constant_columns,
)


def _record(name: str, offence, severity: str, clean: str, dirty: str) -> dict:
    """One check result, as a {check, status, detail} record.

    :param offence: Whatever the check counted or collected. Falsy means the invariant
        held and the status is PASS.
    :param severity: The status carried when `offence` is truthy, WARN or FAIL.
    :param clean: The detail line for an invariant that held.
    :param dirty: The detail line for one that did not.
    """
    return {
        "check": name,
        "status": PASS if not offence else severity,
        "detail": clean if not offence else dirty,
    }


def _skip(name: str, why: str) -> dict:
    return {"check": name, "status": SKIP, "detail": why}


def _multiplicity_range(obj: dict) -> tuple:
    return obj["multiplicity"]["stats"]["min"], obj["multiplicity"]["stats"]["max"]


def _features_where(summary: dict, predicate) -> list[str]:
    """Every 'object.feature' whose statistics satisfy a predicate, sorted.

    :param predicate: Applied to the `_view` of a feature, so it sees the feature's
        statistics together with `doc` and `undocumented`.
    """
    return sorted(
        column for column, entry in _columns(summary).items() if predicate(_view(entry))
    )


def _columns(summary: dict) -> dict:
    """Every column the column-level checks apply to, keyed 'object.feature'."""
    return {
        f"{name}.{feature}": entry
        for name, obj in summary["objects"].items()
        for feature, entry in obj["features"].items()
        if name not in COLUMN_CHECK_SKIP and f"{name}.{feature}" not in OWNED_ELSEWHERE
    }


def _fingerprint(entry: dict) -> tuple:
    """A column's value counts as a hashable key, so identical distributions group."""
    counts = entry["counts"]

    return tuple(counts["values"]), tuple(counts["counts"])


def _listed(names: list) -> str:
    """Names, but never so many that the validation table stops being readable."""
    shown = ", ".join(f"`{name}`" for name in names[:MAX_LISTED])

    return (
        shown
        if len(names) <= MAX_LISTED
        else f"{shown} and {len(names) - MAX_LISTED} more"
    )


def _view(entry: dict) -> dict:
    """A feature's statistics with its documentation attached, for the predicates."""
    return entry["stats"] | {"doc": entry["doc"], "undocumented": not entry["doc"]}


def _exceeds_documented_width(entry: dict) -> bool:
    """Whether an observed value needs more bits than docs/README.md allows.

    Only a feature whose documented range starts at zero has an all-ones code to compare
    against, so the signed and angular ones go unchecked here.
    """
    limit = schema.saturation_code(entry["doc"] or {})

    return limit is not None and entry.get("max") is not None and entry["max"] > limit
