"""The technical validation checks, driven from hand-built summary dictionaries.

Every check reads only the summary, so each one can be given exactly the shape it is
meant to catch without converting anything.
"""

import pytest

from adl1t_datamaker import validation


def feature(counts: dict, doc: dict | None = None, **stats) -> dict:
    """One feature entry of a summary, shaped as measure.py writes it.

    :param counts: Value to the number of entries holding it, from which the entry
        count, the distinct count and the extremes follow.
    :param doc: The docs/README.md metadata, ``bits`` and ``range``, that the bit width
        check reads. Empty stands for an undocumented column.
    :param stats: Merged over the derived statistics, so a check reading a field this
        helper does not compute (``zero_fraction``, ``nonfinite``) can be handed one.
    """
    values = sorted(counts)

    return {
        "doc": doc or {},
        "scale": None,
        "stats": {"entries": sum(counts.values()), "exact": True,
                  "distinct": len(counts), "min": min(values, default=None),
                  "max": max(values, default=None), "nonfinite": 0, **stats},
        "counts": {"values": values, "counts": [counts[value] for value in values]},
    }


def summary(objects: dict, **extra) -> dict:
    """A summary holding every section the checks read, all of it clean.

    :param objects: Object name to its features, each built by `feature`. The inventory
        follows from it at ten rows in one shard per object, so the file-level checks
        pass unless a test rewrites them.
    :param extra: Top-level sections replacing the clean defaults, among them
        ``provenance``, ``event_coverage`` and ``trigger``.
    """
    inventory = {
        name: {"rows": 10, "shards": 1, "bytes": 100, "row_groups": 1, "dtypes": {},
               "compression": ["SNAPPY"], "files": [{"name": "a.parquet", "rows": 10}]}
        for name in objects
    }
    base = {
        "objects": {
            name: {"features": feats, "capacity": None,
                   "multiplicity": {"stats": {"min": 1, "max": 1}}, "occupancy": []}
            for name, feats in objects.items()
        },
        "inventory": inventory,
        "provenance": {},
        "event_coverage": {"duplicate_identifiers": 0, "zero_pileup_fraction": 0.0},
        "trigger": {},
    }

    return base | extra


def status(result: list, name: str) -> str:
    return next(entry["status"] for entry in result if entry["check"] == name)


def test_identical_columns_are_reported():
    """The shape of a real bug in the converter.

    ET.ETTEM was read at sum type 1, which is HT's, so the two columns came out
    identical in every data set produced before the fix.
    """
    shared = {5: 3, 9: 7}
    checks = validation.run_checks(summary({
        "ET": {"Et": feature({1: 10}), "ETTEM": feature(shared)},
        "HT": {"Et": feature(shared)},
    }))
    detail = next(e["detail"] for e in checks if "same distribution" in e["check"])

    assert status(checks, "no two columns hold the same distribution") == "WARN"
    assert "`ET.ETTEM` == `HT.Et`" in detail


def test_constant_columns_do_not_count_as_duplicates():
    """Several single-valued columns matching each other says nothing worth saying."""
    checks = validation.run_checks(summary({
        "ET": {"Et": feature({0: 10})},
        "HT": {"Et": feature({0: 10})},
    }))

    assert status(checks, "no two columns hold the same distribution") == "PASS"


def test_seeds_are_left_out_of_the_column_checks():
    """Hundreds of never-firing seeds would drown every column-level check."""
    documented = {"bits": 11, "range": "0..1024 GeV"}
    checks = validation.run_checks(summary({
        "seeds": {"L1_A": feature({0: 10}, zero_fraction=1.0),
                  "L1_B": feature({0: 10}, zero_fraction=1.0)},
        "jets": {"jetIEt": feature({3: 10}, documented, zero_fraction=0.0)},
    }))

    assert status(checks, "no all-zero columns") == "PASS"
    assert status(checks, "every stored column is documented") == "PASS"


def test_an_all_zero_column_fails():
    checks = validation.run_checks(summary({
        "jets": {"jetIEt": feature({0: 10}, zero_fraction=1.0, distinct=2)},
    }))

    assert status(checks, "no all-zero columns") == "FAIL"


def test_pileup_is_owned_by_its_own_check_not_the_all_zero_one():
    """Zero pileup outside stable beams is genuine, so it must never be a failure."""
    built = summary(
        {"event_info": {"nPV_True": feature({0.0: 10}, zero_fraction=1.0)}},
        event_coverage={"duplicate_identifiers": 0, "zero_pileup_fraction": 1.0},
    )
    checks = validation.run_checks(built)

    assert status(checks, "no all-zero columns") == "PASS"
    assert status(checks, "pileup is populated") == "WARN"


def test_pileup_check_is_skipped_for_simulation():
    built = summary({"jets": {"jetIEt": feature({3: 10})}}, provenance={"mc": True})

    assert status(validation.run_checks(built), "pileup is populated") == "SKIP"


def test_duplicate_events_are_a_warning_for_simulation_and_a_failure_for_data():
    """A repeated identifier means a double conversion in data, but not in simulation.

    Simulation reuses event numbers across samples, so the same check has to carry a
    different severity depending on the mc flag.
    """
    objects = {"jets": {"jetIEt": feature({3: 10})}}
    coverage = {"duplicate_identifiers": 4, "zero_pileup_fraction": 0.0}
    as_data = summary(objects, event_coverage=coverage)
    as_mc = summary(objects, event_coverage=coverage, provenance={"mc": True})

    assert status(validation.run_checks(as_data), "no duplicate event identifiers") == "FAIL"
    assert status(validation.run_checks(as_mc), "no duplicate event identifiers") == "WARN"


def test_values_wider_than_the_documented_field_fail():
    documented = {"bits": 9, "range": "0..256 GeV"}
    checks = validation.run_checks(summary({
        "muons": {"muonIEt": feature({600: 10}, documented, max=600)},
    }))

    assert status(checks, "values fit their documented bit width") == "FAIL"


def test_a_multiplicity_above_the_documented_cap_fails():
    built = summary({"muons": {"muonIEt": feature({3: 10})}})
    built["objects"]["muons"]["capacity"] = 8
    built["objects"]["muons"]["multiplicity"] = {"stats": {"min": 0, "max": 9}}

    assert status(validation.run_checks(built), "multiplicities respect the documented cap") == "FAIL"


def test_a_singleton_object_with_two_entries_fails():
    built = summary({"ET": {"Et": feature({3: 10})}})
    built["objects"]["ET"]["multiplicity"] = {"stats": {"min": 0, "max": 2}}

    assert status(validation.run_checks(built), "per-event objects hold exactly one entry") == "FAIL"


def test_long_offender_lists_are_truncated():
    """A check whose detail runs to hundreds of names makes the table unreadable."""
    names = {f"f{index}": feature({0: 10}, zero_fraction=1.0, distinct=2) for index in range(40)}
    checks = validation.run_checks(summary({"jets": names}))
    detail = next(e["detail"] for e in checks if e["check"] == "no all-zero columns")

    assert "and 32 more" in detail


@pytest.mark.parametrize("mismatch,expected", [(0, "PASS"), (3, "FAIL")])
def test_seed_columns_are_checked_against_the_identified_menu(mismatch, expected):
    built = summary(
        {"jets": {"jetIEt": feature({3: 10})}},
        trigger={"menu": "L1Menu_Collisions2025_v1_3_0.csv", "menu_mismatch": mismatch,
                 "n_seeds": 190},
    )

    assert status(validation.run_checks(built), "seed columns match the menu") == expected


def test_an_unidentified_menu_skips_rather_than_fails():
    built = summary({"jets": {"jetIEt": feature({3: 10})}},
                    trigger={"menu": None, "menu_mismatch": None, "n_seeds": 0})

    assert status(validation.run_checks(built), "seed columns match the menu") == "SKIP"
