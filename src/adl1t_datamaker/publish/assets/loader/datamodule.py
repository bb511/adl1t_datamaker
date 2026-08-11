# Driving the four stages, for a caller who wants tensors and nothing else.

import logging
from dataclasses import dataclass
from pathlib import Path

import torch

from . import common

log = logging.getLogger(__name__)

CATEGORIES = ("zerobias", "background", "signal")


@dataclass(frozen=True)
class SplitTensors:
    """One split as a model sees it: input, padding mask, trigger verdict and label."""

    x: torch.Tensor
    mask: torch.Tensor
    l1bit: torch.Tensor
    y: torch.Tensor


@dataclass
class L1ADData:
    """Run the pipeline over the published record and hand back its tensors.

    :param zerobias: ``{data set: directory of its published shards}``, the normal data.
    :param signal: The simulated anomalies, which are validation data only.
    :param background: The simulated normal data, likewise validation only.
    :param train_features: ``{object: [features]}`` a model is trained on.
    :param l1_scales: Hardware-to-physical factors, carried for the rate calculations.
        Nothing here applies them, so the tensors stay in integer hardware units.
    """

    zerobias: dict
    signal: dict
    background: dict
    data_extractor: object
    data_processor: object
    data_normalizer: object
    data_mlready: object
    data_awkward2torch: object
    train_features: dict
    l1_scales: dict | None = None

    def prepare(self) -> None:
        """Extract, process and normalise every category. Cached, so reruns are cheap."""
        for category in CATEGORIES:
            self.data_extractor.extract(getattr(self, category), category)
        for category in CATEGORIES:
            self.data_processor.process(category)
        self.data_mlready.prepare(self.data_normalizer, self.train_features)

    def load(self, split: str) -> SplitTensors:
        """The zero-bias tensors of one split, labelled 0 as the record labels them."""
        return self._tensors(self.data_mlready.cache_folder / split, label=0)

    def load_aux(self, split: str) -> dict[str, SplitTensors]:
        """Every simulated sample that carries this split, keyed by data set name."""
        aux = self.data_mlready.cache_folder / "aux"
        labels = self.labels()

        return {
            path.name: self._tensors(path / split, labels[path.name])
            for path in common.datasets_in(aux)
            if (path / split).is_dir()
        }

    def labels(self) -> dict[str, int]:
        """Zero bias 0, simulated background negative, signals positive by sorted name.

        These are the values the record's own ``label`` column carries, so a tensor built
        here and a row read straight off the record agree on what a sample is.
        """
        labels = {name: 0 for name in self.zerobias}
        labels.update({n: -(i + 1) for i, n in enumerate(sorted(self.background))})
        labels.update({n: i + 1 for i, n in enumerate(sorted(self.signal))})

        return labels

    def _tensors(self, folder: Path, label: int) -> SplitTensors:
        """One cached split, with its label broadcast over the events."""
        x, mask, l1bit = self.data_awkward2torch.load_folder(folder)

        y = torch.full((len(x),), label, dtype=torch.int64)

        return SplitTensors(x=x, mask=mask, l1bit=l1bit, y=y)
