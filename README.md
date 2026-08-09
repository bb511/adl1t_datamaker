[![Email Badge](https://img.shields.io/badge/blah-podagiu%40ethz.ch-blue?style=flat-square&logo=minutemailer&logoColor=white&label=%20&labelColor=grey)](mailto:podagiu@ethz.ch)
[![Python: version](https://img.shields.io/badge/python-3.10-blue?style=flat-square&logo=python)](https://www.python.org/downloads/)
[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.21787779-blue?style=flat-square&logo=doi)](https://doi.org/10.5281/zenodo.21787779)

# Level 1 Trigger data for the global trigger

The CMS Level-1 Trigger decides on each bunch crossing from a deliberately small view of
the detector: at most a handful of muons, jets, egammas, and taus, six energy sums, and
one decision bit per trigger algorithm, all fixed-width hardware integers. This
repository extracts that view from L1Ntuple root files and writes it as parquet, one
folder per object. Everything else in the ntuple is dropped: float reconstructions, the
objects of neighbouring bunch crossings, and detector-level branches that never reach
the trigger boards. [`docs/README.md`](docs/README.md) specifies every surviving
feature, with its bit width, hardware unit, and physical range, and the code is tested
against it.

A release built with this code is published at
[10.5281/zenodo.21787779](https://doi.org/10.5281/zenodo.21787779) under CC0. That
grant covers the released data; the repository ships no licence of its own.

## What the conversion produces

The conversion writes one directory per data set, one subdirectory per object, and
inside each one parquet file per input ntuple, named after the ntuple's stem. Row $i$
of every folder is the
same event, so the folders can be read separately and joined by position.

```
<data set>/
  muons/  jets/  egammas/  taus/    jagged: one entry per in-time object, nothing padded
  ET/  HT/  MET/  MHT/  FET/  FHT/  one entry per event, stored as a length-1 list
  event_info/                       run, lumi, event, bx, orbit, time, nPV_True
  seeds/                            one boolean column per unprescaled algorithm, and L1bit
  cica/                             the CICADA anomaly score, flat, where available
```

Only bunch crossing zero is kept: no event is lost, but the crossing an object came
from cannot be recovered afterwards. `L1bit` is synthesised as the logical OR of the
algorithm columns beside it. The `cica` folder appears only where a calorimeter summary
tree was configured, which the unpacked 2025 zero-bias ntuples lack. Values stay in
hardware units, and `docs/README.md` gives the conversion factors; the exception is
`nPV_True`, which in recorded data holds the brilcalc average pileup of the luminosity
section.

## Setup

The repository requires `python >= 3.10`. Reading the published data needs only the
package, and nothing from CERN:

```
pip install "adl1t-datamaker @ git+https://github.com/bb511/adl1t_datamaker.git@master"
```

The package is not on PyPI, and the `@master` matters: a stale `main` branch still
exists on the GitHub mirror.

Converting needs the full environment, managed with
[poetry](https://python-poetry.org/). From the repository root:

```
poetry install                   # add --extras xrootd to read inputs over root://
```

The xrootd extra is optional because its wheel builds from source and needs cmake and a
C++ toolchain; without it, globbing a `root://` path fails with an error that names the
fix. `requirements.txt` holds the resolved pins exported from `poetry.lock`.

### Tests

```
poetry install --with dev
poetry run pytest
```

The suite is a minimal core and runs entirely offline: the converter's feature lists
against `docs/README.md`, the sum-type map, the prescale menus, the brilcalc pileup
join, the overwrite guard, and the loader on a synthetic parquet tree.

### Docker

The `Dockerfile` (BuildKit) builds on `alma9-base` with the EOS and xrootd clients, so
a conversion inside it can read `root://` given a Kerberos ticket. The default target,
`production`, carries the package alone; `development` adds `tests/`, `docs/`, and the
dev group. The summary and publish tooling parses `docs/README.md` from the source
tree, so it needs `development` or a checkout. No image is published; build locally.

## Usage

Run every script from the repository root: the default pileup folder and the prescale
menu paths resolve against it. `scripts/run.snip` holds a worked example of each
conversion and summary command, and
[`scripts/README.md`](scripts/README.md) documents the scripts, the
configuration, and the auxiliary files in full.

### Converting

`./scripts/convert` converts one ntuple and `./scripts/convert_folder` a folder of
them, `--ncores` at a time. Each needs the input, the prescale menu that selects the
trigger algorithms, and an output path, and each defaults to the emulated trees;
`--mc` marks simulation and skips the brilcalc pileup join. In practice, `convert_run` reads a campaign config from
`scripts/configs/experiment/` and converts everything the config names:

```
./scripts/convert_run +experiment=EphZB_2025G_run398183 output_root_path=./parquet_files
```

### Summarising

```
./scripts/summary --folder parquet_files/EphZB_2025G_run398183
./scripts/summary_run +experiment=EphZB_2025G_run398183 output_root_path=./parquet_files
./scripts/summary_comparison --folder1 A --folder2 B --output_folder OUT
```

`summary` writes a `SUMMARY` directory into the data folder: figures, a `REPORT.md`,
and a `summary.json` covering provenance, the file inventory with digests, every column
against its specification, and a validation checklist. Nothing is sampled: one
streaming pass counts every value, and each statistic follows from the counts.
`summary.json` also records the per-shard manifest and the raw counts, so it is the
artefact worth keeping. `summary_run` summarises every folder of a campaign and
records the config as provenance. `summary_comparison` overlays two data sets and
writes their differences, which is how a reconversion gets validated.

### Publishing

```
./scripts/publish/publish --out <release folder>
```

This partitions a converted data set into the train, valid, and test archives, writes
the dataset card and the licence beside them, and records the checksums. The partition
is a frozen map that must already sit under `--out`; see
[`scripts/publish/README.md`](scripts/publish/README.md).

### Reading the data

```python
from adl1t_datamaker.loader import Parquet2Awkward

data = Parquet2Awkward("parquet_files/EphZB_2025G_run398183")

data.object_names             # the object folders found
muons = data["muons"]         # ak.Array, the whole folder in memory
muons.muonIEt                 # jagged: one list of in-time muons per event

for batch in data("muons"):   # the same content, streamed
    ...
```

Indexing reads an object whole; calling streams it in batches of `bs` events, one
million by default. `select_feats={"muons": ["muonIEt"], "seeds": None}` narrows the
read: `None` keeps every column of that object, and an object left out is not read.
The loader takes local paths only.

Two things catch people out. Only `cica` is flat; every other column carries a list
layer, so a seed reads as `data["seeds"].L1bit[:, 0]` and a sum as
`data["ET"].Et[:, 0]`. And batches from two folders are not aligned, because pyarrow
takes its boundaries from each folder's own row groups, so join folders shard by shard
rather than by zipping streams.

## Repository layout

| Path | Contents |
| --- | --- |
| `src/adl1t_datamaker/` | the package |
| `scripts/` | entry points, hydra configs, prescale menus, and brilcalc pileup files |
| `docs/` | the feature specification, and the CMS documents behind it |
| `tests/` | the minimal offline suite; the code must match `docs/README.md` |
| `notebooks/` | two analyses; neither runs any more (`pileup_vs_towers` predates the parquet rewrite, `zero_values_analysis` used the deleted `figures.plot_feature_from_array`) |

| Module | Role |
| --- | --- |
| `root2parquet` | reads the ntuple trees and writes the object folders |
| `loader` | reads them back, whole or streamed |
| `components.l1_seeds` | the prescale menu and the trigger decision bits |
| `components.pileup` | the brilcalc pileup join for recorded data |
| `schema` | parses `docs/README.md` into the feature specification |
| `summary/` | the summary chain: exact counting, one streaming pass, checks, report, figures, and the comparison |
| `publish` | the release: partition, card, archives, and HuggingFace mirror |
| `util`, `terminal_colors` | path handling across local and `root://`, and console colour |

## Contact

Patrick Odagiu, `podagiu@ethz.ch`. Mirrored at
[github.com/bb511/adl1t_datamaker](https://github.com/bb511/adl1t_datamaker) and on the
CERN GitLab at `cms-l1-ad/data_converter`.
