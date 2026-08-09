"""ParquetLoader / Parquet2Awkward against a synthetic parquet tree."""

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

    # A folder holding no parquet must be ignored, like the SUMMARY dir the summary
    # scripts drop into the same root.
    (tmp_path / "SUMMARY").mkdir()
    return tmp_path


def test_object_names_come_from_folders_with_parquet(dataset):
    loader = ParquetLoader(str(dataset))
    assert sorted(loader.object_names) == sorted(OBJECTS)
    assert "SUMMARY" not in loader.object_names


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


def test_select_feats_dict_is_not_mutated(dataset):
    """The caller's dict must survive being passed to a loader unchanged."""
    shared = {"muons": ["muonIEt"]}
    Parquet2Awkward(str(dataset), select_feats=shared)

    assert shared == {"muons": ["muonIEt"]}


def test_two_loaders_can_share_one_dict(tmp_path, dataset):
    """The scripts/summary_comparison case: one dict, two folders of different shape.

    _get_select_feats used to stamp absent objects as 'none' in the caller's dict, so
    an object missing from the first folder was permanently disabled for the second.
    """
    smaller = tmp_path / "smaller"
    (smaller / "muons").mkdir(parents=True)
    array = ak.Array({feat: [[1, 2], [3]] for feat in OBJECTS["muons"]})
    ak.to_parquet(array, smaller / "muons" / "L1Ntuple_1.parquet", compression="snappy")

    shared = {obj: feats for obj, feats in OBJECTS.items()}
    first = Parquet2Awkward(str(smaller), select_feats=shared)
    second = Parquet2Awkward(str(dataset), select_feats=shared)

    assert first.object_names == ["muons"]
    assert sorted(second.object_names) == sorted(OBJECTS), "jets/event_info were dropped"


def test_empty_select_feats_loads_nothing(dataset):
    """An empty dict means every object is unlisted, so nothing is read."""
    assert Parquet2Awkward(str(dataset), select_feats={}).object_names == []


def test_missing_folder_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        ParquetLoader(str(tmp_path / "not_here"))
