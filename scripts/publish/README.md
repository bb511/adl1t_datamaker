# Publishing the L1 trigger data

`publish` writes the archival record of a converted data set, and `export_hf` mirrors
it for HuggingFace once the accompanying paper is accepted. Both run from the root of
the repository.

## What the release needs

The release needs three inputs, of which only the first is produced by this
repository.

The **converted parquet** is what `./scripts/convert_run` writes: one directory per
data set, one subdirectory per object.

The **frozen split map**, `_splitmap/`, holds one `(split, order)` pair per raw row
for each data set, plus an `index.json` naming the raw directory each map belongs to.
It cannot be regenerated here. The study this data was produced for draws its splits from a
single seeded generator advancing across data sets in a fixed order, so no data set's
split can be redrawn on its own, and redrawing all of them would partition the release
differently from the published one. The map was written by
`scripts/publish_l1data/build_split_map.py` in the study's repository, at commit
`0399608`, and travels with the data as a frozen artefact.

The **split summary**, `metadata/split_summary.json`, records the seed, the split
fractions, and the raw and surviving event counts the card quotes. Its
`dataset_version` field is deliberately ignored, since the file never changes.

## Running it

```
./scripts/publish/publish --out /data/deodagiu/adl1t_data/publish --ncores 32
```

Three stages run in order. **export** checks every data set against its map, then
consolidates each object's shards and takes the rows of each split out of them.
**card** renders `README.md` and `LICENSE` into the tree. **pack** writes one archive
per split into `--out`, copies the card and the licence beside them, and writes
`sha256sums.txt`. `--stage pack` redoes the last stage alone after a failed archive;
`--only <name>` exports a single data set.

Scratch goes to a sibling of `--out`, so the release folder holds only the upload and
its metadata:

```
publish/                README.md LICENSE {train,valid,test}.tar sha256sums.txt
  metadata/             split_summary.json release.json
  _splitmap/            the frozen input, never uploaded
publish_work/
  consolidated/         one file per object per data set
  adl1t-l1ad-v2/        the exported tree the archives are built from
```

The exported tree survives the pack because `export_hf` reads it; delete
`publish_work/` once the mirror is built.

The export reads every published object twice, once to consolidate and once to take
rows, and writes about 4 GB of tree plus 4 GB of archives, so give it roughly 10 GB of
scratch beyond the release itself. Consolidation is the slow half and parallelises over
objects, so `--ncores` is worth setting on a large machine.

## The guard

`publish` refuses to export a data set whose raw parquet no longer matches its map: it
checks the row count, then a sha256 over the event numbers in raw row order, which
`index.json` records under `fingerprint`. The map addresses raw rows by position, and
position is defined by the lexicographic order of the shards. Reconverting the same
ntuples preserves that order, as the ETTEM correction did; converting a different set
of files does not, and without the fingerprint an export whose totals happened to agree
would silently scramble every split. A map with no `fingerprint` recorded falls back to
the row count alone.

## Things to know

The card derives its numbers rather than restating them: unit factors, bit widths, and
per-collection capacities come from `adl1t_datamaker.schema`, which parses
`docs/README.md`, and the constituent counts from
`adl1t_datamaker.publish.assets.adl1t_l1ad`, the reader that ships inside the record.
Version 1 hand-copied a calorimeter eta factor of 0.5 against the documented 0.0435,
putting a jet at $|\eta| = 57$; deriving is what stops that recurring. Because `schema`
resolves `docs/README.md` in the source tree, the card renders from a checkout, not
from a wheel.

The card section headed "What version 2 corrects" is prose about this release rather
than generated text, so a later version has to rewrite it.

The export appends `split` and `order` to `event_info`. Neither belongs in
`docs/README.md`, since the converter does not produce them, so `./scripts/summary` run
over a published split warns that they are undocumented; the warning is expected.

`SKIP_OBJECTS` in `adl1t_datamaker.publish.export` names the directories that are not
object collections: `PLOTS` and `SUMMARY`, which this repository writes about the data
rather than as data, and `cica`, another anomaly trigger's output rather than detector
input, excluded from the release along with the `L1_CICADA_*` seed bits.

## Where the code lives

The scripts are thin; the work happens in `src/adl1t_datamaker/publish/`, a subpackage
kept apart because it runs the other way round: the rest of the package turns ntuples
into parquet, and these modules take finished parquet and package it. They read the
producer, for the feature specification and the row counts; the producer reads nothing
of theirs.

| Module | What it does |
| --- | --- |
| `publish.export` | partition a data set by its frozen map, then archive and checksum it |
| `publish.card` | the dataset card and the licence that ship inside the record |
| `publish.huggingface` | the row-per-event mirror |
| `publish.assets` | code that ships inside the record, copied rather than run from here |
