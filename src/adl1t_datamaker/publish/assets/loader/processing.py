# Applying the saturation cuts to the extracted data.

import functools
import logging
import operator
from dataclasses import dataclass
from pathlib import Path

import awkward as ak

from . import common

log = logging.getLogger(__name__)


@dataclass
class L1DataProcessor:
    """Drop the events and mask the objects the trigger saturated.

    :param extracted_folder: The extract stage's output, ``.../extracted/<name>``.
    :param event_filters: ``{object: expression}``. An event survives when every one of
        its entries in that object passes, e.g. ``ET: 'Et < 4095'``.
    :param object_filters: ``{object: expression}``, applied per object instead of per
        event, so one saturated jet leaves the rest of its event intact.
    :param name: Names this processing; the ml-ready cache inherits it.
    """

    extracted_folder: str
    event_filters: dict
    object_filters: dict
    cache_root_dir: str = "data"
    name: str = "default"
    verbose: bool = False

    def process(self, data_category: str) -> None:
        """Process every extracted data set of one category."""
        source = Path(self.extracted_folder) / data_category
        root = Path(self.cache_root_dir) / "processed" / self.name / data_category
        for dataset_dir in common.datasets_in(source):
            out_dir = root / dataset_dir.name
            if common.cached(out_dir, common.objects_in(dataset_dir)):
                log.info("Processed %s exists at %s.", dataset_dir.name, out_dir)
                continue
            self._process_dataset(dataset_dir, out_dir)

    def _process_dataset(self, dataset_dir: Path, out_dir: Path) -> None:
        """Write one data set's objects with the saturated events and objects removed."""
        out_dir.mkdir(parents=True, exist_ok=True)
        keep = self._event_mask(dataset_dir)
        filters = common.as_dict(self.object_filters)
        for path in sorted(dataset_dir.glob("*.parquet")):
            data = ak.from_parquet(path)[keep]
            criterion = filters.get(path.stem)
            ak.to_parquet(data[_mask(data, criterion)] if criterion else data, out_dir / path.name)
        log.info("Cached processed data at %s.", out_dir)

    def _event_mask(self, dataset_dir: Path) -> ak.Array:
        """The events that pass every event-level filter."""
        masks = [
            ak.all(_mask(_load(dataset_dir, obj), criterion), axis=1)
            for obj, criterion in common.as_dict(self.event_filters).items()
        ]

        return functools.reduce(operator.and_, masks)


def _load(dataset_dir: Path, obj: str) -> ak.Array:
    path = dataset_dir / f"{obj}.parquet"
    if not path.is_file():
        raise FileNotFoundError(f"{obj} is filtered on but was not extracted: {path}.")

    return ak.from_parquet(path)


def _mask(data: ak.Array, criterion: str) -> ak.Array:
    """Evaluate a filter such as ``Et < 511`` against one object's own fields.

    Awkward's operators do the work, the expression only naming fields and literals.
    Configuration files are trusted input, as they were for the numexpr evaluation this
    replaces.
    """
    return eval(criterion, {"__builtins__": {}}, {f: data[f] for f in data.fields})
