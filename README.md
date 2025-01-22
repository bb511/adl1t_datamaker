# Level 1 Trigger Data Processing for uGT

The code herein fulfills two functions:
* creates the level 1 trigger ntuples from raw CMS detector data
* converts the generated level 1 trigger ntuples to h5 files that contain only the objects and features available to the global trigger (uGT)

The package is split into two submodules, i.e., `L1Trigger_data/rootfile_generation` and `L1Trigger_data/h5convert`.
See the corresponding directories for additional details on each subpackage.
Futhermore, The scripts used to run the code are in the `scripts` folder.
Examples of how the code is ran are found in the `run.snip` of the respective `scripts` subfolders.

## Setup

A `conda` environment can be imported from `condaenv.yml` file by using
```
conda env create -f condaenv.yml
```
which sets up all the dependencies.

Afterwards, install this repo package by running
```
pip install .
```
in the repo directory.
