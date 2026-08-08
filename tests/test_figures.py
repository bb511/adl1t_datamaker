"""Binning, which is where a spectrum silently stops meaning what it says.

Bad edges raise nothing. They produce a figure that looks reasonable and misrepresents
the data, so the cases below are the ones that would slip past a reader.
"""

import numpy as np
import pytest

from adl1t_datamaker import figures


@pytest.mark.parametrize("values", [
    np.array([0, 1, 2, 3]),
    np.array([-1, 0, 1]),
    np.array([7]),
    np.array([]),
    np.arange(8192),                       # tower_count, wider than MAX_BINS
    np.array([1716486000 << 32]),          # the packed time field, out at 7e18
    np.array([1.5, 2.25, 3.125]),
    np.array([44.5, 44.5]),
])
def test_edges_are_always_usable(values):
    """np.histogram needs at least two finite, increasing edges, whatever it is given."""
    edges = figures.bin_edges(values.astype(np.float64))

    assert edges.size >= 2
    assert np.all(np.isfinite(edges))
    assert np.all(np.diff(edges) > 0)


def test_small_integers_get_one_bin_each():
    """A four-code quality flag needs one bin per code, each code at a bin centre."""
    edges = figures.bin_edges(np.arange(4, dtype=np.float64))

    assert list(edges) == [-0.5, 0.5, 1.5, 2.5, 3.5]


def test_wide_integer_ranges_are_coarsened_by_a_whole_factor():
    """Steps stay integral, so every bin still holds a whole number of hardware codes."""
    edges = figures.bin_edges(np.arange(8192, dtype=np.float64))

    assert edges.size <= figures.MAX_BINS + 1
    assert float(np.diff(edges)[0]).is_integer()


def test_plotting_a_raw_array_writes_a_figure(tmp_path):
    """The one entry point taking an array: it counts before drawing, unlike the rest."""
    import awkward as ak

    figures.plot_feature_from_array(ak.Array([[1, 2], [3], []]), "jetIEt", tmp_path)

    assert (tmp_path / "jetIEt.png").is_file()


def test_every_value_lands_inside_the_edges():
    values = np.array([-30, -1, 0, 5, 8191], dtype=np.float64)
    edges = figures.bin_edges(values)

    assert edges[0] < values.min() and edges[-1] > values.max()
    assert np.histogram(values, bins=edges)[0].sum() == values.size
