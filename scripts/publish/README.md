# Publishing the L1 trigger data

These two scripts turn a converted data set into a release: `publish` writes the
archival record, and `export_hf` mirrors it for HuggingFace once the accompanying paper
is accepted. Both run from the root of the repository, as every script here does.

## What the release needs

Three inputs, and only one of them is produced by this repository.

The **converted parquet**, one directory per data set holding one subdirectory per
object, is what `./scripts/convert_run` writes.

The **frozen split map**, `_splitmap/`, holds one `(split, order)` pair per raw row for
each data set, plus an `index.json` naming the raw directory each map belongs to. It is
not regenerated here, and cannot be. The study this data was produced for draws its
splits from a single seeded generator that advances across data sets in a fixed order,
so one data set's split cannot be redrawn on its own, and redrawing all of them would
partition the release differently from the published one. The map therefore travels with
the data as a frozen artefact. It was written by `scripts/publish_l1data/build_split_map.py`
in the study's repository, at commit `0399608`, which was retired once the split was
frozen.

The **split summary**, `metadata/split_summary.json`, travels with the map and records
the seed, the split fractions, and the raw and surviving event counts the card quotes.
Its `dataset_version` field names the version it was first written for and is
deliberately ignored, since the file itself never changes.

## Running it

```
./scripts/publish/publish --out /data/deodagiu/adl1t_data/publish --ncores 32
```

That runs three stages in order. **export** checks every data set against its map, then
consolidates each object's shards and takes the rows of each split out of them.
**card** renders `README.md` and `LICENSE` into the tree. **pack** writes one archive per
split into `--out`, copies the card and the licence beside them, and writes
`sha256sums.txt`. Pass `--stage pack` to redo the last of those alone after a failed
archive, or `--only <name>` to export a single data set.

Scratch goes to a sibling of `--out`, so the release folder holds the upload and its
metadata and nothing else:

```
publish/                README.md LICENSE {train,valid,test}.tar sha256sums.txt
  metadata/             split_summary.json release.json
  _splitmap/            the frozen input, never uploaded
publish_work/
  consolidated/         one file per object per data set
  adl1t-l1ad-v2/        the exported tree the archives are built from
```

The exported tree survives the pack because `export_hf` reads it. Delete
`publish_work/` once the mirror is built, or before it if the disk is tight and you are
willing to re-export.

## The guard, and why it matters

`publish` refuses to export a data set whose raw parquet no longer matches its map. It
checks the row count, and then a sha256 over the event numbers in raw row order, which
`index.json` records under `fingerprint`.

That second check is the one that earns its place. The map addresses raw rows by
position, and position is defined by the lexicographic order of the shards. Reconverting
the same ntuples preserves it, as the ETTEM correction did, so the map still applies.
Converting a different set of files does not, and if the totals happened to agree,
nothing else in the tree would reveal it: the export would succeed and silently scramble
every split. A map with no `fingerprint` recorded falls back to the row count alone.

## Resources

The export reads every published object twice, once to consolidate and once to take
rows, and writes about 4 GB of tree plus 4 GB of archives. Give it roughly 10 GB of
scratch beyond the release itself. Consolidation is the slow half and parallelises over
objects, so `--ncores` is worth setting on a large machine.

## Things to know

The card derives its numbers rather than restating them. Unit factors, hardware bit
widths, and per-collection capacities come from `adl1t_datamaker.schema`, which parses
`docs/README.md`; the constituent counts come from `adl1t_datamaker.publish.assets.adl1t_l1ad`,
the reader that ships inside the record. Version 1 of the card carried a hand-copied
calorimeter eta factor of 0.5 against the documented 0.0435, which put a jet at
$|\eta| = 57$, and deriving is what stops that recurring. One consequence: `schema`
resolves `docs/README.md` relative to the source tree, so the card renders from a
checkout and not from a wheel.

The section of the card headed "What version 2 corrects" is prose about this release
rather than generated text, so a later version has to rewrite it.

The export appends `split` and `order` to `event_info`. Neither is in `docs/README.md`,
and neither should be, since the converter does not produce them, so `./scripts/summary`
run over a published split warns that they are undocumented. The warning is expected.

`SKIP_OBJECTS` in `adl1t_datamaker.publish.export` names the directories that are not object
collections: `PLOTS` and `SUMMARY`, which this repository writes about the data rather
than as data, and `cica`, the CICADA score, which is another anomaly trigger's output
rather than detector input and is excluded from the release along with the
`L1_CICADA_*` seed bits.

## Where the code lives

The scripts here are thin, as every script in this repository is. The work happens in
`src/adl1t_datamaker/publish/`, a subpackage kept apart from the rest because it runs
the other way round: the modules above it turn ntuples into parquet and measure what
came out, while these take finished parquet and package it. They read the producer, for
the feature specification and the row counts, and the producer reads nothing of theirs.

| Module | What it does |
| --- | --- |
| `publish.export` | Partition a data set by its frozen map, then archive and checksum it |
| `publish.card` | The dataset card and the licence that ship inside the record |
| `publish.huggingface` | The row-per-event mirror |
| `publish.assets` | Code that ships inside the record, copied rather than run from here |
