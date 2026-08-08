"""docs/README.md is the specification; the code and the parquet must agree with it.

The tables there mark each feature with :heavy_check_mark: or :x: in the `in` column,
which makes them an independent source of truth. Checking against them catches both the
code drifting from the docs and the docs going stale.

The parser lives in `adl1t_datamaker.schema` because the summary reports need the same
tables for their bit widths and documented ranges; this suite consumes it rather than
carrying a second copy that could disagree.
"""

import pytest

from adl1t_datamaker import root2parquet
from adl1t_datamaker import schema
import eos
from conversion_helpers import EMULATED, convert

# Objects compared column for column against the docs tables. seeds is absent because
# its columns come from the prescale menu rather than from docs/README.md, and
# event_info is left to test_code_requests_documented_event_information below.
OBJECTS = ("muons", "jets", "egammas", "taus", "cica", "ET", "HT", "MET", "MHT", "FET", "FHT")

INPUT = (
    "/eos/cms/store/cmst3/group/l1tr/axol1tl/MC/L1TNtupleRun3-142XWinter25/"
    "haa-4b-ma15-POWHEG/mcRun3_Run3Winter25Digi-142XnoPU/250522_115555/0000/"
    "L1Ntuple_105.root"
)
MENU = "L1Menu_Collisions2024_v1_3_0_last.csv"

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


@pytest.mark.eos
def test_converted_parquet_matches_docs(tmp_path, repo_root):
    """The end of the chain: real converted columns against the specification."""
    url = eos.require_file(INPUT, min_bytes=500_000)
    out = convert(url, tmp_path, repo_root, MENU, mc=True, converter=EMULATED)

    from adl1t_datamaker.loader import Parquet2Awkward

    data = Parquet2Awkward(str(out))
    for obj in OBJECTS:
        assert sorted(data[obj].fields) == sorted(DOCUMENTED[obj]), f"{obj} schema drifted"
