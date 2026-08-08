# Level 1 Trigger Data Processing for uGT

The code converts the level 1 trigger ntuples (L1Ntuple.root) to parquet files that contain only the objects and features available to the global trigger (uGT).

The scripts used to run the code are in the `scripts` folder.
Examples of running commands are found in the `run.snip` of the `scripts` folder.

Explanations of all the objects and features found in the parquet files are [here](docs/README.md).

## Setup
---

This repository requires `python >= 3.10`.

### Reader Only
If you do not want to convert any data but just want to read parquet files produced by this package, just install it using pip:
```
pip install "adl1t-datamaker @ git+ssh://git@gitlab.cern.ch:7999/cms-l1-ad/data_converter.git@master"
```
Then to use the reader follow the instructions at the end of this README.

### Full package

#### Installation with Poetry
This repository uses [poetry](https://python-poetry.org/) for dependency management.
Hence, the easiest way to install the dependencies is through poetry.

If you have a `python >= 3.10` installation and `poetry`, simply run
```
poetry install
```

in the parent directory of this repository to set up all the dependencies.
If you need xrootd support (are running using `eos`), then install additional dependencies:
```
poetry install --extras xrootd
````

#### Manual Dependecy Installation
You can also install the dependencies manually, as they are listed in `/pyproject.toml`.

#### Docker
A docker image of this project is also available [here](https://gitlab.cern.ch/cms-l1-ad/data_converter/) **(TBA)**, under the tag `latest`.

## Usage
---

All the scripts are run from the root of this repository, since their default paths
(`scripts/pileup_files/`, `scripts/L1Menus/`) are relative to it.

### Converter

See `/scripts/run.snip` for usage examples.

### Summaries

`./scripts/summary --folder <converted folder>` writes a `SUMMARY` directory beside the
data holding figures, a `REPORT.md` and a `summary.json`. The report covers provenance,
the file inventory with row counts and checksums, every column against its specification
in `docs/README.md`, object multiplicities, run and luminosity coverage, the full ranked
trigger seed table, and a technical validation checklist. Every number is exact rather
than sampled: the summary counts how often each value occurs in a single streaming pass
and derives the statistics from those counts.

`./scripts/summary_run +experiment=<name> output_root_path=<path>` does the same for a
whole conversion campaign and adds an aggregate report, and because it composes the same
config as `convert_run` it also records the input paths, tree names and prescale menu
that the parquet files themselves cannot say. `./scripts/summary_comparison` overlays two
data sets and writes the differences, which is how a reconversion gets validated.

### Reader

To read the parquet files generated with this code, import the reader class
`from adl1t_datamaker.loader import Parquet2Awkward`

For an example of how the reading is done, check the `scripts/summary` script.
