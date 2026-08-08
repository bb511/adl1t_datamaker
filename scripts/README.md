# Scripts, configuration, and auxiliary files

Every script here is run from the root of the repository, not from this folder. Two paths
are written relative to that root and are resolved against the working directory: the
default pileup folder, `scripts/pileup_files/`, and the prescale menu named by each
experiment config, `scripts/L1Menus/<menu>.csv`. A campaign started from anywhere else
therefore fails at the first ntuple, when it opens the menu, and a conversion of recorded
data would have failed a moment later looking for the brilcalc file of its run. Only the
hydra entry points are affected: `convert` and `convert_folder` take both paths on the
command line, so absolute arguments free them of the convention. `run.snip` holds a worked
example of every conversion and summary command, each beginning `./scripts/`; the publish
example lives in [`publish/README.md`](publish/README.md).

The scripts themselves are thin. Each parses arguments and calls into
`src/adl1t_datamaker`, so the behaviour each documents is the library's.

## The scripts

| Script | What it does |
| --- | --- |
| `convert` | one L1Ntuple to one parquet per object folder |
| `convert_folder` | every root file of one folder, `--ncores` at a time |
| `convert_run` | a whole campaign, from a hydra experiment config |
| `summary` | figures, `REPORT.md` and `summary.json` for one or more converted folders |
| `summary_run` | the same for a campaign, plus an aggregate report and the config as provenance |
| `summary_comparison` | two data sets overlaid, and a `COMPARISON.md` of the differences |
| `publish/publish` | a converted data set partitioned, carded and packed into a release |
| `publish/export_hf` | the HuggingFace mirror of a finished release |

`convert` and `convert_folder` differ only in what they are pointed at, `--input_file`
against `--folder`, and in `--ncores`, which only the second has. Both take
`--prescale_file`, `--output_path`, an optional `--pileup_folder`, and the four tree
names. The defaults name the emulated trees, `l1UpgradeEmuTree/L1UpgradeTree` and
`l1uGTEmuTree/L1uGTTree`; the unpacked ntuples hold the same two trees without the `Emu`,
but carry no calorimeter summary tree at all. `--calosumm_tree_name` accordingly defaults
to nothing, and left unset it skips the CICADA object rather than writing an empty folder.
`--mc` marks the input as simulation. The flag is read in exactly one place, where it
skips the brilcalc pileup join and leaves `nPV_True` as the ntuple wrote it.

Two behaviours are easy to trip over. `convert_folder` refuses to write a parquet whose
stem is already in the output folder, because output files are named after their input
stem and several input folders can map onto one output folder; `convert` has no such guard
and replaces silently. `--silent` then defaults to off here while both converter config
groups set it on, so a campaign run is quieter than a hand-run conversion, though not
silent: the flag suppresses the per-object progress lines alone.

`summary` takes one or more `--folder` arguments and writes a `SUMMARY` directory inside
each. `--outdir` redirects those writes and then accepts only one folder, and
`--campaign_report` additionally aggregates the folders given into one report. `--reuse`
takes each folder's existing `summary.json` rather than measuring it again, measuring only
a folder that has none, which is how an aggregate is regenerated for free. It writes no
per-folder summary and ignores `--batch_size`, `--no_checksums`, `--objects`, `--clean`
and `--outdir`, since it passes none of them on.

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

An experiment config is applied with `+experiment=<name>`, and the `+` is needed because
the group is not in either base's defaults list. Each is marked `# @package _global_`, so
its `paths` and `converter` blocks merge at the top level. Each supplies the input root on
EOS, the mapping from input folders to output folders, the prescale menu, and the `mc`
flag. Two of them override the converter group to `unpacked`, which drops the `Emu` from
two tree names and omits the calorimeter summary tree altogether, so those conversions
carry no CICADA score.

| Experiment | Simulation | Trees | Menu | Input folders to output folders |
| --- | --- | --- | --- | --- |
| `EphZB_2024E_run381148-381149` | no | emulated | 2024 v1.1.0 | 1 to 1 |
| `EphZB_2025B_run392642` | no | emulated | 2025 v1.1.1 | 1 to 1 |
| `EphZB_2025E_run396102` | no | unpacked | 2025 v1.3.0 | 1 to 1 |
| `EphZB_2025G_run398183` | no | unpacked | 2025 v1.3.0 | 1 to 1 |
| `L1TNtupleRun3-133XWinter24` | yes | emulated | 2023 v1.2.0 | 38 to 38 |
| `L1TNtupleRun3-142XWinter25` | yes | emulated | 2024 v1.3.0 | 32 to 21 |

The Winter25 campaign is the one that merges: six of its samples were produced by CRAB
across several shard directories, the widest spanning `0000` through `0003`, and the
config maps each sample's shards onto one output folder. Two shard directories of the same
sample can hold files of the same name, which is why the overwrite guard exists and why
`allow_overwrite` defaults to `False`.

`output_root_path` is mandatory and given on the command line. `summary_run` writes its
aggregate to `<output_root_path>/SUMMARY/<experiment>`, qualified by experiment because
one output root usually holds several campaigns.

## Prescale menus

The menus in `L1Menus/` decide which trigger algorithms reach the parquet. A menu is a csv
with one row per algorithm; column 6, counting from zero, holds that algorithm's prescale
at nominal luminosity, and a value of `1` there means unprescaled. Everything else is
dropped. Most of what that discards is an algorithm disabled at this luminosity, marked
`0`, and the rest are genuinely prescaled: `L1_SingleMuOpen` carries `n` = 63000 in the
2022 menu, so one accept in every 63000 is recorded and its column would measure the
prescale rather than the physics.

The header of that column names the luminosity it refers to, and that name changes with
the menu generation, which is why the code identifies the column by position and reports
the header it found. A menu whose column 6 never holds `1` raises an error rather than
producing an empty seed list.

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
`L1_DoubleTau_Iso*` seeds and thereby names three algorithms twice, so it selects 190 rows
but only 187 distinct algorithms. Duplicates are collapsed when the names are matched
against the trigger tree.

All nine are scanned when a summary tries to identify which menu a converted data set was
made with, and the attempt succeeds: the nine unprescaled sets are pairwise distinct, so a
list of seed columns names its menu exactly, with no root file and no config.

## Pileup files

`pileup_files/` holds brilcalc output, one file per run, for seven runs: 381148, 381149,
386554, 386593, 392642, 396102 and 398183. Only the first two and the last three are named
by an experiment config. For recorded data, the conversion overwrites `nPV_True` per run
and luminosity section with the `avgpu` that brilcalc reports; simulation keeps whatever
the ntuple carried.

To process a new run, drop its brilcalc file here. The name has to begin with
`run<number>`, which is all the code globs for, the `_brilcalc_PU` suffix the existing
files carry being convention rather than requirement. The conversion aborts when a run has
no file at all, on the grounds that silently unpopulated pileup is worse than a failure. A
luminosity section missing from a file that is otherwise present yields zero, which is
indistinguishable from a genuine zero outside stable beams, so the summary reports the
zero fraction and warns when it exceeds one per cent rather than asserting anything.

## Publish

`publish/` holds the tooling that turns a converted data set into a release: the split
archives, the dataset card, the licence, and the checksums. It is documented separately in
[`publish/README.md`](publish/README.md) because two of its three inputs come from
elsewhere, the frozen split map and the split summary that travels with it.
