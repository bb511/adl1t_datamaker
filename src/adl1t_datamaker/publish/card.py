# The dataset card and licence that ship inside the published record.
#
# Every number the card quotes is derived from the data itself. The event counts come from
# the frozen split summary; the unit factors, hardware bit widths and collection
# capacities come from schema.py, which reads docs/README.md; the constituent counts
# come from the reader the record ships.

import textwrap

from adl1t_datamaker import schema

SPLITS = ("train", "valid", "test")

# The mirror the HuggingFace card's examples load from.
REPO_ID = "podagiu/anomaly_detection_cmsl1t"

# Width the card's prose is reflowed to. Zenodo shows the rendered markdown, but a
# reader who opens the file sees the raw text, and the substituted counts are long
# enough to leave the template's own line breaks ragged.
WRAP = 88

# Plural names the card uses for the collections, which are not the directory names.
DISPLAY = {"muons": "muons", "jets": "jets", "egammas": "e-gammas", "taus": "taus"}

# Rows of the unit table: the label, a collection carrying the same scales as every
# collection on that row, and the branches supplying the Et, eta and phi columns. None
# marks a column the collection has no field for.
UNIT_ROWS = (
    ("muons", "muons", ("muonIEt", "muonIEta", "muonIPhi")),
    ("jets", "jets", ("jetIEt", "jetIEta", "jetIPhi")),
    ("e-gammas", "egammas", ("egIEt", "egIEta", "egIPhi")),
    ("taus", "taus", ("tauIEt", "tauIEta", "tauIPhi")),
    ("ET, HT", "ET", ("Et", None, None)),
    ("MET, MHT, FET, FHT", "MET", ("Et", None, "phi")),
)

LICENCE = """CC0 1.0 Universal Public Domain Dedication

The person who associated a work with this deed has dedicated the work to the
public domain by waiving all rights to the work worldwide under copyright law,
including all related and neighbouring rights, to the extent allowed by law.

You can copy, modify, distribute and use the work, even commercially, without
asking permission.

Deed:        https://creativecommons.org/publicdomain/zero/1.0/
Legal code:  https://creativecommons.org/publicdomain/zero/1.0/legalcode

Attribution is not legally required. It is still requested as a scholarly
courtesy: cite this record by its DOI, and the accompanying data descriptor once
it is published.
"""

CARD = """# Trigger Anomaly Detection for New Physics at the LHC

This dataset contains Level-1 Trigger objects from the CMS experiment at the CERN Large Hadron Collider, assembled for research on unsupervised anomaly detection in the trigger.
The goal of unsupervised anomaly detection in this context is the discovery of new physics.
**This data set does not contain new physics. It is meant for research on anomaly detectors.**

In the new physics search context, recording true anomalies or simulating them is impossible, compared to other settings (e.g. industrial applications of anomaly detection) where this is commonly done.
Anomaly simulation data sets are provided, but they should be used with the aforementioned caveat in mind. Aside from its high statistics, **this data set uniquely provides simulations of the normal data**.

* **normal data**: zero-bias events recorded during 2025 proton–proton running (runs 396102 and 398183); these events are chosen at random from all the proton-proton collisions that happen inside the CMS detector and are recorded by it.

* **anomaly simulations**: 20 simulated signal data sets covering Higgs, multi-Higgs, SUSY and exotic scenarios from the CMS Run 3 Winter25 campaign.

* **normal data simulation**: one simulated zero-bias-like background sample (SingleNeutrino).

The normal data has 20,887,636 events.
The normal data simulation has 2,000,000 events.
The 20 anomaly simulations amount to 13,012,931 events.

Each event provides particle level and event information, as recorded by the trigger.
The data is published pre-partitioned into training, validation and test splits: the zero-bias data 60/20/20, the simulated samples 60/40 between validation and test.
All the feature values are in the trigger-native format of hardware integers.

Specific technical data can be found in the github repo that was used to produce this data: https://github.com/bb511/adl1t_datamaker
The data were produced at commit `16dcaac` of that repository.

## Layout

The three tar files in the record contain the following directory structure:

```
zerobias/<run>/{{train,valid,test}}/<object>/*.parquet
signal/<sample>/{{valid,test}}/<object>/*.parquet
background/<sample>/{{valid,test}}/<object>/*.parquet
```

The zero bias constitutes `train.tar` by itself.
The simulated anomaly samples, as well as the simulated background sample only appear in `valid.tar` and `test.tar`, together with zero-bias.

Each subdirectory is a different object that contains its collection of parquet files.
Every collection of a split has the same rows in the same order, so row *i* of `jets/` and row *i* of `muons/` describe one event.
That position is the only correspondence that always holds.
**Neither `order` nor the `event` entry fulfils this same role.**


## Comparison with other trigger algorithms

The level-1 trigger menu contains hundreds of algorithms that take data, like the one present in this record, and output a decision.
All of them ran on every event of the presented data sets, outputting a decision.
The results are stored in the `seeds` folder and can be used to do comparative studies between your anomaly detection algorithm and the standard algorithms running in the CMS trigger.
The trigger's own anomaly detection algorithms, `L1_AXO_*` and `L1_CICADA_*`, are left out, since benchmarking an anomaly detector against the decisions of another anomaly detector would be circular.
The folder also contains an `L1bit` field, which encodes the logical OR of the algorithm columns deposited beside it.
Skip the `seeds` folder if you want kinematics alone and do not want to compare your anomaly detector with the rest of the algorithms.

## Splits

The zero-bias data are split 60/20/20.
The simulated samples are validation-only and are split 60/40 between `valid` and `test`.

| split | events |
|---|---|
{split_table}

The split was drawn once with NumPy's PCG64 generator seeded with **seed={seed}**.
The two zero-bias runs concatenated in the order: `{zb_order}`.

## Units

Each feature of each object has values that are integer hardware units, as the trigger produces them.
Nothing in the files is scaled.
Multiply by these to get GeV, radians and pseudorapidity:

| collection | Et | eta | phi |
|---|---|---|---|
{units_table}

The decimals are rounded.
The steps are exact fractions: calorimeter eta is 0.0870/2, muon eta is 0.0870/8, calorimeter phi is 2pi/144, and muon phi is 2pi/576.
`muonIEtaAtVtx` and `muonIPhiAtVtx` have the same scales as muon eta and phi.
Three energy columns are missing from the table: the `muonIEtUnconstrained` counts 1 GeV per unit, `ETTEM` takes the same 0.5 GeV as the `Et` of `ET`, and `jetRawEt` has no documented scale, but it's probably 1 GeV per step.
The muon energies also carry an offset, since the hardware `0` marks the absence of a muon: the momentum is (`muonIEt` - 1) x 0.5 GeV and the unconstrained momentum is (`muonIEtUnconstrained` - 1) GeV.
No other collection has such an offset.
Quality, charge, isolation, index, and tower-count fields are already integers and unscaled, as is every `seeds` bit and every `event_info` field.
The only exception is `nPV_True`, which is a float32 average per luminosity section in the zero bias and in `haa-4b-ma15`, and an integer count in the other simulations.

The four object collections are jagged: they have one entry per in-time object up to the global trigger's capacity of {capacities}.


## Caveats

**Ordering.**
Objects arrive in the trigger's readout order, which is ET-descending for the calorimeter objects.
This is not true for the muons, except in `haa-4b-ma15`, whose overlay sorted every collection.

**`haa-4b-ma15` carries overlaid pile-up.**
The sample was simulated without pile-up, and each of its events is the merge of the simulated event with one zero-bias event of the same split, at the level of the trigger objects.
The partner events were drawn without replacement with NumPy's PCG64 generator seeded with **{overlay_seed}** from the two zero-bias runs concatenated as `{zb_order}`; they remain in the zero-bias splits.
All the drawn events come from `val` and 'test', for each stage.
The four collections are concatenated, ordered by `Et` and cut at the trigger's capacity of {capacities}; `ET`, `HT` and the tower count are added and clipped at their all-ones code; `MET`, `MHT`, `FET` and `FHT` are added as vectors and quantised back to their codes.
The sample only approximates a simulation with pile-up.
Its seeds are the OR of the two events' decisions over the simulation menu and `L1bit` the OR of those seeds.
Its `event_info` is the zero-bias partner's: the sample has real beam coordinates and a float32 `nPV_True`.

**The menu differs between data and simulation.**
Zero bias has 178 algorithm columns and simulation has 158, of which 145 are shared.
The two data sets do not have the same order for the trigger algorithms in their corresponding menus.
Therefore, please select seeds by name, not by position.

**`nPV_True` has two types.**
It is float32 in zero bias and in `haa-4b-ma15`, and int32 in the other simulations.

**Simulation has no beam coordinates in `event_info`.**
Every simulated sample except `haa-4b-ma15` has `run` of 1, `bx` of 4294967295, and `orbit` of 18446744073709551615, the all-ones codes of their types.
The zero bias data has non-trivial values for these fields, and `haa-4b-ma15` carries those of its zero-bias partner.

**`jetRawEt` is zero throughout the zero-bias data.**
The branch is unfilled in original data ntuples, though it contains real values in simulation.
In `haa-4b-ma15` it is zero for the jets that came from the zero-bias partner.


## Standard Preprocessing

Multiple studies were done internally at CERN on this data set.
A number of conventional preprocessing steps were applied in each of these studies.
Therefore, `event_info` contains two columns that the raw data does not: `split`, so a file separated from its directory is still self-describing, and `order`, the position in that ordering, which is `-1` for the events that the conventional preprocessing removed.
Links to the papers detailing these studies will be attached here once these studies become public.

The standard steps involve dropping an event whose total `ET` reached the all-ones code of its 12 bits, 4095, and removing the muons, e-gammas and taus whose `Et` reached 511, the jets whose `Et` reached 2047, and the `MET` or `FET` that reached 4095.
Each threshold is the all-ones code of that object's own energy width, so exactly the saturated objects are removed, and a removed object does not count towards the multiplicity.

**A split can span several directories.**
The two zero-bias runs were permuted together, so their training rows interleave and `order` counts across the whole split rather than within one run.
To rebuild the study's order, read both run directories, concatenate them, then stable-sort by `order` with the `-1` rows left at the end.
Concatenating one run after the other gives the right rows in the wrong order.

## Provenance

Zero-bias data: CMS, 2025, runs {runs}.
Simulated samples: CMS Run 3 Winter25 campaign; `haa-4b-ma15` from its no-pile-up production (`142XnoPU`), with pile-up overlaid from the zero-bias data as the caveats describe.
The values are the Level-1 trigger's own reconstructed objects rather than offline reconstruction.

## Licence

CC0 1.0, a public domain dedication with no restrictions on reuse. See `LICENSE`.
Citation by DOI is requested as a courtesy, not required.

## Contact

Questions and problems are welcome as a discussion on the HuggingFace dataset page, or as an issue on the repository that produced it: https://github.com/bb511/adl1t_datamaker.

## Release approval

The public release of this data set was approved at the CMS Collaboration Board meeting of 15 May 2026: https://indico.cern.ch/event/1683535/
"""


CARD_HF = """# Trigger Anomaly Detection for New Physics at the Large Hadron Collider

*This dataset is a mirror of the Zenodo record: https://doi.org/10.5281/zenodo.21787779*

This dataset contains Level-1 Trigger objects from the CMS experiment at the CERN Large Hadron Collider, assembled for research on unsupervised anomaly detection in the trigger.
The goal of unsupervised anomaly detection in this context is the discovery of new physics.
**This data set does not contain new physics. It is meant for research on anomaly detectors.**

In the new physics search context, recording true anomalies or simulating them is impossible, compared to other settings (e.g. industrial applications of anomaly detection) where this is commonly done.
Anomaly simulation data sets are provided, but they should be used with the aforementioned caveat in mind. Aside from its high statistics, **this data set uniquely provides simulations of the normal data**.

* **normal data**: zero-bias events recorded during 2025 proton–proton running (runs {runs}); these events are chosen at random from all the proton-proton collisions that happen inside the CMS detector and are recorded by it.

* **anomaly simulations**: {n_signal} simulated signal data sets covering Higgs, multi-Higgs, SUSY and exotic scenarios from the CMS Run 3 Winter25 campaign.

* **normal data simulation**: one simulated zero-bias-like background sample (SingleNeutrino).

The normal data has {zerobias_total:,} events.
The normal data simulation has {background_total:,} events.
The {n_signal} anomaly simulations amount to {signal_total:,} events.

Each event provides particle level and event information, as recorded by the trigger.
The data is published pre-partitioned into training, validation and test splits: the zero-bias data 60/20/20, the simulated samples 60/40 between validation and test.
All the feature values are in the trigger-native format of hardware integers.

Specific technical data can be found in the github repo that was used to produce this data: https://github.com/bb511/adl1t_datamaker
The data were produced at commit `16dcaac` of that repository.

## Comparison with other trigger algorithms

The level-1 trigger menu contains hundreds of algorithms that take data, like the one present in this record, and output a decision.
All of them ran on every event of the presented data sets, outputting a decision.
The results are stored in the `seeds` folder and can be used to do comparative studies between your anomaly detection algorithm and the standard algorithms running in the CMS trigger.
The trigger's own anomaly detection algorithms, `L1_AXO_*` and `L1_CICADA_*`, are left out, since benchmarking an anomaly detector against the decisions of another anomaly detector would be circular.
The folder also contains an `L1bit` field, which encodes the logical OR of the algorithm columns deposited beside it.
Skip the `seeds` folder if you want kinematics alone and do not want to compare your anomaly detector with the rest of the algorithms.

Row *i* of `<data set>-seeds` is row *i* of `<data set>`, which is the correspondence that always holds.
Neither column is a key on its own: every event the standard preprocessing dropped carries `order = -1`, and `event` cycles over a hundred values in `ggH-suep-decay` and `smj-case-A`.
Among the rows with `order >= 0` it is unique within a split, so a filter or a shuffle can be undone by joining on `order` once those rows are set aside.

## Loading

Every data set is a configuration of its own, and every one of them has a `-seeds` twin holding the other algorithm decisions for the same events in the same order.

```python
from datasets import load_dataset
normal = load_dataset("{repo}", "ZB_run396102", split="train")
signal = load_dataset("{repo}", "WtoTauto3Mu", split="validation")
menu = load_dataset("{repo}", "WtoTauto3Mu-seeds", split="validation")
```

HuggingFace calls the middle split `validation` while our files call it 'valid'.
We also include a dataloader that we used for performing anomaly detection trigger development on this data.
It reads the data, applies our cuts and normalisation, and stacks the collections into pytorch tensors that can be directly fed into models.

```python
import sys
from huggingface_hub import snapshot_download
from hydra import compose, initialize_config_dir
from hydra.utils import instantiate
record = snapshot_download("{repo}", repo_type="dataset")
sys.path.insert(0, record)  # the configs name loader.*, so the record has to be importable
with initialize_config_dir(config_dir=record + "/configs", version_base=None):
    cfg = compose("config", overrides=["paths.root_dir=" + record])
data = instantiate(cfg.data)
data.prepare()
train = data.load("train")
```

`prepare` reads the whole record and caches each stage under `./cache`, which the `ADL1T_CACHE` environment variable moves elsewhere; allow it a few times the record's size on disk.
`train` then has `x`, the model input, of shape (events, 39, 3) under the `basis` configuration, its padding `mask`, whether the event passed ANY other algorithm in the trigger `l1bit` and the label `y` (0 for zerobias, > 0 for anomalies, < 0 for zerobias simulation).
`data.load_aux("valid")` returns the same for every simulated sample.
The pipeline needs python 3.10 or newer with `awkward`, `pyarrow`, `numpy`, `torch`, `omegaconf` and `hydra-core`, which `pip install -r requirements.txt` at the record's root installs.
**If you would just rather read the raw data, you need none of the above dependencies.**
Just call `load_dataset`.

## Layout

```
data/<data set>/<split>-NNNNN-of-NNNNN.parquet
data/<data set>/seeds/<split>-NNNNN-of-NNNNN.parquet
loader/
configs/
requirements.txt
```

One row is one event.
The four object collections are jagged, holding one entry per in-time object up to the global trigger's capacity of {capacities}, with no padding and no truncation.
The energy sums are collections too, of one entry each. The event information, the trigger's verdict and every seed are plain values.

## Columns

| column | holds |
|---|---|
| `<collection>_<branch>` | one collection's features, e.g. `muons_muonIEt` or `jets_jetIEta`. The collections are `muons`, `jets`, `egammas`, `taus` and the energy sums `ET`, `HT`, `MET`, `MHT`, `FET`, `FHT`, and the branch names are the trigger's own |
| `run`, `lumi`, `event`, `bx`, `orbit`, `time`, `nPV_True` | event information, carried without a prefix |
| `split`, `order` | the published partition and the position within it, described below |
| `L1bit` | whether the trigger accepted the event, i.e. the OR over the algorithm columns deposited in the `-seeds` config |
| `dataset` | the data set the row came from, so that a concatenation stays self-describing |
| `label` | 0 for zero bias, negative for a simulated background, positive for a signal |

**A column prefixed by a collection is a list, and every other column is a plain value.**
The collections have one entry per object in the event.
The energy sums have a single entry (list with one value).
Everything else contains one value: `row["L1bit"]` is `True`, `row["event"]` is an integer, and `ds.filter(lambda r: r["L1bit"])` selects the events the trigger accepted.
A `-seeds` config has one boolean column per trigger algorithm and four other columns: `L1bit`, `dataset`, `event` and `order`.
The trigger's own anomaly detection algorithms, `L1_AXO_*` and `L1_CICADA_*`, are left out, since benchmarking an anomaly detector against the decisions of another anomaly detector would be circular.

## Data sets

| config | label | train | valid | test |
|---|---|---|---|---|
{config_table}

## Units

Each feature of each object has values that are integer hardware units, as the trigger produces them.
Nothing in the files is scaled.
Multiply by the following to get GeV, radians and pseudorapidity:

| collection | Et | eta | phi |
|---|---|---|---|
{units_table}

The decimals are rounded.
The steps are exact fractions: calorimeter eta is 0.0870/2, muon eta is 0.0870/8, calorimeter phi is 2pi/144, and muon phi is 2pi/576.
`muons_muonIEtaAtVtx` and `muons_muonIPhiAtVtx` take the same scales as muon eta and phi.
Three energies are missing from the table: `muons_muonIEtUnconstrained` is 1 GeV per unit rather than 0.5, `ET_ETTEM` takes the same 0.5 GeV as `ET_Et`, and `jets_jetRawEt` has no documented scale, but it's probably 1 GeV per step.
The muon energies also carry an offset, since the hardware `0` marks the absence of a muon: the momentum is (`muons_muonIEt` - 1) x 0.5 GeV and the unconstrained momentum is (`muons_muonIEtUnconstrained` - 1) GeV.
Quality, charge, isolation, index and tower-count fields are already integers and unscaled, as is every seed and every event information field except `nPV_True`, which is a float32 average per luminosity section in the zero bias and in `haa-4b-ma15`, and an integer count in the other simulations.

## Caveats

**Ordering.**
Objects arrive in the trigger's readout order, which is ET-descending for the calorimeter objects.
This is not the case for the muons, except in `haa-4b-ma15`, whose overlay sorted every collection.
The shipped loader sorts objects by ET before processing them.

**`haa-4b-ma15` carries overlaid pile-up.**
The sample was simulated without pile-up, and each of its events is the merge of the simulated event with one zero-bias event of the same split, at the level of the trigger objects.
The partner events were drawn without replacement with NumPy's PCG64 generator seeded with **{overlay_seed}** from the two zero-bias runs concatenated as `{zb_order}`; they remain in the zero-bias splits.
All the drawn events come from `val` and 'test', for each stage.
The four collections are concatenated, ordered by `Et` and cut at the trigger's capacity of {capacities}; `ET`, `HT` and the tower count are added and clipped at their all-ones code; `MET`, `MHT`, `FET` and `FHT` are added as vectors and quantised back to their codes.
The sample only approximates a simulation with pile-up.
Its seeds are the OR of the two events' decisions over the simulation menu and `L1bit` the OR of those seeds.
Its `event_info` is the zero-bias partner's: the sample has real beam coordinates and a float32 `nPV_True`.

**The menu differs between data and simulation.**
Zero bias data has 178 algorithm columns and the simulations have 158, of which 145 are shared.
Additionally, the order of the other trigger algorithm decisions is not the same between zerobias and simulations.

**`nPV_True` has two types.**
It is float32 in zero bias and in `haa-4b-ma15`, and int32 in the other simulations.

**Simulation carries no beam coordinates.**
Every simulated sample except `haa-4b-ma15` has `run` of 1, `bx` of 4294967295 and `orbit` of 18446744073709551615, the all-ones codes of their types, in place of the values a collision would have.
The zero bias has non-trivial values in these fields, and `haa-4b-ma15` carries those of its zero-bias partner.

**`jetRawEt` is zero throughout the zero-bias data.**
The branch is unfilled in original data ntuples, though it has real values in simulation.
In `haa-4b-ma15` it is zero for the jets that came from the zero-bias partner.

## Standard preprocessing

Multiple studies were done internally at CERN on this data set.
A number of conventional preprocessing steps were applied in each of these studies.
Therefore the record contains two columns that the raw data does not: `split`, so a file separated from its directory is still self-describing, and `order`, the position in that ordering, which is `-1` for the events that the conventional preprocessing removed.
Links to the papers detailing these studies will be attached here once these studies become public.

The split was drawn once with NumPy's PCG64 generator seeded with **{seed}**, over the two zero-bias runs concatenated in the order `{zb_order}`.

**A split can span two configs.**
The two zero-bias runs were permuted together.
Their training rows interleave and `order` counts across the whole split rather than within one run.
To rebuild the same order as in previous studies, read both zero-bias configs, concatenate them, then stable-sort by `order` with the `-1` rows left at the end.
Concatenating one run after the other gives the right rows in the wrong order.

The pipeline in `loader/` goes through the standard preprocessing steps.
In the four stages the studies used: read the tables into one array per collection, drop the events saturated in ET and remove the saturated objects, fit the normalisation on the training split alone and apply it to every other split, then pad each collection to a fixed number of constituents and stack them into one tensor.
That object cut is `Et < 511` for muons, e-gammas and taus, `Et < 2047` for jets and `Et < 4095` for `MET` or `FET`, each the all-ones code of the object's own energy width, so this cut removes saturated objects.
The events cut by this pipeline have the `order` set to `-1`: run over the zero bias it removes the {dropped:,} events marked `-1`, {dropped_pct} of them.

## Provenance

Zero-bias data: CMS, 2025, runs {runs}. Simulated samples: CMS Run 3 Winter25 campaign; `haa-4b-ma15` from its no-pile-up production (`142XnoPU`), with pile-up overlaid from the zero-bias data as the caveats describe.
The values are the Level-1 trigger's own reconstructed objects rather than offline reconstruction.

## Citation

Cite the Zenodo record that this dataset mirrors.
The data descriptor is not published yet; its citation will be added here once it is.

```bibtex
@dataset{{cms_l1t_anomaly_2026,
  author    = {{{{CMS Collaboration}}}},
  title     = {{Trigger Anomaly Detection for New Physics at the Large Hadron Collider}},
  year      = {{2026}},
  publisher = {{Zenodo}},
  version   = {{1.0}},
  doi       = {{10.5281/zenodo.21787779}},
  url       = {{https://doi.org/10.5281/zenodo.21787779}}
}}
```

## Licence

CC0 1.0, a public domain dedication with no restrictions on reuse. See `LICENSE`.
Citation by DOI is requested as a courtesy, not required.

## Contact

Questions and problems are welcome as a discussion on this dataset's page, or as an issue on the repository that produced it: https://github.com/bb511/adl1t_datamaker.

## Release approval

The public release of this data set was approved at the CMS Collaboration Board meeting of 15 May 2026: https://indico.cern.ch/event/1683535/
"""


def render(summary: dict) -> str:
    """Fill the card from the frozen split summary and the producer's own schema.

    The "What version 2 corrects" section is specific to this release rather than
    generated, so a later version has to rewrite it.

    :param summary: Contents of ``metadata/split_summary.json``. Its
        ``dataset_version`` is deliberately not read, because that file travels with the
        release unchanged and still names the version it was first written for.
    """
    return _rewrap(
        CARD.format(
            split_table=split_table(summary["datasets"]),
            seed=summary["split_seed"],
            units_table=units_table(),
            capacities=capacities(),
            overlay_seed=overlay_seed(summary),
            **event_counts(summary["datasets"]),
        )
    )


def render_hf(summary: dict, labels: dict) -> str:
    """Fill the HuggingFace card, which describes the mirror rather than the archives.

    :param summary: Contents of ``metadata/split_summary.json``.
    :param labels: ``{data set: label}``, as ``publish.huggingface`` assigns them. Passed
        in rather than imported, so that the card stays independent of the mirror.
    """
    datasets = summary["datasets"]

    return _rewrap(
        CARD_HF.format(
            repo=REPO_ID,
            config_table=config_table(datasets, labels),
            seed=summary["split_seed"],
            units_table=units_table(),
            capacities=capacities(),
            overlay_seed=overlay_seed(summary),
            **event_counts(datasets),
            **category_totals(datasets),
        )
    )


def event_counts(datasets: dict) -> dict:
    """Zero-bias totals the card quotes, and the runs that supplied them."""
    zerobias = {k: v for k, v in datasets.items() if v["category"] == "zerobias"}
    total = sum(v["raw_events"] for v in zerobias.values())
    dropped = total - sum(v["events_passing_filter"] for v in zerobias.values())

    return {
        "zb_events": total,
        "total_raw": total,
        "dropped": dropped,
        "dropped_pct": f"{100 * dropped / total:.4f}%",
        "zb_order": " then ".join(sorted(zerobias)),
        "runs": ", ".join(sorted(k.replace("ZB_run", "") for k in zerobias)),
        "n_signal": sum(1 for v in datasets.values() if v["category"] == "signal"),
    }


def overlay_seed(summary: dict) -> int:
    """Seed of the draw that paired the no-pile-up sample with its zero-bias partners."""
    return summary["overlay"]["haa-4b-ma15"]["seed"]


def split_table(datasets: dict) -> str:
    """The events table, zero bias split by split and every simulated sample on one row."""
    rows = [
        f"| zero-bias {split} | {_split_total(datasets, split):,} |"
        for split in SPLITS
        if _split_total(datasets, split)
    ]
    rows += [
        f"| {name} valid / test | {datasets[name]['counts'].get('valid', 0):,}"
        f" / {datasets[name]['counts'].get('test', 0):,} |"
        for name in sorted(
            k for k, v in datasets.items() if v["category"] != "zerobias"
        )
    ]

    return "\n".join(rows)


def units_table() -> str:
    """The hardware-to-physical factors, one row per group of collections."""
    return "\n".join(
        f"| {label} | " + " | ".join(_factor(obj, feat) for feat in feats) + " |"
        for label, obj, feats in UNIT_ROWS
    )


def capacities() -> str:
    """The global trigger's per-event capacity for each object collection."""
    documented = schema.documented_capacities()

    return _listed([f"{documented[obj]} {name}" for obj, name in DISPLAY.items()])


def config_table(datasets: dict, labels: dict) -> str:
    """One row per config: its label and the events it holds in each split.

    The mirror's unit is the data set, where the archives merge the two zero-bias runs,
    so this table is per run rather than per split.
    """
    rows = [
        f"| `{name}` | {labels[name]} | "
        + " | ".join(_count(datasets[name], split) for split in SPLITS)
        + " |"
        for name in sorted(datasets)
    ]

    return "\n".join(rows)


def category_totals(datasets: dict) -> dict:
    """Published events per category. Every raw event is published, none were dropped."""
    totals = {"zerobias": 0, "background": 0, "signal": 0}
    for meta in datasets.values():
        totals[meta["category"]] += sum(meta["counts"].values())

    return {f"{category}_total": count for category, count in totals.items()}


def _count(meta: dict, split: str) -> str:
    """One cell of the config table, blank where the data set has no such split."""
    events = meta["counts"].get(split, 0)

    return f"{events:,}" if events else " "


def _split_total(datasets: dict, split: str) -> int:
    """Zero-bias events in one split, summed over the runs that contribute to it."""
    return sum(
        v["counts"].get(split, 0)
        for v in datasets.values()
        if v["category"] == "zerobias"
    )


def _factor(obj: str, feature: str | None) -> str:
    """One unit-table cell, blank where the collection has no such field."""
    if feature is None:
        return " "

    scale, unit = schema.unit_scale(obj, feature)

    return f"{scale:.6g}" if unit == "eta" else f"{scale:.6g} {unit}"


def _listed(items: list[str]) -> str:
    """Join with commas and a final 'and', as prose rather than as a list."""
    return ", ".join(items[:-1]) + f" and {items[-1]}" if len(items) > 1 else items[0]


def _rewrap(text: str) -> str:
    """Reflow the prose, leaving headings, tables and fenced blocks as they are."""
    return "\n\n".join(
        block if block.startswith(("#", "|", "```")) else _fill(block)
        for block in text.split("\n\n")
    )


def _fill(block: str) -> str:
    """Wrap one paragraph without splitting identifiers such as ``adl1t-l1ad``."""
    return textwrap.fill(
        " ".join(block.split()),
        width=WRAP,
        break_long_words=False,
        break_on_hyphens=False,
    )
