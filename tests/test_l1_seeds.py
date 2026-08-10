"""Prescale menu parsing and seed construction."""

import numpy as np
import pytest

from adl1t_datamaker.components import l1_seeds

# Distinct unprescaled algorithms in each checked-in menu, and the header of the
# column that decides it. Pinning these makes any change to PRESCALE_COLUMN, or to a
# menu file, a visible test failure rather than a silent shift in the seeds schema.
MENUS = {
    "L1Menu_Collisions2023_v1_1_0.csv": ("2p1E34", 168),
    "L1Menu_Collisions2023_v1_2_0.csv": ("2p1E34", 175),
    "L1Menu_Collisions2024_v1_1_0.csv": ("2p0E34", 161),
    "L1Menu_Collisions2024_v1_2_1.csv": ("2p0E34", 170),
    "L1Menu_Collisions2024_v1_3_0_last.csv": ("2p0E34+ZeroBias+HLTPhysics", 164),
    # 190 rows but only 187 distinct names; see test_duplicate_seed_names below.
    "L1Menu_Collisions2025_v1_1_1.csv": ("1p95E34", 187),
    "L1Menu_Collisions2025_v1_1_1_original.csv": ("1p95E34", 190),
    "L1Menu_Collisions2025_v1_3_0.csv": ("1p95E34", 190),
    "Prescale_2022_v0_1_1.csv": ("1.5E+34", 150),
}


@pytest.mark.parametrize("menu,expected", MENUS.items(), ids=list(MENUS))
def test_prescale_column_header(menus, menu, expected):
    header, _ = expected
    assert l1_seeds.prescale_column_header(menus / menu) == header


@pytest.mark.parametrize("menu,expected", MENUS.items(), ids=list(MENUS))
def test_unprescaled_count(menus, menu, expected):
    _, count = expected
    # A map covering every name in the menu, so what is counted is the prescale column
    # alone and not the overlap with some trigger tree.
    algo_map = _all_names_map(menus / menu)
    assert len(l1_seeds.filter_algo_map(menus / menu, algo_map)) == count


@pytest.mark.parametrize("menu,expected", MENUS.items(), ids=list(MENUS))
def test_unprescaled_names_needs_no_root_file(menus, menu, expected):
    """The seed set is derivable from the menu alone, with no root file involved.

    That is what lets a summary report name the menu behind an already converted data
    set, by matching its seed columns against every menu in scripts/L1Menus.
    """
    _, count = expected

    assert len(set(l1_seeds.unprescaled_names(menus / menu))) == count


def test_every_menu_has_a_distinct_unprescaled_set(menus):
    """Menu identification from seed columns is only unambiguous if this holds."""
    sets = [
        frozenset(l1_seeds.unprescaled_names(menu))
        for menu in sorted(menus.glob("*.csv"))
    ]

    assert len(set(sets)) == len(sets), "two menus select the same seeds"


def _all_names_map(path):
    """Every seed a menu names, mapped to a stand-in for its decision bit number.

    Production reads that map off the trigger tree; here the row index does instead, so
    filter_algo_map cannot raise KeyError on a name the tree happens to lack. Rows of
    one field or fewer are the blank lines, which name nothing.
    """
    import csv

    with open(path, newline="") as f:
        rows = csv.reader(f)
        next(rows)
        return {r[l1_seeds.NAME_COLUMN]: i for i, r in enumerate(rows) if len(r) > 1}


def test_header_row_is_never_selected(menus):
    """The header must be discarded explicitly, not by luck of its column value."""
    menu = menus / "L1Menu_Collisions2025_v1_3_0.csv"
    assert "Name" not in l1_seeds.filter_algo_map(menu, _all_names_map(menu))


def test_short_and_blank_lines_are_tolerated(tmp_path):
    """A truncated or blank row must be skipped, not raise IndexError."""
    menu = tmp_path / "menu.csv"
    menu.write_text(
        "Index,Name,Emergency,a,b,c,2p0E34,extra\n"
        "0,L1_Good,,,,,1,x\n"
        "\n"
        "1,L1_Truncated\n"
        "2,L1_Prescaled,,,,,63000,x\n"
    )
    assert l1_seeds.filter_algo_map(menu, {"L1_Good": 7}) == {"L1_Good": 7}


def test_get_level1_seeds_adds_combined_l1bit():
    algo_map = {"L1_A": 0, "L1_B": 1}
    # (events, algorithms), the column index being the decision bit algo_map points at.
    bits = np.array([[1, 0], [0, 0], [0, 1]])

    seeds = l1_seeds.get_level1_seeds(algo_map, bits)

    assert set(seeds) == {"L1_A", "L1_B", "L1bit"}
    assert seeds["L1_A"].dtype == bool
    np.testing.assert_array_equal(seeds["L1bit"], [True, False, True])


def test_duplicate_seed_names_collapse(menus):
    """L1Menu_Collisions2025_v1_1_1.csv repeats three tau seed names, deliberately.

    Rows 276-278 were edited to duplicate rows 273-275, replacing the Jet70 and Iso23
    variants that _original still carries. filter_algo_map returns a dict, so those
    rows collapse and the menu yields 187 seeds rather than 190. This is intended:
    do not "restore" the names from _original without asking.
    """
    edited = menus / "L1Menu_Collisions2025_v1_1_1.csv"
    original = menus / "L1Menu_Collisions2025_v1_1_1_original.csv"

    assert len(l1_seeds.filter_algo_map(edited, _all_names_map(edited))) == 187
    assert len(l1_seeds.filter_algo_map(original, _all_names_map(original))) == 190


def test_menu_selecting_nothing_names_the_column(tmp_path):
    """A menu whose layout does not match must say so, not fail deep in awkward.

    An empty selection used to reach get_level1_seeds, where np.logical_or.reduce([])
    gives a scalar L1bit, and only blew up later in ak.Array with a message about
    scalar promotion that says nothing about the menu.
    """
    menu = tmp_path / "wrong_layout.csv"
    menu.write_text(
        "Index,Name,Emergency,a,b,c,9p9E34,extra\n" "0,L1_Something,,,,,63000,x\n"
    )

    with pytest.raises(ValueError, match="9p9E34"):
        l1_seeds.filter_algo_map(menu, {"L1_Something": 3})


def test_get_level1_seeds_with_empty_algo_map_yields_a_scalar():
    """Pins a sharp edge: no algorithms means L1bit is a scalar, not per-event.

    np.logical_or.reduce([]) is False rather than an error, so an empty menu produces
    a seeds record whose L1bit does not line up with the event axis.
    """
    seeds = l1_seeds.get_level1_seeds({}, np.zeros((3, 2)))

    assert set(seeds) == {"L1bit"}
    assert seeds["L1bit"].shape == ()  # not (3,), which is what events would need
