"""The exact-counting engine must agree with numpy on the fully expanded sample.

Every number in a report comes out of these counts, so the whole feature is only as
trustworthy as this file. Each entry of CASES is checked against numpy applied to the
same data, not against a hand-written expectation.
"""

import numpy as np
import pytest

from adl1t_datamaker import stats

# Every generator is seeded, so a failing case reproduces exactly from its name.
CASES = {
    "small_ints": np.random.default_rng(1).integers(0, 12, 5000),
    "negatives": np.random.default_rng(2).integers(-30, 30, 5000),
    "constant": np.full(1000, 7),
    "single_entry": np.array([42]),
    "bools": np.random.default_rng(3).random(5000) < 0.3,
    "floats": np.round(np.random.default_rng(4).normal(50, 8, 5000), 2).astype(np.float32),
}


def accumulate(data: np.ndarray, chunks: int = 7) -> stats.ValueCounts:
    """Feed an array through the accumulator in batches, as a pass over shards does.

    :param chunks: How many update calls the array is split across. More than one is
        what puts the merge between calls under test.
    """
    store = stats.ValueCounts()
    for chunk in np.array_split(data, chunks):
        store.update(chunk)

    return store


def reference(data: np.ndarray) -> np.ndarray:
    """The data as the accumulator sees it, with booleans counted as 0 and 1."""
    return data.astype(np.int8) if data.dtype.kind == "b" else data


@pytest.mark.parametrize("name", sorted(CASES))
def test_extremes_and_moments_match_numpy(name):
    summary = stats.summarise(accumulate(CASES[name]))
    expected = reference(CASES[name])

    assert summary["exact"]
    assert summary["entries"] == expected.size
    assert summary["min"] == expected.min()
    assert summary["max"] == expected.max()
    assert summary["mean"] == pytest.approx(expected.mean())
    assert summary["std"] == pytest.approx(expected.std())
    assert summary["distinct"] == len(np.unique(expected))


@pytest.mark.parametrize("name", sorted(CASES))
@pytest.mark.parametrize("q", stats.QUANTILES)
def test_quantiles_match_the_inverted_cdf_method(name, q):
    """The counts are a compressed sample, so quantiles must match the expanded one."""
    summary = stats.summarise(accumulate(CASES[name]))
    expected = np.percentile(reference(CASES[name]), q * 100, method="inverted_cdf")

    assert summary["quantiles"][str(q)] == pytest.approx(expected)


def test_empty_input_stays_empty():
    store = accumulate(np.array([], dtype=np.int64), chunks=1)

    assert store.n == 0 and store.counts == {} and store.exact


def test_summarising_nothing_gives_no_numbers_rather_than_nan():
    """An object folder can legitimately hold an empty column.

    Dividing the total by the entry count would raise there rather than give a number.
    """
    summary = stats.summarise(stats.ValueCounts())

    assert summary["entries"] == 0
    assert summary["mean"] is None and summary["std"] is None
    assert summary["quantiles"] == {}


def test_wide_values_demote_but_keep_coverage_exact():
    """Event and orbit counters cannot be enumerated; coverage must still be right.

    A demoted store keeps a float64 running total instead of the exact map, so the mean
    is compared to a relative tolerance rather than exactly.
    """
    data = np.random.default_rng(5).integers(0, 1 << 40, 5000)
    summary = stats.summarise(accumulate(data))

    assert not summary["exact"]
    assert "quantiles" not in summary and "std" not in summary
    assert summary["entries"] == data.size
    assert (summary["min"], summary["max"]) == (data.min(), data.max())
    assert summary["mean"] == pytest.approx(data.mean(), rel=1e-12)


def test_demotion_partway_through_keeps_the_earlier_batches():
    """The narrow first batch is counted exactly, so demotion must keep it.

    Its entries and its total have to survive, rather than the accumulation restarting
    from the wide batch.
    """
    narrow = np.zeros(100, dtype=np.int64)
    wide = np.random.default_rng(6).integers(0, 1 << 40, 100)
    store = stats.ValueCounts()
    store.update(narrow)
    store.update(wide)

    assert not store.exact
    assert store.n == 200
    assert store.total == pytest.approx(float(wide.sum()), rel=1e-12)


def test_merge_is_the_same_as_counting_the_concatenation():
    rng = np.random.default_rng(7)
    first, second = rng.integers(0, 9, 300), rng.integers(0, 9, 300)
    merged = stats.merge_counts(stats.count_values(first), stats.count_values(second))

    assert merged == stats.count_values(np.concatenate([first, second]))


def test_pair_counts_match_histogram2d():
    rng = np.random.default_rng(8)
    first, second = rng.integers(-5, 6, 4000), rng.integers(0, 20, 4000)
    # Edges half a unit below each integer, so one bin holds one value. Row 0 of the
    # grid is then first == -5 and column 0 is second == 0, whence the offsets below.
    grid = np.histogram2d(
        first, second, bins=[np.arange(-5, 7) - 0.5, np.arange(0, 21) - 0.5]
    )[0]
    expected = {
        (row - 5, col): int(count)
        for (row, col), count in np.ndenumerate(grid)
        if count
    }

    assert stats.count_pairs({}, first, second) == expected


def test_non_finite_values_are_dropped_and_counted():
    """A NaN has to leave a trace: validation fails any feature with a non-finite tally.

    Non-finite entries stay out of the counts and out of `n`, hence 3 rather than 5.
    """
    store = stats.ValueCounts()
    store.update(np.array([1.0, 2.0, np.nan, np.inf, 2.0], dtype=np.float32))

    assert store.nonfinite == 2
    assert store.n == 3
    assert store.counts == {1.0: 1, 2.0: 2}


def test_saturation_fraction_counts_the_all_ones_code():
    data = np.array([511] * 3 + [0] * 7)
    summary = stats.summarise(accumulate(data, chunks=2), saturation=511)

    assert summary["saturated_fraction"] == pytest.approx(0.3)
    assert summary["zero_fraction"] == pytest.approx(0.7)


@pytest.mark.parametrize("dtype,sentinel", [(np.uint64, 2**64 - 1), (np.uint32, 2**32 - 1)])
def test_unsigned_sentinels_are_counted_not_wrapped(dtype, sentinel):
    """Simulation writes the all-ones value into orbit and bx; int64 cannot hold it."""
    store = accumulate(np.full(6, sentinel, dtype=dtype), chunks=2)
    summary = stats.summarise(store)

    assert store.counts == {sentinel: 6}
    assert summary["min"] == summary["max"] == sentinel
    assert summary["distinct"] == 1


def test_unsigned_values_keep_their_spacing_after_the_shift():
    values = np.array([2**64 - 3, 2**64 - 1, 2**64 - 3], dtype=np.uint64)

    assert stats.count_values(values) == {2**64 - 3: 2, 2**64 - 1: 1}


def test_counts_survive_a_json_round_trip():
    counts = stats.count_values(np.array([2, 10, 10, 2, 3]))

    assert stats.counts_from_json(stats.counts_to_json(counts)) == counts
