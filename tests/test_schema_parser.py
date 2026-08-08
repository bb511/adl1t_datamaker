"""The docs/README.md parser, behind the Bits column and every saturation ceiling."""

import pytest

from adl1t_datamaker import schema

DOCUMENTED = schema.documented_features()


def test_all_twelve_object_sections_parse():
    """A '## Energy Objects' heading names no object; its six '###' children do.

    Guards the parser itself, so a reshuffle of the docs cannot quietly empty this file.
    """
    expected = {"muons", "jets", "egammas", "taus", "cica", "event_info",
                "ET", "HT", "MET", "MHT", "FET", "FHT"}

    assert set(DOCUMENTED) == expected


@pytest.mark.parametrize(
    "obj,feature,bits,starts", [
        ("jets", "jetIEt", 11, "0..1024 GeV"),
        ("muons", "muonIEt", 9, "0..256 GeV"),
        ("muons", "muonIEtaAtVtx", 9, "2π"),      # '8+1' must add up, not parse as 8
        ("jets", "jetIEta", 8, "-5..5"),          # '7+1 = 8' takes the stated total
        ("ET", "Et", 12, "0..2048 GeV"),
        ("HT", "tower_count", 13, "0..8191"),
    ],
)
def test_bits_and_range_are_read_from_the_table(obj, feature, bits, starts):
    entry = DOCUMENTED[obj][feature]

    assert entry["bits"] == bits
    assert entry["range"] == starts


def test_excluded_features_are_kept_but_flagged():
    """A ':x:' row is still parsed, so the docs can be checked against the code."""
    assert DOCUMENTED["muons"]["muonIso"]["included"] is False
    assert DOCUMENTED["muons"]["muonIEt"]["included"] is True


def test_the_three_column_event_table_parses():
    """Event Information carries three columns where every other table carries six.

    Column positions therefore cannot be assumed; the parser reads each table's header.
    """
    entry = DOCUMENTED["event_info"]["nPV_True"]

    assert entry["included"] is True
    assert entry["bits"] is None
    assert "pileup" in entry["explanation"].lower()


@pytest.mark.parametrize(
    "obj,feature,expected", [
        ("muons", "muonIEt", 511),        # 9 bits, unsigned
        ("ET", "Et", 4095),               # 12 bits, the event level ceiling
        ("HT", "tower_count", 8191),      # 13 bits
        ("jets", "jetIEta", None),        # signed, so all-ones is an ordinary value
        ("MET", "phi", None),             # angular, likewise
        ("muons", "muonQual", None),      # range is '-', so no ceiling is claimed
    ],
)
def test_saturation_code_only_applies_to_unsigned_fields(obj, feature, expected):
    assert schema.saturation_code(DOCUMENTED[obj][feature]) == expected


def test_documented_capacities_cover_the_particle_collections():
    """Validation flags any object exceeding this cap, so it must come out of the docs.

    Only these four state a capacity the parser can read: the CICADA note is phrased
    'There is one cicada object', and the note counting the energy sums sits above the
    first '###' heading, where no object owns it yet.
    """
    assert schema.documented_capacities() == {
        "muons": 8, "jets": 12, "egammas": 12, "taus": 12
    }


@pytest.mark.parametrize(
    "obj,feature,factor,unit", [
        ("muons", "muonIEt", 0.5, "GeV"),
        ("jets", "jetIEta", 0.0435, "eta"),
        ("MET", "phi", 2 * 3.141592653589793 / 144, "rad"),
        ("ET", "ETTEM", 0.5, "GeV"),
    ],
)
def test_unit_scales_convert_hardware_codes(obj, feature, factor, unit):
    scale = schema.unit_scale(obj, feature)

    assert scale[0] == pytest.approx(factor)
    assert scale[1] == unit


def test_unscaled_columns_have_no_conversion():
    """Quality flags and tower counts are already integers with no physical unit."""
    assert schema.unit_scale("HT", "tower_count") is None
    assert schema.unit_scale("event_info", "run") is None
