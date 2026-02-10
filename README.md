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

### Converter

See the `/.gitlab-ci.yaml` or `/scripts/convert/run.snip` for usage examples.

### Reader

To read the h5 files generated with this code, import the h5converter class
`from adl1t_datamaker.convert.loader import Parquet2Awkward`

For an example of how the reading is done, check the `scripts/convert/plot` script.
