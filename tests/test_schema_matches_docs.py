"""docs/README.md is the specification; the code and the parquet must agree with it.

The tables there mark each feature with :heavy_check_mark: or :x: in the `in` column,
which makes them an independent source of truth. Checking against them catches both the
code drifting from the docs and the docs going stale.

The parser lives in `adl1t_datamaker.schema` because the summary reports need the same
tables for their bit widths and documented ranges; this suite consumes it.
"""

import pytest

from adl1t_datamaker import root2parquet
from adl1t_datamaker import schema
from conversion_helpers import EMULATED

# Objects compared column for column against the docs tables. seeds is absent because
# its columns come from the prescale menu rather than from docs/README.md, and
# event_info is left to test_code_requests_documented_event_information below.
OBJECTS = ("muons", "jets", "egammas", "taus", "cica", "ET", "HT", "MET", "MHT", "FET", "FHT")

DOCUMENTED = schema.included_features()


def test_every_expected_section_was_found():
    """Guard the parser itself, so a docs reshuffle cannot silently empty this suite."""
    assert set(OBJECTS) <= set(DOCUMENTED)
    assert DOCUMENTED["muons"], "muon table parsed as empty"
    assert DOCUMENTED["event_info"], "event information table parsed as empty"


@pytest.mark.parametrize("obj", ["muons", "jets", "egammas", "taus"])
def test_code_requests_exactly_what_docs_promise(obj):
    """Root2Parquet's own feature lists must match the specification."""
    conv = root2parquet.Root2Parquet(mc=True, **EMULATED)
    assert sorted(conv.particles[obj]) == sorted(DOCUMENTED[obj])


def test_code_requests_documented_cicada_features():
    conv = root2parquet.Root2Parquet(mc=True, **EMULATED)
    assert sorted(conv.cicada["cicada"]) == sorted(DOCUMENTED["cica"])


def test_code_requests_documented_event_information():
    conv = root2parquet.Root2Parquet(mc=True, **EMULATED)
    assert sorted(conv.event_info["event_info"]) == sorted(DOCUMENTED["event_info"])


@pytest.mark.parametrize("obj", ["ET", "HT", "MET", "MHT", "FET", "FHT"])
def test_code_stores_the_documented_energy_columns(obj):
    """The energy tables name parquet columns, so the sumType map can be checked."""
    conv = root2parquet.Root2Parquet(mc=True, **EMULATED)
    assert sorted(conv.energies[obj]) == sorted(DOCUMENTED[obj])
