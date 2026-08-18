# Publishing the L1 trigger data

The `publish` script compiles the data into a zenodo-ready record.
The `export_hf` script prepares it for HuggingFace.
When generating a new release, please run these from **the root of the repo**.

## Prerequisites

The release of a data set requires three inputs:

* the converted parquet files, generated with `./scripts/convert_run`
* the frozen split map, which partitions the events into train, validation, and test
data sets; see the `splitmap` folder for the current split map
* the `split_summary.json` records the seed that was used in generating the split,
the fractions of events being used, the event filter, and per-dataset event counts

notice that the latter two inputs are frozen and present in this repository; the parquet
files need to be generated, which this repository facillitates.

## Usage

```
./scripts/publish/publish --out /data/deodagiu/adl1t_data/publish --ncores 32
```

The code runs in three stages:
* **export** checks every data set against its map, then consolidates each object's
shards and takes the rows of each split out of them.
* **card** renders `README.md` and `LICENSE` into the tree.
* **pack** writes one archive per split into `--out`, copies the card and the licence
beside them, and writes `sha256sums.txt`. `--stage pack` redoes the last stage alone
after a failed archive; `--only <name>` exports a single data set.

The release folder has only the `.tar` data splits (train, validation, test), the README.md,
and the associated license.
The `publish_work` folder contains the data in parquet format, used to build the HuggingFace
release of it.

```
publish/                README.md LICENSE {train,valid,test}.tar sha256sums.txt
  metadata/             split_summary.json release.json
  _splitmap/            the frozen input, never uploaded
publish_work/
  consolidated/         one file per object per data set
  adl1t-l1ad-v1/        the exported tree the archives are built from
```

**You can delete the `publish_work` repository after running the `export_hf` script.**
One needs about 10 GB of space for the full release. Plan to have that much when generating
a new release.

`SKIP_OBJECTS` in `adl1t_datamaker.publish.export` contains the directories that are not
object collections: `PLOTS` and `SUMMARY`, which this repository writes about the data,
and `cica`, another anomaly trigger's output rather than detector input,
excluded from the release along with the `L1_AXO_*` and `L1_CICADA_*` seed bits.

## Scripts

| Module | What it does |
| --- | --- |
| `publish.export` | partition a data set by its frozen map, then archive and checksum it |
| `publish.card` | the dataset card and the licence that ship inside the record |
| `publish.huggingface` | the row-per-event mirror |
| `publish.assets` | the loading pipeline and its configs, which ship inside the HuggingFace mirror rather than run from here |
