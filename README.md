# Level 1 Trigger data for the global trigger

The CMS Level-1 Trigger records one event per bunch crossing, and it
decides from a deliberately small view of the detector: at most a handful of muons, jets,
egammas, and taus, six energy sums, and one decision bit per trigger algorithm, all
carried as fixed-width hardware integers. This repository extracts that view from L1Ntuple
root files and writes it as parquet, one folder per object.

Most of what an L1Ntuple carries is dropped: float reconstructions of the same quantities,
objects from the two bunch crossings on either side of the one that fired, and
detector-level branches that never reach the trigger boards.
[`docs/README.md`](docs/README.md) lists every feature that survives, together with its
bit width, its hardware unit, and its physical range. It is the specification the code is
tested against rather than a description written after the fact.

A release built with this code is published at
[10.5281/zenodo.21787779](https://doi.org/10.5281/zenodo.21787779) under CC0. That grant
covers the released data; this repository ships no licence of its own. The tooling that
builds the release lives in `scripts/publish` and has
[its own README](scripts/publish/README.md).

## What the conversion produces

The conversion writes one directory per data set, with one subdirectory per object, and
inside each one parquet file per input ntuple, named after that ntuple's stem and
compressed with snappy. Row $i$ of every object folder is the same event, which is what
lets the folders be read separately and joined by position.

```
<data set>/
  muons/  jets/  egammas/  taus/    jagged: one entry per in-time object, nothing padded
  ET/  HT/  MET/  MHT/  FET/  FHT/  one entry per event, stored as a length-1 list
  event_info/                       run, lumi, event, bx, orbit, time, nPV_True
  seeds/                            one boolean column per unprescaled algorithm, and L1bit
  cica/                             the CICADA anomaly score, flat, where available
```

Only the objects belonging to bunch crossing zero are kept, so no event is lost, but the
crossing an object came from cannot be recovered afterwards. `L1bit` is synthesised rather
than read, being the logical OR of the algorithm columns stored beside it. The `cica`
folder appears only where a calorimeter summary tree was configured, which the unpacked
ntuples of the 2025 zero-bias runs leave out. Values otherwise stay in hardware units, so
converting `jetIEt` to GeV is the reader's business and `docs/README.md` gives the factor.
The exception is `nPV_True`, which for recorded data holds the brilcalc average pileup of
the luminosity section rather than anything the trigger measured.

## Setup

This repository requires `python >= 3.10`.

### Reading published data

Reading needs only the package, and nothing from CERN:

```
pip install "adl1t-datamaker @ git+https://github.com/bb511/adl1t_datamaker.git@master"
```

The package is not on PyPI, so the git URL is the only route, and the `@master` matters
because a stale `main` branch still exists on the GitHub mirror. There is no reader-only
extra, so this pulls the full dependency set even though the reader itself imports only
`awkward` and `pyarrow`. See [Reading the data](#reading-the-data) below.

### Converting

Dependencies are managed with [poetry](https://python-poetry.org/). From the repository
root, where `pyproject.toml` lives:

```
poetry install
```

Add the xrootd extra to read inputs from EOS over `root://`:

```
poetry install --extras xrootd
```

The extra is optional because nothing on the reading side needs it, and because the
`xrootd` wheel is built from source and needs cmake and a C++ toolchain. The converter and
the loader both import cleanly without it, and when a `root://` path is globbed without it
the error names the fix.

The direct dependencies are declared in `pyproject.toml`, and `requirements.txt` holds the
fully resolved pins exported from `poetry.lock`.

### Tests

The test dependencies sit in an optional group, so a bare `poetry install` does not pull
pytest:

```
poetry install --with dev
poetry run pytest -m "not eos"
```

All but eight of the tests run offline. Those eight are marked `eos`, convert real ntuples
from `root://eoscms.cern.ch`, and need both the xrootd extra and a live Kerberos ticket
(`kinit you@CERN.CH`); if either is missing they skip rather than fail, and two of them
skip permanently because their inputs no longer exist on EOS. One test of the release
packer shells out to GNU tar, so it fails against a stock macOS `tar`.

What the suite pins is worth knowing before trusting a conversion: two conversions of the
same ntuple produce byte-identical parquet; two summaries of the same folder produce a
`REPORT.md` and a `summary.json` that differ only in the generated block; the converter's
feature lists are compared against the tables parsed out of `docs/README.md`; the sum type
of every energy column is fixed against the value it must have; and `convert_folder`
refuses to overwrite parquet written from a different input file.

### Docker

The `Dockerfile` builds on `alma9-base` and installs the EOS and xrootd clients, so a
conversion inside it can read `root://` given a Kerberos ticket. It defines five stages,
of which two are worth running: `development` adds `tests/`, `docs/`, and the dev group,
while `production` is the default target and carries the package alone. Both leave a
`bash` prompt in `/adl1t_datamaker`, from which the scripts below work unchanged. Since
`production` copies no `docs/`, the summary and publish tooling, which parses
`docs/README.md`, works only under `development` or from a checkout. No image is published
anywhere, so build it locally; the `Dockerfile` needs BuildKit.

## Usage

Every script is run from the root of the repository. The default pileup folder and the
prescale menu paths in the experiment configs are written relative to it, so a conversion
started elsewhere fails when it looks for them. `scripts/run.snip` holds a worked example
of each conversion and summary command, and [`scripts/README.md`](scripts/README.md)
documents the scripts, the configuration, and the auxiliary files in full.

### Converting

`./scripts/convert` takes one ntuple and `./scripts/convert_folder` takes a folder of
them, `--ncores` at a time. Each needs the input, the prescale menu that decides which
trigger algorithms are kept, and an output path, and each defaults to the emulated trees.
For simulation, pass `--mc`, which skips the brilcalc pileup join.

`convert_run` is the form used in practice. It reads a campaign config from
`scripts/configs/experiment/`, which names the input folders on EOS, the output folder
each maps onto, the menu, and whether the sample is simulation, and converts everything
that config names. Six campaigns are checked in.

```
./scripts/convert_run +experiment=EphZB_2025G_run398183 output_root_path=./parquet_files
```

### Summarising

```
./scripts/summary --folder parquet_files/EphZB_2025G_run398183
```

This writes a `SUMMARY` directory inside the data folder, holding figures, a `REPORT.md`,
and a `summary.json`. The report covers provenance, the file inventory with row counts and
sha256 digests, every column against its specification in `docs/README.md`, object
multiplicities, run and luminosity coverage, the full ranked trigger seed table, and a
validation checklist of fourteen checks.

Nothing is sampled. One streaming pass counts how often each value occurs, and every
statistic, quantile, and histogram follows from those counts, so `--batch_size` trades
memory alone for any column narrow enough to stay countable. A column whose values spread
too widely is demoted instead: it keeps its extremes and its mean, reports no deviation,
quantiles, or distinct count, and is marked as inexact in the report.

`summary.json` carries more than the report renders, and is the artefact worth keeping:
the per-shard manifest with row counts and digests, the arrow type of every column, and
the raw value counts from which every figure can be redrawn. `summary_comparison` reads it
in preference to the parquet, and the campaign aggregate is built from it alone.

```
./scripts/summary_run +experiment=EphZB_2025G_run398183 output_root_path=./parquet_files
./scripts/summary_comparison --folder1 A --folder2 B --output_folder OUT
```

`summary_run` does the same for a whole campaign and adds an aggregate report, and,
because it composes the same config as `convert_run`, it also records the input paths,
tree names, and prescale menu that the parquet files do not carry. `summary_comparison` overlays
two data sets and writes the differences, which is how a reconversion gets validated.

Both the summary and the publish tooling read `docs/README.md` from the source tree, and
the summary reads the menus in `scripts/L1Menus/` from it as well, so both need a checkout
rather than an installed wheel. The reader does not.

### Publishing

```
./scripts/publish/publish --out <release folder>
```

This partitions a converted data set into the published train, valid, and test archives,
writes the dataset card and the licence beside them, and records the checksums. It draws
no split of its own: the partition arrives as a frozen map, which has to be in place under
`--out` before the command will run. See
[scripts/publish/README.md](scripts/publish/README.md).

### Reading the data

```python
from adl1t_datamaker.loader import Parquet2Awkward

data = Parquet2Awkward("parquet_files/EphZB_2025G_run398183")

data.object_names             # the object folders found, in directory order
muons = data["muons"]         # ak.Array, the whole folder in memory
muons.muonIEt                 # jagged: one list of in-time muons per event

for batch in data("muons"):   # the same content, streamed
    ...
```

Indexing reads an object whole; calling the loader streams it, in batches of `bs` events,
1,000,000 by default. Pass `select_feats={"muons": ["muonIEt"], "seeds": None}` to narrow
the read: `None` for an object means every column of it, and an object left out of the
dictionary is not read at all. `object_names` narrows in place to the objects actually
loaded once `select_feats` is given.

Two things catch people out. Only `cica` is flat; every other column carries a list layer,
so a seed reads as `data["seeds"].L1bit[:, 0]` and a sum as `data["ET"].Et[:, 0]`, the
particle collections being genuinely jagged where the rest are length-1. And batches from
two folders are not aligned, because pyarrow takes its boundaries from each folder's own
row groups, so join them shard by shard rather than by zipping the streams.

`Parquet2Awkward` is the class to use. `ParquetLoader`, which it derives from, holds the
dataset plumbing and reads nothing on its own. Both take local paths only.

## Repository layout

| Path | What is in it |
| --- | --- |
| `src/adl1t_datamaker/` | the package |
| `scripts/` | the entry points, the hydra configs, the prescale menus, and the brilcalc pileup files |
| `docs/` | the feature specification, and the CMS documents behind it |
| `tests/` | the suite described above |
| `notebooks/` | two analyses; `pileup_vs_towers.ipynb` predates the parquet rewrite and no longer runs |

The package divides by what each module touches:

| Module | What it does |
| --- | --- |
| `root2parquet` | reads the ntuple trees and writes the object folders |
| `loader` | reads them back, whole or streamed |
| `components.l1_seeds` | the prescale menu, and the trigger decision bits |
| `components.pileup` | the brilcalc pileup join, for recorded data |
| `schema` | parses `docs/README.md` into the feature specification the rest of the code checks against |
| `stats`, `measure` | exact value counting, and the one streaming pass over a data folder |
| `summary`, `report`, `figures`, `validation` | what a summary measures, renders, draws, and checks |
| `publish` | the release: partition, card, archives, and HuggingFace mirror |
| `util`, `terminal_colors` | path handling across local and `root://`, and console colour |

## Contact

Patrick Odagiu, `podagiu@ethz.ch`. The repository is mirrored at
[github.com/bb511/adl1t_datamaker](https://github.com/bb511/adl1t_datamaker) and on the
CERN GitLab at `cms-l1-ad/data_converter`.
