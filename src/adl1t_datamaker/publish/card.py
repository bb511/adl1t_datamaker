# The dataset card and licence that ship inside the published record.
#
# Every number the card quotes is derived rather than typed. The event counts come from
# the frozen split summary; the unit factors, hardware bit widths and collection
# capacities come from schema.py, which reads docs/README.md; the constituent counts
# come from the reader the record ships. Version 1 of this card carried a hand-copied
# calorimeter eta factor of 0.5 against the documented 0.0435, which put a jet at
# |eta| = 57, and deriving is what stops that recurring.

import textwrap

from adl1t_datamaker import schema
from adl1t_datamaker.publish.assets import adl1t_l1ad

SPLITS = ("train", "valid", "test")

# Width the card's prose is reflowed to. Zenodo shows the rendered markdown, but a
# reader who opens the file sees the raw text, and the substituted counts are long
# enough to leave the template's own line breaks ragged.
WRAP = 88

# Plural names the card uses for the collections, which are not the directory names.
DISPLAY = {"muons": "muons", "jets": "jets", "egammas": "e-gammas", "taus": "taus"}

# Rows of the unit table: the label, a collection carrying the same scales as every
# collection on that row, and the branches supplying the Et, eta and phi columns. None
# marks a column the collection has no field for.
UNIT_ROWS = (
    ("muons", "muons", ("muonIEt", "muonIEta", "muonIPhi")),
    ("jets", "jets", ("jetIEt", "jetIEta", "jetIPhi")),
    ("e-gammas", "egammas", ("egIEt", "egIEta", "egIPhi")),
    ("taus", "taus", ("tauIEt", "tauIEta", "tauIPhi")),
    ("ET, HT", "ET", ("Et", None, None)),
    ("MET, MHT, FET, FHT", "MET", ("Et", None, "phi")),
)

LICENCE = """CC0 1.0 Universal Public Domain Dedication

The person who associated a work with this deed has dedicated the work to the
public domain by waiving all rights to the work worldwide under copyright law,
including all related and neighbouring rights, to the extent allowed by law.

You can copy, modify, distribute and use the work, even commercially, without
asking permission.

Deed:        https://creativecommons.org/publicdomain/zero/1.0/
Legal code:  https://creativecommons.org/publicdomain/zero/1.0/legalcode

Attribution is not legally required. It is still requested as a scholarly
courtesy: cite this record by its DOI, and the accompanying data descriptor once
it is published.
"""

CARD = """# L1 trigger anomaly-detection dataset

Level-1 trigger objects from the CMS experiment at the LHC: {zb_events:,} zero-bias
events recorded in 2025, alongside {n_signal} simulated signal samples and one simulated
zero-bias-like background sample. The record is built for unsupervised anomaly
detection, so a model trains on the zero-bias events and is validated against signals it
never saw.

Every recorded event is here, and every in-time object. The saturation cuts the
accompanying study applied are documented below rather than applied to the files, so you
can reproduce that study exactly or depart from it wherever you choose. Three further
reductions were made when the files were produced, before any of that, and "What is not
here" lists them.

## What version 2 corrects

Version 1 of this record shipped a wrong `ET/ETTEM` column. The producer read it with
the wrong sum-type flag, so almost every value came out zero. Version 2 reads the
correct flag, and `ETTEM` now carries the electromagnetic part of the total transverse
energy as documented. Every other column is unchanged, `ET/Et` included, and so is the
partition into train, valid and test.

## Layout

```
zerobias/<run>/{{train,valid,test}}/<object>/*.parquet
signal/<sample>/{{valid,test}}/<object>/*.parquet
background/<sample>/{{valid,test}}/<object>/*.parquet
```

The record holds that tree as three archives, `train.tar`, `valid.tar` and `test.tar`,
each unpacking straight into the paths above with no wrapping directory, so you can take
only the split you need. Zero bias is the only source of training data, and the
simulated samples appear in `valid.tar` and `test.tar`. The card and the licence sit
loose in the record, readable without downloading anything.

One directory holds one object collection, sharded across parquet files. Every
collection of a split has the same rows in the same order, so row *i* of `jets/` and row
*i* of `muons/` describe one event.

Objects: `ET`, `FET`, `FHT`, `HT`, `MET`, `MHT`, `egammas`, `event_info`, `jets`,
`muons`, `seeds`, `taus`.

`seeds/` holds the per-event decision of every unprescaled algorithm in the L1 menu, and
takes about a third of the total volume, so skip it if you want kinematics alone.

## What is not here

Three reductions were made when the parquet was written, and no later step undoes them.

**Out-of-time objects.** The trigger records objects from the five bunch crossings
around the triggered one, and only the central crossing is written out. No event is
lost, only objects, and the `Bx` column that would identify them is not kept either.

**CICADA.** The CICADA score and the `L1_CICADA_*` menu bits are another anomaly
trigger's output rather than detector input, so they are excluded. One consequence is
worth knowing: `L1bit` in `seeds/` is the OR over the algorithms as they stood before
that exclusion, so it can be true on an event where every published bit is false.

**Everything off the producer's allow-list.** The collections carry what the global
trigger sees and nothing else, so tower-level quantities, pile-up estimates, the float
duplicates of the integer branches, and the muon shower flags are all absent, and
`seeds/` keeps the unprescaled algorithms alone.

## Splits

The zero-bias data are split 60/20/20. The simulated samples are validation-only and are
split 60/40 between `valid` and `test`.

| split | events |
|---|---|
{split_table}

The split was drawn once with NumPy's PCG64 generator seeded with **{seed}**, over the
events passing the event cut below, with the two zero-bias runs concatenated in the
order `{zb_order}`.

## Reproducing the study's preprocessing

Four steps, in this order. None of them needs code from the study, since every threshold
and count is given here.

**1. Rename.** Muons, jets, e-gammas and taus carry their original ntuple field names,
and the study renames three of them per collection:

| collection | raw | renamed |
|---|---|---|
| muons | `muonIEt`, `muonIEta`, `muonIPhi` | `Et`, `eta`, `phi` |
| jets | `jetIEt`, `jetIEta`, `jetIPhi` | `Et`, `eta`, `phi` |
| e-gammas | `egIEt`, `egIEta`, `egIPhi` | `Et`, `eta`, `phi` |
| taus | `tauIEt`, `tauIEta`, `tauIPhi` | `Et`, `eta`, `phi` |

Everything else in those collections keeps its ntuple name, so `muonQual`, `muonChg`,
`muonIEtaAtVtx`, `egIso`, `jetHwQual`, `jetRawEt` and `tauIso` are unchanged, and a
mixture of renamed and original names is intended.

The energy sums work differently. The ntuple stores all six in one branch tagged by sum
type, so the producer demultiplexes them into six collections and names the fields
itself: `ET` carries `Et` and `ETTEM`, `HT` carries `Et` and `tower_count`, and `MET`,
`MHT`, `FET` and `FHT` each carry `Et` and `phi`. `event_info` keeps its ntuple names
and gains `split` and `order`.

Every column is a variable-length list per event, the single-valued ones included:
`run`, `lumi`, `event`, `bx`, `orbit`, `time`, `nPV_True` and the six sums all arrive as
length-1 lists.

**2. Cuts.** These are counter limits rather than physics selections.

| kind | cut | effect |
|---|---|---|
| event | `ET.Et < {et_sat}` | drops the event entirely |
| object | `Et < {obj_cut}` on muons, e-gammas, jets and taus | removes that object, keeps the event |
| object | `FET.Et < {fet_sat}` | removes that entry, keeps the event |

For muons, e-gammas and taus, {obj_cut} is where the hardware stops: their `Et` is
{obj_bits} bits wide. Jet `Et` is {jet_bits} bits wide and saturates at {jet_sat}
instead, so the same threshold applied to jets is the study's own choice rather than a
counter limit, and jets above it are ordinary values.

The event cut removes {dropped:,} of {total_raw:,} zero-bias events ({dropped_pct}).
Those events **are published**: they carry `order = -1` in `event_info` and sit at the
end of their split.

**3. Normalise.** Per collection and feature, subtract the median and divide by the 5-95
interquantile range, both fitted on the training split alone and over real (unpadded)
constituents. The constants are not shipped, because the training split here recomputes
them exactly. Fit on train, then apply those same constants to valid and test; refitting
per split would leak.

**4. Pad to a fixed shape.** Keep {nconst}, padding with zeros, which gives
`(N, {nrows}, {nfeats})`, and flatten for the {nflat} features the models take. Stack
the collections in the order {stack_order}, and the features within each as `Et`, `eta`,
`phi`. `FET` has no eta, so that slot is zeroed and masked. A companion boolean mask
marks the real constituents.

## Units

Values are integer hardware units, as the trigger produces them, and nothing in the
files is scaled. Multiply by these to get GeV, radians and pseudorapidity:

| collection | Et | eta | phi |
|---|---|---|---|
{units_table}

Those decimals are rounded. The steps are exact fractions: calorimeter eta is 0.0870/2,
muon eta is 0.0870/8, calorimeter phi is 2*pi/144, and muon phi is 2*pi/576.
`muonIEtaAtVtx` and `muonIPhiAtVtx` take the same scales as muon eta and phi. Quality,
charge, isolation, index and tower-count fields are already integers and unscaled, as is
every `event_info` field and every `seeds` bit.

The four object collections are jagged, holding one entry per in-time object up to the
global trigger's capacity of {capacities}, with no padding and no truncation.

## Things that will catch you out

**The menu differs between data and simulation.** Zero bias carries 183 algorithm
columns and simulation carries 161, of which 147 are shared, and the two do not order
them the same way. Select seeds by name, never by position.

**`nPV_True` carries two types.** It is float32 in zero bias and int32 in simulation, so
concatenating the two without a cast fails on type promotion.

**`jetRawEt` is zero throughout the zero-bias data.** The branch is unfilled in data
ntuples, though it carries real values in simulation.

## Reading the row order

Within a split, rows sit in the order the study consumed them, so reading front to back
after applying the event cut reproduces its input row for row. `event_info` carries two
columns the ntuple does not: `split`, so a file separated from its directory is still
self-describing, and `order`, the position in that ordering, which is `-1` for the
events the study's cut removed.

**A split can span several directories.** The two zero-bias runs were permuted together,
so their training rows interleave and `order` counts across the whole split rather than
within one run. To rebuild the study's order, read both run directories, concatenate
them, then stable-sort by `order` with the `-1` rows left at the end. Concatenating one
run after the other gives the right rows in the wrong order.

## Notes for comparison

If you are comparing against the accompanying study, two of its choices matter. It
evaluated each simulated sample on the first 163,840 events of that sample's split alone
while using the zero-bias split in full, and it assigned sample labels by sorted sample
name, with zero bias 0, the simulated background -1, and the signals 1 upward.

## Provenance

Zero-bias data: CMS, 2025, runs {runs}. Simulated samples: CMS Run 3 Winter25 campaign.
The values are the Level-1 trigger's own reconstructed objects rather than offline
reconstruction.

This record is the archival copy. A mirror carrying one row per event, which suits
loaders that expect a single table, will follow on HuggingFace.

## Licence

CC0 1.0, a public domain dedication with no restrictions on reuse. See `LICENSE`.
Citation by DOI is requested as a courtesy, not required.
"""


def render(summary: dict) -> str:
    """Fill the card from the frozen split summary and the producer's own schema.

    The "What version 2 corrects" section is specific to this release rather than
    generated, so a later version has to rewrite it.

    :param summary: Contents of ``metadata/split_summary.json``. Its
        ``dataset_version`` is deliberately not read, because that file travels with the
        release unchanged and still names the version it was first written for.
    """
    return _rewrap(CARD.format(
        split_table=split_table(summary["datasets"]),
        seed=summary["split_seed"],
        units_table=units_table(),
        capacities=capacities(),
        **event_counts(summary["datasets"]),
        **cut_limits(),
        **tensor_shape(),
    ))


def event_counts(datasets: dict) -> dict:
    """Zero-bias totals the card quotes, and the runs that supplied them."""
    zerobias = {k: v for k, v in datasets.items() if v["category"] == "zerobias"}
    total = sum(v["raw_events"] for v in zerobias.values())
    dropped = total - sum(v["events_passing_filter"] for v in zerobias.values())

    return {
        "zb_events": total,
        "total_raw": total,
        "dropped": dropped,
        "dropped_pct": f"{100 * dropped / total:.4f}%",
        "zb_order": " then ".join(sorted(zerobias)),
        "runs": ", ".join(sorted(k.replace("ZB_run", "") for k in zerobias)),
        "n_signal": sum(1 for v in datasets.values() if v["category"] == "signal"),
    }


def split_table(datasets: dict) -> str:
    """The events table, zero bias split by split and every simulated sample on one row."""
    rows = [
        f"| zero-bias {split} | {_split_total(datasets, split):,} |"
        for split in SPLITS
        if _split_total(datasets, split)
    ]
    rows += [
        f"| {name} valid / test | {datasets[name]['counts'].get('valid', 0):,}"
        f" / {datasets[name]['counts'].get('test', 0):,} |"
        for name in sorted(k for k, v in datasets.items() if v["category"] != "zerobias")
    ]

    return "\n".join(rows)


def units_table() -> str:
    """The hardware-to-physical factors, one row per group of collections."""
    return "\n".join(
        f"| {label} | " + " | ".join(_factor(obj, feat) for feat in feats) + " |"
        for label, obj, feats in UNIT_ROWS
    )


def capacities() -> str:
    """The global trigger's per-event capacity for each object collection."""
    documented = schema.documented_capacities()

    return _listed([f"{documented[obj]} {name}" for obj, name in DISPLAY.items()])


def cut_limits() -> dict:
    """Saturation codes and bit widths behind the cuts table, read off the specification.

    ``obj_cut`` is the study's threshold on the four object collections. It coincides
    with the hardware limit for muons, e-gammas and taus, and does not for jets, which
    is why both are stated.
    """
    return {
        "et_sat": _saturation("ET", "Et"),
        "fet_sat": _saturation("FET", "Et"),
        "obj_cut": adl1t_l1ad.OBJECT_CUTS["muons"],
        "obj_bits": _bits("muons", "muonIEt"),
        "jet_bits": _bits("jets", "jetIEt"),
        "jet_sat": _saturation("jets", "jetIEt"),
    }


def tensor_shape() -> dict:
    """The padded tensor's shape and the constituent counts that produce it."""
    kept = adl1t_l1ad.NCONST
    rows, feats = sum(kept.values()), len(adl1t_l1ad.SCHEMA)
    counts = [f"{kept[obj]} {name}" for obj, name in DISPLAY.items()]

    return {
        "nconst": _listed(counts + [f"{kept['FET']} FET entry"]),
        "stack_order": _listed([DISPLAY.get(obj, obj) for obj in sorted(kept)]),
        "nrows": rows,
        "nfeats": feats,
        "nflat": rows * feats,
    }


def _split_total(datasets: dict, split: str) -> int:
    """Zero-bias events in one split, summed over the runs that contribute to it."""
    return sum(
        v["counts"].get(split, 0) for v in datasets.values() if v["category"] == "zerobias"
    )


def _factor(obj: str, feature: str | None) -> str:
    """One unit-table cell, blank where the collection has no such field."""
    if feature is None:
        return " "

    scale, unit = schema.unit_scale(obj, feature)

    return f"{scale:.6g}" if unit == "eta" else f"{scale:.6g} {unit}"


def _saturation(obj: str, feature: str) -> int:
    """The all-ones code of one feature, i.e. the value its counter stops at."""
    return schema.saturation_code(schema.documented_features()[obj][feature])


def _bits(obj: str, feature: str) -> int:
    return schema.documented_features()[obj][feature]["bits"]


def _listed(items: list[str]) -> str:
    """Join with commas and a final 'and', as prose rather than as a list."""
    return ", ".join(items[:-1]) + f" and {items[-1]}" if len(items) > 1 else items[0]


def _rewrap(text: str) -> str:
    """Reflow the prose, leaving headings, tables and fenced blocks as they are."""
    return "\n\n".join(
        block if block.startswith(("#", "|", "```")) else _fill(block)
        for block in text.split("\n\n")
    )


def _fill(block: str) -> str:
    """Wrap one paragraph without splitting identifiers such as ``adl1t-l1ad``."""
    return textwrap.fill(
        " ".join(block.split()), width=WRAP, break_long_words=False, break_on_hyphens=False
    )
