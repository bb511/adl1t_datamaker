# Scripts, configuration, and auxiliary files

> [!IMPORTANT]
> Run every script in this folder from the root of the repository!!!

There are two paths that resolve based on you being in root: the default pileup folder,
`scripts/pileup_files/`, and the prescale menu named by each experiment config,
`scripts/L1Menus/<menu>.csv`.

The `run.snip` file has a worked example of every conversion and summary command.
For more details on the `publish` part of this repo, which handles the publishing of the
produced data to `Zenodo` and `HuggingFace` is available in [publish/README.dm](publish/README.md).


## The scripts

| Script | What it does |
| --- | --- |
| `convert` | one L1Ntuple to one parquet per object folder |
| `convert_folder` | every root file of one folder, `--ncores` at a time |
| `convert_run` | a whole campaign, from a hydra experiment config |
| `summary` | figures, `REPORT.md`, and `summary.json` for one or more converted folders |
| `summary_run` | the same for every folder of a campaign, with the config as provenance |
| `summary_comparison` | two data sets overlaid, and a `COMPARISON.md` of the differences |
| `publish/publish` | a converted data set partitioned, carded, and packed into a release |
| `publish/export_hf` | the HuggingFace mirror of a finished release |

The `convert` and `convert_folder` scripts differ only by one input argument:
`--input_file` vs `--folder`, respectively.
The latter also takes `--ncores`.

The scripts expect the emulated trees by default, `l1UpgradeEmuTree/L1UpgradeTree` and
`l1uGTEmuTree/L1uGTTree`.
The unpacked trees do not have `Emu` and have no calo summary.
Therefore, `--calosumm_tree_name` defaults to nothing skips the CICADA object.
The `--mc` flag is used when wanting to convert Monte Carlo simulation data: it skips the
brilcalc pileup join and leaves `nPV_True` as it was originally wrote it.
This is because brilcalc adds pileup information to real data, while for simulated data
this information is readily available.

**The `convert_folder` script refuses to write a parquet whose stem already exists.**
The `convert` script does not have this guard and overwrites silently.
The `--silent` flag defaults to off here while both converter config groups set it on,
so a campaign run is quieter than a hand-run conversion.

The `summary` script takes one or more `--folder` arguments and writes a `SUMMARY` directory into
each; `--outdir` redirects the writes and then accepts only one folder.

## Configuration

The `convert_run` and `summary_run` scripts are hydra applications reading `configs/`.

```
configs/
  convert.yaml            output_root_path, ncores, allow_overwrite
  summary.yaml            output_root_path, batch_size, figure_format, checksums,
                          skip_existing, clean
  converter/default.yaml  the emulated trees, with the calorimeter summary tree
  converter/unpacked.yaml the unpacked trees, without it
  paths/default.yaml      input_root_path, input_output_folders, auxiliary_files
  experiment/*.yaml       one campaign each
```

An experiment config is applied with `+experiment=<name>`.
**Again, for conversion, you need access to CERN EOS and a CERN CMS membership.**

| Experiment | Simulation | Trees | Menu | Input folders to output folders |
| --- | --- | --- | --- | --- |
| `EphZB_2024E_run381148-381149` | no | emulated | 2024 v1.1.0 | 1 to 1 |
| `EphZB_2025B_run392642` | no | emulated | 2025 v1.1.1 | 1 to 1 |
| `EphZB_2025E_run396102` | no | unpacked | 2025 v1.3.0 | 1 to 1 |
| `EphZB_2025G_run398183` | no | unpacked | 2025 v1.3.0 | 1 to 1 |
| `L1TNtupleRun3-133XWinter24` | yes | emulated | 2023 v1.2.0 | 38 to 38 |
| `L1TNtupleRun3-142XWinter25` | yes | emulated | 2024 v1.3.0 | 32 to 21 |

`output_root_path` is mandatory and given on the command line.

## Prescale menus

The menus in `L1Menus/` pertain to configurations of each trigger run: they describe
which algorithms were active during that run and how their output is scaled.
A menu is a csv with one row per algorithm; column 6, counting from zero, has the prescale at
nominal luminosity, and `1` there means unprescaled.
Everything else is dropped, mostly algorithms disabled at this luminosity and marked `0`,
the rest genuinely prescaled.
The header of column 6 is the luminosity and changes with the menu generation.
The code identifies the column by position and reports the header it found.

| Menu | Nominal luminosity column | Unprescaled algorithms | Used by |
| --- | --- | --- | --- |
| `Prescale_2022_v0_1_1.csv` | `1.5E+34` | 150 | |
| `L1Menu_Collisions2023_v1_1_0.csv` | `2p1E34` | 168 | |
| `L1Menu_Collisions2023_v1_2_0.csv` | `2p1E34` | 175 | Winter24 |
| `L1Menu_Collisions2024_v1_1_0.csv` | `2p0E34` | 161 | 2024E |
| `L1Menu_Collisions2024_v1_2_1.csv` | `2p0E34` | 170 | |
| `L1Menu_Collisions2024_v1_3_0_last.csv` | `2p0E34+ZeroBias+HLTPhysics` | 164 | Winter25 |
| `L1Menu_Collisions2025_v1_1_1.csv` | `1p95E34` | 187 | 2025B |
| `L1Menu_Collisions2025_v1_1_1_original.csv` | `1p95E34` | 190 | |
| `L1Menu_Collisions2025_v1_3_0.csv` | `1p95E34` | 190 | 2025E, 2025G |

The two 2025 v1.1.1 files differ in three rows: the edited one renames three
`L1_DoubleTau_Iso*` seeds and thereby names three algorithms twice, so it selects 190
rows but only 187 distinct algorithms.
Duplicates are collapsed when the names are matched against the trigger tree.

## Pileup files

The `pileup_files/` folder has `brilcalc` output, which is a CERN tool for retrieving the
pileup conditions for each of the events.
Pileup is the number of concomitant collisions within one bunch crossing.
There is one such `brilcalc` file per run.
For recorded data, the conversion overwrites `nPV_True` per run and luminosity section
with the `avgpu` that brilcalc reports; simulation keeps whatever the original tree carried.

To process a new run, drop its brilcalc file here, named `run<number>*`: the code globs
for the prefix alone.
A luminosity section missing from a present file yields zero, indistinguishable from
a genuine zero outside stable beams, so the summary reports the zero fraction and warns when it exceeds one per cent.

## Publish

The `publish/` contains all the scripts pertaining to publishing the data into a release.
More details are available at [`publish/README.md`](publish/README.md).
