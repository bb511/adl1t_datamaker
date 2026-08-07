"""docs/README.md is the specification; the code and the parquet must agree with it.

The tables there mark each feature with :heavy_check_mark: or :x: in the `in` column,
which makes them an independent source of truth. Parsing them catches both the code
drifting from the docs and the docs going stale.

The Energy Objects section is deliberately excluded: it names features in LaTeX
($E_t$, $\\varphi$) rather than as branch identifiers, so it is not machine-readable.
Those objects are covered structurally by the conversion tests instead.
"""

import re
from pathlib import Path

import pytest

from adl1t_datamaker import root2parquet
import eos
from conversion_helpers import EMULATED, convert

REPO_ROOT = Path(__file__).resolve().parent.parent

# docs section heading -> parquet folder written by Root2Parquet.
SECTION_TO_OBJECT = {
    "Muon Objects": "muons",
    "Jet Objects": "jets",
    "Egamma Objects": "egammas",
    "Tau Objects": "taus",
    "Cicada Objects": "cica",
}

INPUT = (
    "/eos/cms/store/cmst3/group/l1tr/axol1tl/MC/L1TNtupleRun3-142XWinter25/"
    "haa-4b-ma15-POWHEG/mcRun3_Run3Winter25Digi-142XnoPU/250522_115555/0000/"
    "L1Ntuple_105.root"
)
MENU = "L1Menu_Collisions2024_v1_3_0_last.csv"


def documented_features() -> dict[str, list[str]]:
    """Backticked feature names ticked as included, per docs section."""
    features, section = {}, None
    for line in (REPO_ROOT / "docs" / "README.md").read_text().splitlines():
        heading = re.match(r"^##\s+(.*?)\s*$", line)
        if heading:
            section = heading.group(1)
            continue
        if section not in SECTION_TO_OBJECT or not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 6 or cells[0].startswith("---") or cells[0] == "Feature":
            continue
        name = re.match(r"`([^`]+)`", cells[0])
        if name and ":heavy_check_mark:" in cells[-1]:
            features.setdefault(SECTION_TO_OBJECT[section], []).append(name.group(1))

    return features


DOCUMENTED = documented_features()


def test_every_mapped_section_was_found():
    """Guard the parser itself, so a docs reshuffle cannot silently empty this suite."""
    assert set(DOCUMENTED) == set(SECTION_TO_OBJECT.values())
    assert DOCUMENTED["muons"], "muon table parsed as empty"


@pytest.mark.parametrize("obj", ["muons", "jets", "egammas", "taus"])
def test_code_requests_exactly_what_docs_promise(obj):
    """Root2Parquet's own feature lists must match the specification."""
    conv = root2parquet.Root2Parquet(mc=True, **EMULATED)
    assert sorted(conv.particles[obj]) == sorted(DOCUMENTED[obj])


def test_code_requests_documented_cicada_features():
    conv = root2parquet.Root2Parquet(mc=True, **EMULATED)
    assert sorted(conv.cicada["cicada"]) == sorted(DOCUMENTED["cica"])


@pytest.mark.eos
def test_converted_parquet_matches_docs(tmp_path, repo_root):
    """The end of the chain: real converted columns against the specification."""
    url = eos.require_file(INPUT, min_bytes=500_000)
    out = convert(url, tmp_path, repo_root, MENU, mc=True, converter=EMULATED)

    from adl1t_datamaker.loader import Parquet2Awkward

    data = Parquet2Awkward(str(out))
    for obj, expected in DOCUMENTED.items():
        assert sorted(data[obj].fields) == sorted(expected), f"{obj} schema drifted"
