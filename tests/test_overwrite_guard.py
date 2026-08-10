"""convert_folder must not silently clobber parquet from a different input file.

Output parquet is named after the input stem, and convert_run maps several input
folders onto one output folder. Today's CRAB output numbers files continuously across
those leaf folders, so the stems happen to be unique and no data is lost, but nothing
in the code enforces that.
"""

import pytest

from adl1t_datamaker import root2parquet
from conversion_helpers import UNPACKED


@pytest.fixture
def converter():
    return root2parquet.Root2Parquet(mc=True, silent=True, **UNPACKED)


def make_leaf(tmp_path, name, stems):
    """One CRAB leaf directory of empty root files, named after the given stems.

    The stems are all the guard reads, and every test here either stops before the
    conversion or patches it out, so nothing ever opens these files.
    """
    leaf = tmp_path / name
    leaf.mkdir()
    for stem in stems:
        (leaf / f"{stem}.root").touch()
    return leaf


def already_converted(out_dir, stems):
    """Stand in for a previous convert_folder call over a different leaf.

    Only the seeds folder is filled, since that is the one the guard looks in: every
    conversion writes it, whatever the tree configuration.
    """
    seeds = out_dir / "seeds"
    seeds.mkdir(parents=True)
    for stem in stems:
        (seeds / f"{stem}.parquet").touch()


def test_clashing_stem_raises(tmp_path, converter):
    out = tmp_path / "out"
    already_converted(out, ["L1Ntuple_1", "L1Ntuple_2"])
    leaf = make_leaf(tmp_path, "0001", ["L1Ntuple_2", "L1Ntuple_3"])

    with pytest.raises(FileExistsError, match="L1Ntuple_2"):
        converter.convert_folder(
            folder=leaf,
            prescale_file=tmp_path / "menu.csv",
            pileup_folder=tmp_path,
            output_path=out,
        )


def test_distinct_stems_are_fine(tmp_path, converter, monkeypatch):
    """The real CRAB layout, where leaf 0001 continues the numbering from 0000."""
    out = tmp_path / "out"
    already_converted(out, ["L1Ntuple_1", "L1Ntuple_2"])
    leaf = make_leaf(tmp_path, "0001", ["L1Ntuple_3", "L1Ntuple_4"])

    converted = []
    monkeypatch.setattr(converter, "_conversion", converted.append)
    converter.convert_folder(
        folder=leaf,
        prescale_file=tmp_path / "menu.csv",
        pileup_folder=tmp_path,
        output_path=out,
    )

    assert len(converted) == 2


def test_allow_overwrite_opts_back_in(tmp_path, converter, monkeypatch):
    out = tmp_path / "out"
    already_converted(out, ["L1Ntuple_1"])
    leaf = make_leaf(tmp_path, "0001", ["L1Ntuple_1"])

    monkeypatch.setattr(converter, "_conversion", lambda _: None)
    converter.convert_folder(
        folder=leaf,
        prescale_file=tmp_path / "menu.csv",
        pileup_folder=tmp_path,
        output_path=out,
        allow_overwrite=True,
    )


def test_empty_folder_still_raises(tmp_path, converter):
    with pytest.raises(ValueError, match="is empty"):
        converter.convert_folder(
            folder=make_leaf(tmp_path, "0000", []),
            prescale_file=tmp_path / "menu.csv",
            pileup_folder=tmp_path,
            output_path=tmp_path / "out",
        )
