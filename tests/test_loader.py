"""ParquetLoader / Parquet2Awkward against a synthetic parquet tree. No ROOT, no EOS."""

import awkward as ak
import pytest

from adl1t_datamaker.loader import Parquet2Awkward, ParquetLoader

OBJECTS = {
    "muons": ["muonIEt", "muonIEta", "muonIPhi"],
    "jets": ["jetIEt", "jetIEta", "jetIPhi"],
    "event_info": ["run", "lumi", "event"],
}


@pytest.fixture
def dataset(tmp_path):
    """A <root>/<object>/*.parquet tree shaped like a real conversion."""
    for obj, feats in OBJECTS.items():
        folder = tmp_path / obj
        folder.mkdir()
        for part in ["L1Ntuple_1", "L1Ntuple_2"]:
            array = ak.Array({feat: [[1, 2], [3]] for feat in feats})
            ak.to_parquet(array, folder / f"{part}.parquet", compression="snappy")

    # A folder holding no parquet must be ignored, like the PLOTS dir the plot
    # scripts drop into the same root.
    (tmp_path / "PLOTS").mkdir()
    return tmp_path


def test_object_names_come_from_folders_with_parquet(dataset):
    loader = ParquetLoader(str(dataset))
    assert sorted(loader.object_names) == sorted(OBJECTS)
    assert "PLOTS" not in loader.object_names


def test_reads_everything_when_no_features_given(dataset):
    """select_feats=None is the documented read-everything mode."""
    data = Parquet2Awkward(str(dataset))

    assert sorted(data.object_names) == sorted(OBJECTS)
    for obj, feats in OBJECTS.items():
        assert sorted(data[obj].fields) == sorted(feats)
        assert len(data[obj]) == 4  # two files, two events each


def test_selected_features_narrow_the_columns(dataset):
    data = Parquet2Awkward(str(dataset), select_feats={"muons": ["muonIEt"]})

    assert data.object_names == ["muons"]  # unlisted objects are dropped
    assert data["muons"].fields == ["muonIEt"]


def test_unknown_feature_raises(dataset):
    with pytest.raises(ValueError, match="not in data loaded"):
        Parquet2Awkward(str(dataset), select_feats={"muons": ["does_not_exist"]})


def test_iterator_and_getitem_agree(dataset):
    data = Parquet2Awkward(str(dataset))
    batched = ak.concatenate(list(data("muons")))
    assert len(batched) == len(data["muons"])


def test_select_feats_dict_is_mutated(dataset):
    """Documents a sharp edge rather than endorsing it.

    _get_select_feats stamps absent objects as 'none' in the caller's dict, so
    scripts/plot_comparison reusing one dict for two folders lets the first folder
    permanently disable objects for the second.
    """
    shared = {"muons": ["muonIEt"]}
    Parquet2Awkward(str(dataset), select_feats=shared)

    assert shared["jets"] == "none"
    assert shared["event_info"] == "none"


def test_missing_folder_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        ParquetLoader(str(tmp_path / "not_here"))
