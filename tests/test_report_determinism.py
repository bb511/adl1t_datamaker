"""Two summaries of the same data must be byte identical outside the generated block.

The conversion is byte reproducible (see test_determinism.py); a summary of it that
shuffled its own rows between runs would make that guarantee useless for review.
"""

import json

import numpy as np
import pytest

import awkward as ak

from adl1t_datamaker import summary

EVENTS = 24


@pytest.fixture
def dataset(tmp_path):
    """Enough shape to exercise sorting: jagged objects, singletons and floats."""
    rng = np.random.default_rng(3)
    folder = tmp_path / "Repeatable"
    for name, columns in {
        "jets": {"jetIEt": (0, 200), "jetIEta": (-40, 40), "jetIPhi": (0, 144)},
        "muons": {"muonIEt": (0, 90), "muonIEta": (-80, 80), "muonIPhi": (0, 576)},
    }.items():
        counts = rng.integers(0, 5, EVENTS)
        (folder / name).mkdir(parents=True)
        ak.to_parquet(
            ak.Array({
                column: ak.unflatten(rng.integers(low, high, int(counts.sum())), counts)
                for column, (low, high) in columns.items()
            }),
            folder / name / "L1Ntuple_1.parquet", compression="snappy",
        )
    (folder / "event_info").mkdir(parents=True)
    ak.to_parquet(
        ak.singletons(ak.Array({
            "run": np.full(EVENTS, 396102), "lumi": rng.integers(1, 5, EVENTS),
            "event": np.arange(EVENTS), "bx": rng.integers(1, 3564, EVENTS),
            "orbit": np.arange(EVENTS), "time": np.full(EVENTS, 1716486000 << 32),
            "nPV_True": rng.uniform(20, 55, EVENTS).astype(np.float32),
        })),
        folder / "event_info" / "L1Ntuple_1.parquet", compression="snappy",
    )

    return folder


def summarise_twice(dataset, tmp_path, generated_at="2026-01-01T00:00:00+00:00"):
    """Summarise one folder into two directories and return both paths.

    :param generated_at: Pinned by default, so anything that differs between the two
        outputs came from the measurement rather than from the clock.
    """
    outputs = [tmp_path / "first", tmp_path / "second"]
    for outdir in outputs:
        summary.summarise_folder(
            dataset, outdir, batch_size=7, checksums=True, generated_at=generated_at
        )

    return outputs


def test_report_and_json_are_byte_identical(dataset, tmp_path):
    first, second = summarise_twice(dataset, tmp_path)

    for name in ("REPORT.md", "summary.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes(), name


def test_a_different_batch_size_gives_the_same_numbers(dataset, tmp_path):
    """For columns narrow enough to keep counting exactly, batch size changes only the
    accumulation order and never a reported number.

    It is a tuning knob for memory, so a summary that moved with it would make two runs
    of the same data incomparable.
    """
    coarse = summary.measure_folder(dataset, batch_size=1000)
    fine = summary.measure_folder(dataset, batch_size=3)

    assert json.dumps(coarse, sort_keys=True, default=float) == json.dumps(
        fine, sort_keys=True, default=float
    )


def test_only_the_generated_block_moves_with_the_timestamp(dataset, tmp_path):
    """Everything that varies between runs is confined to one block of the report."""
    first = summarise_twice(dataset, tmp_path, "2026-01-01T00:00:00+00:00")[0]
    later = tmp_path / "later"
    summary.summarise_folder(
        dataset, later, batch_size=7, checksums=True,
        generated_at="2027-02-03T04:05:06+00:00",
    )
    differing = set(first.joinpath("REPORT.md").read_text().splitlines()) ^ set(
        later.joinpath("REPORT.md").read_text().splitlines()
    )

    assert differing, "the timestamp should appear somewhere"
    assert all("Generated" in line for line in differing), differing
