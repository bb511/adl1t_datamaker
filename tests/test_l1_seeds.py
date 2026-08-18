"""Prescale menu parsing and seed construction."""

import numpy as np
import pytest

from adl1t_datamaker.components import l1_seeds

# Distinct kept algorithms in each checked-in menu (unprescaled, minus the anomaly
# seeds of ANOMALY_SEED_PREFIXES), and the header of the column that decides the
# prescale. Pinning these makes any change to PRESCALE_COLUMN, to the exclusion, or to
# a menu file a visible test failure rather than a silent shift in the seeds schema.
MENUS = {
    "L1Menu_Collisions2023_v1_1_0.csv": ("2p1E34", 168),
    "L1Menu_Collisions2023_v1_2_0.csv": ("2p1E34", 175),
    "L1Menu_Collisions2024_v1_1_0.csv": ("2p0E34", 161),
    "L1Menu_Collisions2024_v1_2_1.csv": ("2p0E34", 162),
    "L1Menu_Collisions2024_v1_3_0_last.csv": ("2p0E34+ZeroBias+HLTPhysics", 158),
    # 179 kept rows but only 176 distinct names; see test_duplicate_seed_names below.
    "L1Menu_Collisions2025_v1_1_1.csv": ("1p95E34", 176),
    "L1Menu_Collisions2025_v1_1_1_original.csv": ("1p95E34", 179),
    "L1Menu_Collisions2025_v1_3_0.csv": ("1p95E34", 178),
    "Prescale_2022_v0_1_1.csv": ("1.5E+34", 150),
}


@pytest.mark.parametrize("menu,expected", MENUS.items(), ids=list(MENUS))
def test_menu_reading_is_pinned(menus, menu, expected):
    """The prescale column sits where PRESCALE_COLUMN points, and the kept set holds.

    The names come from the menu alone, with no root file involved, which is what lets
    a summary report identify the menu behind an already converted data set. A count
    moving here means PRESCALE_COLUMN, the anomaly exclusion, or a menu file changed.
    """
    header, count = expected

    assert l1_seeds.prescale_column_header(menus / menu) == header
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


def test_anomaly_trigger_seeds_are_excluded(tmp_path):
    """AXO and CICADA seeds are dropped even where the menu leaves them unprescaled."""
    menu = tmp_path / "menu.csv"
    menu.write_text(
        "Index,Name,Emergency,a,b,c,2p0E34,extra\n"
        "0,L1_Physics,,,,,1,x\n"
        "1,L1_AXO_Tight,,,,,1,x\n"
        "2,L1_CICADA_Medium,,,,,1,x\n"
    )
    assert l1_seeds.unprescaled_names(menu) == ["L1_Physics"]


def test_duplicate_seed_names_collapse(menus):
    """L1Menu_Collisions2025_v1_1_1.csv repeats three tau seed names, deliberately.

    Rows 276-278 were edited to duplicate rows 273-275, replacing the Jet70 and Iso23
    variants that _original still carries. filter_algo_map returns a dict, so those
    rows collapse and the menu yields 176 kept seeds rather than 179. This is intended:
    do not "restore" the names from _original without asking.
    """
    edited = menus / "L1Menu_Collisions2025_v1_1_1.csv"
    original = menus / "L1Menu_Collisions2025_v1_1_1_original.csv"

    assert len(l1_seeds.filter_algo_map(edited, _all_names_map(edited))) == 176
    assert len(l1_seeds.filter_algo_map(original, _all_names_map(original))) == 179


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
