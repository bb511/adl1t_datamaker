"""The sum type of each energy object, pinned so a restructure cannot shift one again.

The energies all live in one leaf of the L1TNtuple and are separated only by a sumType
flag, so a wrong number is silently wrong: it yields a full, plausible column of somebody
else's quantity. That is what happened to ETTEM, which was set to 1 (HT) instead of 16
and so duplicated HT.Et in every data set produced before the reconversion of
2026-08-08.

The values here are the ones the original HDF5 converter used (h5convert/root2h5.py at
commit 70d7e1d, `_store_energies`), confirmed against a 2025 zero-bias ntuple.
"""

import pytest

from adl1t_datamaker import root2parquet
from conversion_helpers import EMULATED

EXPECTED = {
    "ET": {"Et": 0, "ETTEM": 16},
    "HT": {"Et": 1, "tower_count": 21},
    "MET": {"Et": 2, "phi": 2},
    "MHT": {"Et": 3, "phi": 3},
    "FET": {"Et": 8, "phi": 8},
    "FHT": {"Et": 20, "phi": 20},
}


@pytest.fixture(scope="module")
def energies():
    """The sum-type table, read off a converter that never opens a file.

    Only the table is under test, so mc and the tree names are free: they merely have to
    build.
    """
    return root2parquet.Root2Parquet(mc=True, **EMULATED).energies


@pytest.mark.parametrize("obj", sorted(EXPECTED))
def test_sum_types_are_the_documented_ones(obj, energies):
    assert energies[obj] == EXPECTED[obj]


def test_no_two_energy_columns_share_a_sum_type(energies):
    """The bug this file exists for: a collision makes two columns identical.

    MET, MHT, FET and FHT legitimately reuse one sum type for their magnitude and their
    angle, because those are read from different branches; the clash that matters is two
    magnitudes, both read from sumIEt, sharing a number.
    """
    magnitudes = {
        f"{obj}.{feature}": kind
        for obj, features in energies.items()
        for feature, kind in features.items()
        if feature != "phi"
    }
    duplicated = [
        kind for kind in set(magnitudes.values())
        if list(magnitudes.values()).count(kind) > 1
    ]

    assert not duplicated, f"sum types {duplicated} feed more than one column"
