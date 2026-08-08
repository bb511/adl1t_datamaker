# The feature specification, read out of docs/README.md.
#
# The tables in docs/README.md give the range, step, bit width and inclusion flag of
# every global trigger feature. Parsing them here rather than restating them in code
# keeps one source of truth, and lets a report print the documented bit width beside the
# measured values.

import math
import re
from pathlib import Path

DOCS_README = Path(__file__).resolve().parents[2] / "docs" / "README.md"

# A sentinel: '## Energy Objects' names no object of its own, since the '###' headings
# beneath it name the six sums.
ENERGY = object()

SECTION_TO_OBJECT = {
    "Muon Objects": "muons",
    "Jet Objects": "jets",
    "Egamma Objects": "egammas",
    "Tau Objects": "taus",
    "Cicada Objects": "cica",
    "Energy Objects": ENERGY,
    "Event Information": "event_info",
}

TEXT_COLUMNS = ("Range", "Step", "Explanation")

# Multiplying a stored hardware code by one of these factors gives a physical quantity:
# GeV for transverse energies and momenta, radians for phi, dimensionless pseudorapidity
# for eta. Each factor restates a Step column of docs/README.md as a float. The phi codes
# tile the full 2*pi, into 576 bins for muons against 144 for the calorimeter, and muon
# eta is four times finer than calorimeter eta.
GEV_PER_ET = 0.5
MUON_ETA_STEP = 0.0870 / 8
MUON_PHI_STEP = 2 * math.pi / 576
CALO_ETA_STEP = 0.0870 / 2
CALO_PHI_STEP = 2 * math.pi / 144

UNIT_SCALES = {
    ("muons", "muonIEt"): (GEV_PER_ET, "GeV"),
    ("muons", "muonIEtUnconstrained"): (1.0, "GeV"),
    ("muons", "muonIEta"): (MUON_ETA_STEP, "eta"),
    ("muons", "muonIEtaAtVtx"): (MUON_ETA_STEP, "eta"),
    ("muons", "muonIPhi"): (MUON_PHI_STEP, "rad"),
    ("muons", "muonIPhiAtVtx"): (MUON_PHI_STEP, "rad"),
    ("jets", "jetIEt"): (GEV_PER_ET, "GeV"),
    ("jets", "jetIEta"): (CALO_ETA_STEP, "eta"),
    ("jets", "jetIPhi"): (CALO_PHI_STEP, "rad"),
    ("egammas", "egIEt"): (GEV_PER_ET, "GeV"),
    ("egammas", "egIEta"): (CALO_ETA_STEP, "eta"),
    ("egammas", "egIPhi"): (CALO_PHI_STEP, "rad"),
    ("taus", "tauIEt"): (GEV_PER_ET, "GeV"),
    ("taus", "tauIEta"): (CALO_ETA_STEP, "eta"),
    ("taus", "tauIPhi"): (CALO_PHI_STEP, "rad"),
}

# Every sum stores a magnitude in Et units, and only the four missing-energy sums add an
# angle. ET and HT carry ETTEM and tower_count in its place, so the phi entries written
# for them are never looked up.
for _sum in ("ET", "HT", "MET", "MHT", "FET", "FHT"):
    UNIT_SCALES[(_sum, "Et")] = (GEV_PER_ET, "GeV")
    UNIT_SCALES[(_sum, "phi")] = (CALO_PHI_STEP, "rad")
UNIT_SCALES[("ET", "ETTEM")] = (GEV_PER_ET, "GeV")

# An occupancy map needs an eta-phi pair, which only the particle collections carry: the
# energy sums store a phi with no eta.
OCCUPANCY_COLUMNS = {
    "muons": ("muonIEta", "muonIPhi"),
    "jets": ("jetIEta", "jetIPhi"),
    "egammas": ("egIEta", "egIPhi"),
    "taus": ("tauIEta", "tauIPhi"),
}


def documented_features() -> dict[str, dict[str, dict]]:
    """Every documented feature, keyed by parquet object and then by branch name.

    Each metadata mapping holds the range, step, explanation, bit width and inclusion
    flag. Features the docs mark as absent from the parquet are kept, flagged by
    ``included``.
    """
    blocks = _blocks(DOCS_README.read_text())

    return {obj: _parse_tables(lines) for obj, lines in sorted(blocks.items())}


def documented_capacities() -> dict[str, int]:
    """Objects per event per collection, skipping the ones the docs leave silent."""
    blocks = _blocks(DOCS_README.read_text())
    counts = {obj: _capacity(lines) for obj, lines in sorted(blocks.items())}

    return {obj: count for obj, count in counts.items() if count is not None}


def included_features() -> dict[str, list[str]]:
    """Per object, the features the docs mark as stored in the parquet, sorted by name."""
    return {
        obj: sorted(name for name, meta in feats.items() if meta["included"])
        for obj, feats in documented_features().items()
    }


def unit_scale(object_name: str, feature: str) -> tuple[float, str] | None:
    """Factor and unit label converting a stored hardware code to a physical quantity.

    :returns: ``None`` for a column carrying no physical unit, such as a quality flag, a
        tower count or an event identifier.
    """
    return UNIT_SCALES.get((object_name, feature))


def saturation_code(meta: dict) -> int | None:
    """The all-ones hardware code, for unsigned features whose range starts at zero.

    A signed, angular, or undocumented range returns None instead: an all-ones pattern is
    an ordinary value there, so counting entries equal to it would not measure saturation.
    """
    if meta.get("bits") is None or not meta.get("range", "").startswith("0.."):
        return None

    return 2 ** meta["bits"] - 1


def _blocks(text: str) -> dict[str, list[str]]:
    """The documentation lines describing each parquet object, keyed by object."""
    blocks, obj, in_energy = {}, None, False
    for line in text.splitlines():
        heading = re.match(r"^(#{2,3})\s+(.*?)\s*$", line)
        if heading:
            obj, in_energy = _resolve(heading[1], heading[2], obj, in_energy)
        elif obj:
            blocks.setdefault(obj, []).append(line)

    return blocks


def _resolve(level: str, title: str, obj: str | None, in_energy: bool) -> tuple:
    """The object a heading introduces, and whether energy sub-sections follow it.

    A '##' heading absent from SECTION_TO_OBJECT yields None, which drops every line
    beneath it until the next heading.
    """
    if level == "##":
        mapped = SECTION_TO_OBJECT.get(title)
        return (None if mapped is ENERGY else mapped), mapped is ENERGY
    if in_energy:
        return title.split()[0], True  # '### MET ($ET_\mathrm{miss}$)' -> 'MET'

    return obj, in_energy


def _parse_tables(lines: list[str]) -> dict[str, dict]:
    """Every feature row of every markdown table in one documentation block.

    Column positions come from each table's own header row rather than a fixed layout,
    because the Event Information table has three columns where the others have six.
    """
    features, columns = {}, None
    for cells in (_cells(line) for line in lines if line.startswith("|")):
        if cells[0] == "Feature":
            columns = {name: index for index, name in enumerate(cells)}
        elif columns and not cells[0].startswith("---"):
            features.update(_feature_row(cells, columns))

    return features


def _feature_row(cells: list[str], columns: dict) -> dict:
    """One table row as {branch name: metadata}, empty when the row names no branch."""
    name = re.match(r"`([^`]+)`", cells[0])
    if not name:
        return {}

    meta = {key.lower(): _column(cells, columns, key) for key in TEXT_COLUMNS}
    meta["bits"] = _bits(_column(cells, columns, "Bits"))
    meta["included"] = ":heavy_check_mark:" in cells[columns["in"]]

    return {name[1]: meta}


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _column(cells: list[str], columns: dict, key: str) -> str:
    index = columns.get(key)

    return cells[index] if index is not None and index < len(cells) else ""


def _bits(text: str) -> int | None:
    """Bit width from a cell like '9', '8+1' or '7+1 = 8'; None when undocumented."""
    stated = text.split("=")[-1].strip() if "=" in text else text.strip()
    if stated.isdigit():
        return int(stated)

    parts = [part.strip() for part in stated.split("+")]

    return sum(int(part) for part in parts) if all(p.isdigit() for p in parts) else None


def _capacity(lines: list[str]) -> int | None:
    """Objects per event, read from a 'There are N ... objects' note; None without one.

    The CICADA section writes 'There is one cicada object', which this does not match, so
    CICADA carries no documented capacity.
    """
    match = re.search(r"There are (\d+) \w+ objects", "\n".join(lines))

    return int(match[1]) if match else None
