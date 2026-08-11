[![Email Badge](https://img.shields.io/badge/blah-podagiu%40ethz.ch-blue?style=flat-square&logo=minutemailer&logoColor=white&label=%20&labelColor=grey)](mailto:podagiu@ethz.ch)
[![Python: version](https://img.shields.io/badge/python-3.10-blue?style=flat-square&logo=python)](https://www.python.org/downloads/)
[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.21787779-blue?style=flat-square&logo=doi)](https://doi.org/10.5281/zenodo.21787779)
[![Dataset on HF](https://huggingface.co/datasets/huggingface/badges/resolve/main/dataset-on-hf-md.svg)](https://huggingface.co/datasets/podagiu/anomaly_detection_cmsl1t)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000?style=flat-square)](https://github.com/psf/black)

# Level-1 CMS Trigger Anomaly Detection Data

The CMS Level-1 Trigger applies a series of filters to each bunch crossing at the LHC.
This selection is made by using rough data from the detector, accessible at this early stage:
at most 8 muons, 12 jets, 12 egammas, and 12 taus; 6 energy sums.
The information of these objects are stored in fixed-bit hardware integers
(see [`docs/README.md`](docs/README.md) for more details on each object).
Each trigger filter algorithm outputs one decision bit.
This repository converts the input data, as well as each algorithm's decision,
from ROOT, the standard CERN format, to parquet files.
The data that is converted represents randomly selected events at CERN, called ZeroBias,
a simulation thereof, and simulations of how specific signatures of rare events or
new physics would look like to the Level-1 CMS trigger.

Everything else in the original ROOT files is dropped: float reconstructions, the
objects of neighbouring bunch crossings, and detector-level branches that never reach
the trigger boards. [`docs/README.md`](docs/README.md) specifies every surviving
feature, with its bit width, hardware unit, and physical range.

The produced data sets are meant to be used in the context of anomaly detection for new physics discovery.
A data release is published at [10.5281/zenodo.21787779](https://doi.org/10.5281/zenodo.21787779) under CC0.


## Data Structure

The code produces the following structure: one directory per data set, one subdirectory per object, and
inside each subdirectory, one parquet file with a maximum of `10 000` entries.
Each entry corresponds to an event; row $i$ of every folder is the same event.
The folders can be read separately and joined by position.

```
<data set>/
  muons/  jets/  egammas/  taus/    jagged: one entry per in-time object, nothing padded
  ET/  HT/  MET/  MHT/  FET/  FHT/  one entry per event, stored as a length-1 list
  event_info/                       run, lumi, event, bx, orbit, time, nPV_True
  seeds/                            one boolean column per unprescaled algorithm, and L1bit
  cica/                             the CICADA anomaly score, flat, where available
```

`L1bit` is synthesised as the logical OR of the algorithm columns beside it.
The `cica` folder appears only where a calorimeter summary tree was configured;
for example, unpacked 2025 zero-bias ntuples lack this tree.

## Setup

Reading the published data needs only

```
pip install "adl1t-datamaker @ git+https://github.com/bb511/adl1t_datamaker.git@master"
```

Converting needs the full environment, managed with
[poetry](https://python-poetry.org/). From the repository root:

```
poetry install                   # add --extras xrootd to read inputs over root://
```

The xrootd extra is optional because its wheel builds from source and needs cmake and a
C++ toolchain; without it, globbing a `root://` path fails with an error.
`requirements.txt` also describes all the required packages from `poetry.lock`.

### Tests

After implementing a feature, run a minimal suite of tests using:

```
poetry install --with dev
poetry run pytest
```

### Docker

The `Dockerfile` builds on `alma9-base` with the EOS and xrootd clients.
You still need a kerberos ticket to read files from CERN EOS. The default target,
`production` has only the package.
The `development` target adds `tests/`, `docs/`, and the dev group.
Images are only published on CERN internal repos. Build locally.


## Usage

The scripts to run all parts of the code are in the `scripts/` folder.
Run the scripts from the repository root, since all the paths are resolved against it.
See `run.snip` for example of each command that can be run.
For more details, see [`scripts/README.md`](scripts/README.md).


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
million by default.

You can use `select_feats={"muons": ["muonIEt"], "seeds": None}` to only read certain
features per object: `None` keeps every column of that object, and an object left out is not read.
The loader takes local paths only.

Only the `cica` object is flat; every other column carries a list
layer.
For example, a seed is read as `data["seeds"].L1bit[:, 0]` and a sum as
`data["ET"].Et[:, 0]`.
Batches from two folders are not aligned, so join folders shard by shard
rather than by zipping streams.
