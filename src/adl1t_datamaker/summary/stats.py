# Exact statistics for the converted parquet, accumulated in one streaming pass.
#
# The physics quantities the global trigger stores are bounded hardware integers, the
# widest documented at 13 bits. So instead of sampling, or histogramming against guessed
# bin edges, this module counts how often each value occurs and derives the rest from that
# map: mean, standard deviation, any quantile, distinct values, zero and saturation
# fractions, and the histograms the figures draw.
#
# The event, orbit and time identifiers barely repeat, so counting them would hold one
# entry per event; measure.py accumulates those through Extremes instead, which keeps
# count, extremes and a running total alone.

import numpy as np

# Caps what one batch may allocate: a bincount over 2**20 bins is 8 MB of int64. A wider
# batch falls back to np.unique, and count_pairs skips it.
MAX_DENSE_SPAN = 1 << 20

QUANTILES = (0.01, 0.05, 0.25, 0.50, 0.75, 0.95, 0.99)


class ValueCounts:
    """How often each value occurs in one feature, accumulated batch by batch."""

    exact = True

    def __init__(self):
        self.counts: dict = {}
        self.n = 0
        self.nonfinite = 0
        self.low = None
        self.high = None

    def update(self, values: np.ndarray) -> None:
        """Fold one batch of one feature in, whatever its shape: only the contents count.

        Non-finite floats never reach the counts and are tallied in `nonfinite` instead,
        so `n` counts the finite entries alone. Booleans are counted as 0 and 1.
        """
        if values.dtype.kind == "b":
            return self._add(count_values(values), values.size)
        values, dropped = _finite(values)
        self.nonfinite += dropped
        if values.size:
            self._accumulate(values, values.min().item(), values.max().item())

    def _add(self, counts: dict, size: int) -> None:
        """Fold in a batch already counted, which is all the work booleans need.

        `counts` must be non-empty whenever `size` is non-zero: the extremes are read off
        its keys.
        """
        if not size:
            return
        self.n += size
        self._widen(min(counts), max(counts))
        merge_counts(self.counts, counts)

    def _widen(self, low, high) -> None:
        self.low = low if self.low is None else min(self.low, low)
        self.high = high if self.high is None else max(self.high, high)

    def _accumulate(self, values: np.ndarray, low, high) -> None:
        self.n += values.size
        self._widen(low, high)
        merge_counts(self.counts, count_values(values, low))

    @property
    def total(self) -> float:
        """The sum of every entry seen.

        Re-added from the map on each call rather than carried as a running sum: integer
        keys times integer weights stay exact in Python ints, so the mean of an integer
        feature carries no accumulated rounding.
        """
        return sum(value * weight for value, weight in self.counts.items())


class Extremes:
    """Count, extremes and a running total for a feature never counted exactly.

    The empty `counts` and `exact = False` give it the shape every consumer of a store
    expects: statistics an exact map would afford are simply absent from its summary.
    """

    exact = False

    def __init__(self):
        self.counts: dict = {}
        self.n = 0
        self.nonfinite = 0
        self.low = None
        self.high = None
        self._total = 0.0

    def update(self, values: np.ndarray) -> None:
        values, dropped = _finite(values)
        self.nonfinite += dropped
        if not values.size:
            return
        self.n += values.size
        # Summed in float64: a uint64 sum of packed time values wraps within one batch.
        self._total += float(values.sum(dtype=np.float64))
        low, high = values.min().item(), values.max().item()
        self.low = low if self.low is None else min(self.low, low)
        self.high = high if self.high is None else max(self.high, high)

    @property
    def total(self) -> float:
        return self._total


def count_values(values: np.ndarray, low=None) -> dict:
    """Exact {value: occurrences} for one batch.

    :param low: The batch minimum, passed in where the caller already knows it. Without
        it the integer path scans the array again, once per column of every batch.
    """
    if values.dtype.kind == "b":
        return _count_bools(values)
    if values.dtype.kind in "iu":
        return _count_integers(values, low)
    uniques, counts = np.unique(values, return_counts=True)

    return dict(zip(uniques.tolist(), counts.tolist()))


def _count_bools(values: np.ndarray) -> dict:
    """One pass and no copy. The seed columns are booleans and there are hundreds."""
    fired = int(np.count_nonzero(values))

    return {value: weight for value, weight in
            ((0, values.size - fired), (1, fired)) if weight}


def merge_counts(into: dict, other: dict) -> dict:
    """Add one count map into another, in place."""
    for value, weight in other.items():
        into[value] = into.get(value, 0) + weight

    return into


def count_pairs(into: dict, first: np.ndarray, second: np.ndarray) -> dict:
    """Add the exact joint counts of two aligned integer arrays into a map, keyed by pair.

    The arrays must be of equal length. A batch whose bounding grid spans more than
    MAX_DENSE_SPAN cells is skipped and `into` returned unchanged: a grid that large is
    no longer an occupancy map worth drawing. A caller therefore cannot assume that every
    batch reached the map.
    """
    if first.size == 0:
        return into
    lows = (int(first.min()), int(second.min()))
    width = int(second.max()) - lows[1] + 1
    if (int(first.max()) - lows[0] + 1) * width > MAX_DENSE_SPAN:
        return into
    # Row-major pack, `first` along the rows, so the whole batch takes one bincount.
    packed = (first.astype(np.int64) - lows[0]) * width + (second - lows[1])

    return _unpack_pairs(into, count_values(packed), lows, width)


def as_arrays(counts: dict) -> tuple[np.ndarray, np.ndarray]:
    """Values and matching weights, sorted ascending so every sum is reproducible.

    The weights are read off the sorted keys, not off the float array: a key such as
    2**64 - 1 does not survive the round trip through float64, so the lookup afterwards
    would raise. That conversion also rounds any key above 2**53, which leaves the
    standard deviation and quantiles of a feature that wide approximate; its extremes and
    counts stay exact, never having left Python ints.
    """
    if not counts:
        return np.empty(0), np.empty(0)
    keys = sorted(counts)
    weights = np.array([counts[key] for key in keys], dtype=np.int64)

    return np.array(keys, dtype=np.float64), weights


def mean(values: np.ndarray, weights: np.ndarray) -> float:
    return float(np.dot(values, weights) / weights.sum())


def stdev(values: np.ndarray, weights: np.ndarray) -> float:
    """Population standard deviation, matching numpy's default ddof=0.

    Centring before squaring rather than taking E[x^2] - E[x]^2 avoids the cancellation
    that form suffers when the mean is large compared with the spread.
    """
    centred = values - mean(values, weights)

    return float(np.sqrt(np.dot(centred * centred, weights) / weights.sum()))


def quantile(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    """Exact q-quantile, matching numpy's 'inverted_cdf' method on the expanded sample.

    The convention is the smallest counted value whose cumulative weight reaches `q` of
    the total, with no interpolation between neighbours, so the answer is always a value
    that occurs. `values` must be sorted ascending with `weights` aligned to it, as
    `as_arrays` returns them. The clamp is defensive: for q at most one the search cannot
    run past the last value.
    """
    cumulative = np.cumsum(weights)
    index = int(np.searchsorted(cumulative, q * cumulative[-1], side="left"))

    return float(values[min(index, values.size - 1)])


def fraction_equal(counts: dict, value, total: int) -> float:
    """Share of the entries equal to `value`; 0.0 when there are no entries."""
    return counts.get(value, 0) / total if total else 0.0


def summarise(store: ValueCounts | Extremes, saturation: int | None = None) -> dict:
    """Everything a report says about one feature.

    :param saturation: The all-ones hardware code for this feature, which signed and
        angular features lack. None leaves the saturated fraction out.
    :returns: The entry count, non-finite tally, extremes and mean always, and the
        standard deviation, distinct values, zero fraction and quantiles only for a
        store counting exactly.
    """
    summary = {
        "entries": store.n,
        "nonfinite": store.nonfinite,
        "min": store.low,
        "max": store.high,
        "exact": store.exact,
        "mean": store.total / store.n if store.n else None,
    }

    return summary | (_exact_summary(store, saturation) if store.exact else {})


def counts_to_json(counts: dict) -> dict:
    """Serialise a count map as parallel sorted lists.

    A JSON object would have its keys re-ordered lexicographically by the sort_keys dump
    in core.py, putting "10" before "2", so the values travel as a list instead.
    """
    values = sorted(counts)

    return {"values": values, "counts": [counts[value] for value in values]}


def _exact_summary(store: ValueCounts, saturation: int | None) -> dict:
    """The statistics only an exact count map can give."""
    if not store.counts:
        return {"std": None, "distinct": 0, "zero_fraction": 0.0, "quantiles": {}}
    values, weights = as_arrays(store.counts)
    summary = {
        "std": stdev(values, weights),
        "distinct": len(store.counts),
        "zero_fraction": fraction_equal(store.counts, 0, store.n),
        "quantiles": {str(q): quantile(values, weights, q) for q in QUANTILES},
    }
    if saturation is not None:
        summary["saturated_fraction"] = fraction_equal(store.counts, saturation, store.n)

    return summary


def _count_integers(values: np.ndarray, low=None) -> dict:
    """Bincount over values shifted down to zero, so negatives count correctly.

    A batch spanning MAX_DENSE_SPAN or more falls back to np.unique: exact either way,
    just without the dense allocation.
    """
    flat = values.ravel()
    low = int(flat.min()) if low is None else int(low)
    if int(flat.max()) - low >= MAX_DENSE_SPAN:
        uniques, counts = np.unique(flat, return_counts=True)
        return dict(zip(uniques.tolist(), counts.tolist()))
    dense = np.bincount(_shifted(flat, low))
    seen = np.nonzero(dense)[0]
    # Offsets and weights leave numpy as Python ints, so undoing the shift below cannot
    # overflow: an unsigned column can carry low = 2**64 - 1.
    weights = dense[seen].tolist()

    return {offset + low: weight for offset, weight in zip(seen.tolist(), weights)}


def _shifted(flat: np.ndarray, low: int) -> np.ndarray:
    """Values moved down to start at zero, without leaving the representable range.

    Unsigned columns shift within their own dtype: simulation writes the all-ones
    sentinel into orbit and bx, and 2**64 - 1 does not survive the trip through int64.
    That subtraction relies on `low` being no greater than the minimum of `flat`, since
    an unsigned difference below zero wraps instead of going negative.
    """
    if low == 0:
        return flat
    if flat.dtype.kind == "u":
        return flat - flat.dtype.type(low)

    return flat.astype(np.int64) - low


def _finite(values: np.ndarray) -> tuple[np.ndarray, int]:
    """The finite entries, and how many entries were dropped as non-finite."""
    if values.dtype.kind != "f":
        return values, 0
    good = np.isfinite(values)

    return values[good], int((~good).sum())


def _unpack_pairs(into: dict, packed: dict, lows: tuple, width: int) -> dict:
    for key, weight in packed.items():
        pair = (key // width + lows[0], key % width + lows[1])
        into[pair] = into.get(pair, 0) + weight

    return into
