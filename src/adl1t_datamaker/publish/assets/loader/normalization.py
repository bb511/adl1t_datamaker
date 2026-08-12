# Feature normalisation, fitted on the training split alone.
#
# The scheme is picked by name: 'robust' is what the published studies used, 'standard'
# and 'robust_axov4' are the other two the configuration tree offers, and 'unnormalized'
# leaves the hardware integers as they are.

import logging
import pickle
from dataclasses import dataclass, field
from pathlib import Path

import awkward as ak
import numpy as np

log = logging.getLogger(__name__)


@dataclass
class L1DataNormalizer:
    """Shift and scale each feature of each object by parameters fitted on train.

    :param name: The scheme, one of ``unnormalized``, ``robust``, ``standard`` and
        ``robust_axov4``. It also names the ml-ready cache, so two schemes never share
        one directory.
    :param hyperparams: Passed to the fit of that scheme, e.g. the quantiles bounding
        the robust range. ``None`` for a scheme that takes none.
    """

    name: str
    hyperparams: dict | None = None
    norm_params: dict = field(default_factory=dict, init=False)

    def fit(self, data: ak.Array, obj_name: str) -> None:
        """Determine one object's parameters. Fit on the training split only."""
        log.info("Fitting %s normalisation to %s.", self.name, obj_name)
        self.obj_name = obj_name
        fit = getattr(self, f"_{self.name}_fit")
        if self.hyperparams:
            fit(data, **self.hyperparams)
        else:
            fit(data)

    def norm(self, data: ak.Array, obj_name: str) -> ak.Array:
        """Apply the parameters fitted earlier to any split."""
        return getattr(self, f"_{self.name}")(data, obj_name)

    def import_norm_params(self, norm_filepath: Path, obj_name: str) -> None:
        """Read one object's parameters back, for a run that did not fit them itself."""
        if not Path(norm_filepath).is_file():
            raise FileNotFoundError(f"Norm params not found at {norm_filepath}!")

        self.norm_params[obj_name] = pickle.loads(Path(norm_filepath).read_bytes())

    def export_norm_params(self, norm_filepath: Path, obj_name: str) -> None:
        """Write one object's parameters beside the split they were fitted on."""
        if Path(norm_filepath).suffix != ".pkl":
            raise ValueError(
                f"Norm params are only written to .pkl, not {norm_filepath}."
            )

        Path(norm_filepath).write_bytes(pickle.dumps(self.norm_params[obj_name]))

    def setup_1d_denorm(self, object_feature_map: dict) -> None:
        """Build the tensors that undo the normalisation on a flattened model input.

        :param object_feature_map: ``{object: {feature: [flat indices]}}``, as the torch
            stage writes it beside the tensors.
        """
        import torch

        self.object_feature_map = object_feature_map
        length = sum(len(i) for m in object_feature_map.values() for i in m.values())
        self.scale_tensor = torch.ones(length, dtype=torch.float32)
        self.shift_tensor = torch.zeros(length, dtype=torch.float32)
        for obj_name, feature_map in object_feature_map.items():
            self._fill_1d(obj_name, feature_map)

    def norm_1d_tensor(self, data):
        """Normalise a flattened model input in place."""
        scale, shift = self._as(data)

        return data.sub_(shift).div_(scale)

    def denorm_1d_tensor(self, data):
        """Undo :meth:`norm_1d_tensor` in place, e.g. on a model's reconstruction."""
        scale, shift = self._as(data)

        return data.mul_(scale).add_(shift)

    def _fill_1d(self, obj_name: str, feature_map: dict) -> None:
        """One object's parameters, spread over the columns it occupies."""
        params = self.norm_params.get(obj_name)
        if not params:
            raise ValueError(f"Missing norm params for the {obj_name} object.")

        for feat, idxs in feature_map.items():
            self.scale_tensor[idxs] = float(params.get(feat, {}).get("scale", 1.0))
            self.shift_tensor[idxs] = float(params.get(feat, {}).get("shift", 0.0))

    def _as(self, data):
        """The parameter tensors, on the device and dtype of the data they act on."""
        if getattr(self, "scale_tensor", None) is None:
            raise ValueError("Run setup_1d_denorm before normalising a flat tensor.")

        return (
            self.scale_tensor.to(device=data.device, dtype=data.dtype),
            self.shift_tensor.to(device=data.device, dtype=data.dtype),
        )

    def _affine(self, data: ak.Array, obj_name: str) -> ak.Array:
        """Shift and scale every feature by the parameters fitted for it."""
        params = self.norm_params[obj_name]

        return ak.Array(
            {
                f: (data[f] - params[f]["shift"]) / params[f]["scale"]
                for f in data.fields
            }
        )

    def _unnormalized(self, data: ak.Array, obj_name: str) -> ak.Array:
        return data

    def _unnormalized_fit(self, data: ak.Array) -> None:
        self._record({f: (0.0, 1.0) for f in data.fields})

    # Three schemes that differ in how they are fitted and not in how they are applied.
    _robust = _affine
    _standard = _affine
    _robust_axov4 = _affine

    def _robust_fit(self, data: ak.Array, percentiles: list) -> None:
        """Shift by the median, scale by the interquantile range."""
        fitted = {}
        for feat in data.fields:
            values = _values(data[feat])
            low, high = np.quantile(values, percentiles)
            fitted[feat] = (float(np.median(values)), float(high - low))

        self._record(fitted)

    def _standard_fit(self, data: ak.Array) -> None:
        """Shift by the mean, scale by the standard deviation."""
        fitted = {}
        for feat in data.fields:
            values = _values(data[feat])
            fitted[feat] = (float(np.mean(values)), float(np.std(values)))

        self._record(fitted)

    def _robust_axov4_fit(self, data: ak.Array, percentiles: list, scale: list) -> None:
        """Robust, with the quantile range mapped onto the interval ``scale``.

        ``scale = [2, -2]`` puts the quantile range between -2 and 2 rather than between
        0 and 1, which is the convention the axol1tl v4 and v5 trainings were run with.
        """
        width = scale[0] - scale[1]
        fitted = {}
        for feat in data.fields:
            low, high = np.quantile(_values(data[feat]), percentiles)
            fitted[feat] = (
                (low * scale[0] - high * scale[1]) / width,
                (high - low) / width,
            )

        self._record(fitted)

    def _record(self, fitted: dict) -> None:
        """Store one object's parameters, guarding the degenerate scale of a flat feature."""
        self.norm_params[self.obj_name] = {
            feat: {"shift": shift, "scale": scale if scale else 1e-12}
            for feat, (shift, scale) in fitted.items()
        }


def _values(feature: ak.Array) -> np.ndarray:
    """One feature's real entries, the padding not yet being there to exclude."""
    return ak.to_numpy(ak.flatten(feature))
