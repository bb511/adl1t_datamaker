# Scripts, configuration, and auxiliary files

Every script here runs from the root of the repository, not from this folder. Two paths
resolve against the working directory: the default pileup folder,
`scripts/pileup_files/`, and the prescale menu named by each experiment config,
`scripts/L1Menus/<menu>.csv`. A campaign started elsewhere therefore fails when it
opens the menu. Only the hydra entry points are affected; `convert` and
`convert_folder` take both paths on the command line. `run.snip` holds a worked example
of every conversion and summary command; the publish example lives in
[`publish/README.md`](publish/README.md).

The scripts are thin: each parses arguments and calls into `src/adl1t_datamaker`, so
the behaviour each documents is the library's.

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

`convert` and `convert_folder` differ only in their input argument, `--input_file`
against `--folder`, and in `--ncores`, which only the second has. Both take
`--prescale_file`, `--output_path`, an optional `--pileup_folder`, and the four tree
names. The defaults name the emulated trees, `l1UpgradeEmuTree/L1UpgradeTree` and
`l1uGTEmuTree/L1uGTTree`; the unpacked ntuples hold the same trees without the `Emu`
and carry no calorimeter summary tree, so `--calosumm_tree_name` defaults to nothing
and, left unset, skips the CICADA object. `--mc` marks simulation: it skips the
brilcalc pileup join and leaves `nPV_True` as the ntuple wrote it.

Two behaviours are easy to trip over. `convert_folder` refuses to write a parquet whose
stem already exists in the output folder, because several input folders can map onto
one output folder; `convert` has no such guard and replaces silently. And `--silent`
defaults to off here while both converter config groups set it on, so a campaign run is
quieter than a hand-run conversion.

`summary` takes one or more `--folder` arguments and writes a `SUMMARY` directory into
each; `--outdir` redirects the writes and then accepts only one folder.

## Configuration

`convert_run` and `summary_run` are hydra applications reading `configs/`. Both compose
the same two groups, so a campaign is described once and both commands understand it.

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

An experiment config is applied with `+experiment=<name>`; the `+` is needed because
the group is not in either base's defaults list. Each is marked `# @package _global_`
and supplies the input root on EOS, the mapping from input folders to output folders,
the prescale menu, and the `mc` flag. Two override the converter group to `unpacked`,
so those conversions carry no CICADA score.

| Experiment | Simulation | Trees | Menu | Input folders to output folders |
| --- | --- | --- | --- | --- |
| `EphZB_2024E_run381148-381149` | no | emulated | 2024 v1.1.0 | 1 to 1 |
| `EphZB_2025B_run392642` | no | emulated | 2025 v1.1.1 | 1 to 1 |
| `EphZB_2025E_run396102` | no | unpacked | 2025 v1.3.0 | 1 to 1 |
| `EphZB_2025G_run398183` | no | unpacked | 2025 v1.3.0 | 1 to 1 |
| `L1TNtupleRun3-133XWinter24` | yes | emulated | 2023 v1.2.0 | 38 to 38 |
| `L1TNtupleRun3-142XWinter25` | yes | emulated | 2024 v1.3.0 | 32 to 21 |

The Winter25 campaign is the one that merges: six of its samples were produced by CRAB
across several shard directories, and the config maps each sample's shards onto one
output folder. Two shards of the same sample can hold files of the same name, which is
why the overwrite guard exists and `allow_overwrite` defaults to `False`.

`output_root_path` is mandatory and given on the command line.

## Prescale menus

The menus in `L1Menus/` decide which trigger algorithms reach the parquet. A menu is a
csv with one row per algorithm; column 6, counting from zero, holds the prescale at
nominal luminosity, and `1` there means unprescaled. Everything else is dropped, mostly
algorithms disabled at this luminosity and marked `0`, the rest genuinely prescaled.
The header of column 6 names the luminosity and changes with the menu generation, so
the code identifies the column by position and reports the header it found. A menu
whose column 6 never holds `1` raises rather than producing an empty seed list.

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
rows but only 187 distinct algorithms. Duplicates are collapsed when the names are
matched against the trigger tree.

The nine unprescaled sets are pairwise distinct, so a summary can name the menu a data
set was made with from its seed columns alone, with no root file and no config.

## Pileup files

`pileup_files/` holds brilcalc output, one file per run. For recorded data, the
conversion overwrites `nPV_True` per run and luminosity section with the `avgpu` that
brilcalc reports; simulation keeps whatever the ntuple carried.

To process a new run, drop its brilcalc file here, named `run<number>*`: the code globs
for the prefix alone. The conversion aborts when a run has no file, because silently
unpopulated pileup is worse than a failure. A luminosity section missing from a present
file yields zero, indistinguishable from a genuine zero outside stable beams, so the
summary reports the zero fraction and warns when it exceeds one per cent.

## Publish

`publish/` turns a converted data set into a release: the split archives, the dataset
card, the licence, and the checksums. [`publish/README.md`](publish/README.md)
documents it, together with the two inputs that come from elsewhere, the frozen split
map and the split summary that travels with it.
