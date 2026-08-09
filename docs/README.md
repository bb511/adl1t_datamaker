# L1TNtuple to parquet

The conversion keeps what the global trigger (uGT) sees, together with the metadata that says which event it saw.
The rest of the L1TNtuple is dropped: float reconstructions, detector-level branches that never reach the trigger boards, and the objects of neighbouring bunch crossings.
The tables below describe every feature that reaches the parquet; a tick in the `in` column marks it as written.

The ranges, steps, and bit widths come from the [scales](./scales_inputs_2_ugt.pdf) and [firmware](./gt-mp7-firmware-specification.pdf) specifications.
The explanatory text was assembled from exchanges with subsystem experts and carries no citation: read the numbers as specification and the descriptions as expert opinion.
Where a description says a quantity is not yet defined, that reports the state of the subsystem, not a gap in this document.

> [!IMPORTANT]
> This file is parsed. `src/adl1t_datamaker/schema.py` reads the tables below into the feature specification behind the summary reports, the validation checks, and the dataset card, and `tests/test_schema_matches_docs.py` fails when the converter and these tables disagree.
> The prose can be edited freely. The parser depends on the items below, each failing silently rather than loudly, except the last:
>
> - Each `##` heading keeps its exact title. An unknown `##` heading ends the section, so nothing new may be inserted inside one; that is why the seeds section below is invisible to the parser. Under `## Energy Objects` only the first word of each `###` title is read, and it must be the parquet folder name.
> - A table row begins with `|` in the first column. One leading space and that feature is gone.
> - The header row's first cell reads `Feature`, and its remaining cells are found by the exact names `Range`, `Step`, `Bits`, and `Explanation`.
> - A row counts as a feature only when its first cell *starts* with a backticked name, and as converted only when its `in` cell contains the literal `:heavy_check_mark:`.
> - A `Range` beginning `0..` marks the feature as unsigned, which turns on the check that no measured value exceeds the all-ones code of its `Bits`. The number after `0..` is never read.
> - A capacity is matched as "There are N ... objects" with exactly one word where the ellipsis is. Reword it and the multiplicity check for that object stops running.
>
> The exception is the `in` column, whose header is looked up without a fallback, so renaming it raises rather than passing quietly.

# Objects

An `I` in a feature name abbreviates `Integer` and marks a quantity taken straight from hardware, but its absence means nothing: `muonQual`, `muonChg`, `muonTfMuonIdx`, `jetHwQual`, `jetRawEt`, `egIso`, and `tauIso` are hardware integers too.
Every value keeps its hardware units, so a reader that wants GeV or radians applies the `Step` column itself.

Each event carries objects from five bunch crossings, ±2 around the one that fired.
The conversion keeps crossing 0 alone, selected through each particle collection's `Bx` branch and through `sumBx` for the energy sums, and drops the `Bx` column itself, so the parquet cannot say which crossing an object came from.
No event is lost, only the objects of the other crossings; the CICADA score, one number per event, has no crossing to select.

Each object is stored in its own folder, holding one parquet file per input L1Ntuple.
Row $i$ of every folder is the same event, so the folders can be read separately and joined by position.
The four particle collections are jagged, one entry per in-time object: nothing is padded and nothing is truncated.

## Muon Objects

> [!NOTE]
> There are 8 muon objects at most, the global trigger's capacity per event.

The L1TNtuple also carries `nMuons`, `muonIDEta`, `muonIDPhi`, `nMuonShowers`, `muonShowerBx`, `muonShowerOneNominal`, `muonShowerOneTight`, `muonShowerTwoLoose`, `muonShowerTwoLooseDiffSectors`, and float versions of `muonIEt`, `muonIEtUnconstrained`, `muonIEta`, `muonIPhi`, `muonIEtaAtVtx`, and `muonIPhiAtVtx` (the same names without `I`).
None of these reaches the global trigger, so none is converted.

| Feature       |     Range     |      Step     |      Bits     |  Explanation  |      in       |
| ------------- | ------------- | ------------- | ------------- | ------------- | ------------- |
| `muonIPhiAtVtx` $\varphi\mathrm{\,\,(extrapolated)}$  |  2 π  | 2π/576 ~ 0.011 | 10 | Muon azimuthal angle extrapolated to the centre of the detector. Layer 2 of the global trigger system is performing the extrapolation in a rudimentary way; if latency allows, a more sophisticated extrapolation, e.g., using an ML method, is preferable. | :heavy_check_mark: |
| `muonIEt` $p_t$  |  0..256 GeV  | 0.5 | 9 | The muon transverse momentum (a proxy for its transverse energy). | :heavy_check_mark: |
| `muonQual` quality  |  -  | - | 4 | The muon quality is represented by 4 bits. A hit in each of the muon stations flips its corresponding bit to 1. The three muon track finding systems assign quality differently: the BMTF covers the barrel, $\lvert\eta\rvert \lesssim 0.83$, the OMTF the overlap, $0.83 \lesssim \lvert\eta\rvert \lesssim 1.24$, and the EMTF the endcaps beyond that. Each requires a quality higher than 12, i.e., the first two bits are 1, but how that quality is arrived at is peculiar to each system. | :heavy_check_mark: |
| `muonIEtaAtVtx` $\eta \mathrm{\,\,(extrapolated)}$  |  2π  | 0.0870/8=0.010875 | 8+1 | Muon polar angle extrapolated to the centre of the detector. The explanation is the same as for $\phi$. | :heavy_check_mark: |
| `muonIso` iso  |  -  | - | 2 | Muon isolation. The isolation is stored in two bits, corresponding to two types of isolation. However, the meaning of this isolation is not defined yet in the uGMT system: the uGMT has the capability to create an isolation variable but the calorimeter links were never commissioned. | :x: |
| `muonChg` charge sign  |  -  | - | 1 | Muon charge determined from the muon bending trajectory. `-1` is negative charge while `1` is positive charge. | :heavy_check_mark: |
| charge valid  |  -  | - | 1 | This is set to `0` whenever one cannot determine the charge. This can happen when the track is too straight, e.g., in the case of very high momentum muons. | :x: |
| `muonTfMuonIdx` index bits |  -  | - | 7 | Seven index bits are enough to number the 108 muon slots the track finders deliver to the global trigger, and the position within that ordering says which subsystem a muon came from. The first 18 slots come from the EMTF, the next 18 from the OMTF, the next 36 from the BMTF, then a further 18 from the OMTF, and the last 18 again from the EMTF. | :heavy_check_mark: |
| `muonIPhi` $\varphi$ (out)  |  2π  | 2π/576 ~ 0.011 | 10 | This is just the raw version of the extrapolated azimuthal angle mentioned above. One can use this to obtain more refined versions of the phi at vertex. | :heavy_check_mark: |
| `muonIEta` $\eta$ (out)  |  2π  | 0.0870/8=0.010875 | 8+1 | This is just the raw version of the extrapolated polar angle mentioned above. One can use this to obtain more refined versions of the eta at vertex. | :heavy_check_mark: |
| `muonIEtUnconstrained` unconstrained $p_t$  |  0..256 GeV  | 1 | 8 | The transverse momentum not constrained to the vertex. Lower resolution when compared with the momentum defined above, but useful in the case of offset muons, since it can be more precise than its constrained counterpart. | :heavy_check_mark: |
| hadronic shower trigger |  -  | - | 1 | Whether one observes a hadronic shower in the muon detectors. Very experimental feature and not useful for training the anomaly detector. | :x: |
| `muonDxy` impact parameter  |  -  | - | 2 | Displacement with respect to primary vertex. Not defined yet. | :x: |


## Jet Objects

> [!NOTE]
> There are 12 jet objects at most, the global trigger's capacity per event.

The L1TNtuple also carries `jetSeedEt`, `jetTowerIEta`, `jetTowerIPhi`, `jetPUEt`, `jetPUDonutEt0`, `jetPUDonutEt1`, `jetPUDonutEt2`, `jetPUDonutEt3`, and float versions of `jetIEt`, `jetIEta`, and `jetIPhi` (the same names without `I`).
None of these reaches the global trigger, so none is converted.

| Feature       |     Range     |      Step     |      Bits     |  Explanation  |      in       |
| ------------- | ------------- | ------------- | ------------- | ------------- | ------------- |
| `jetIEt` $E_t$  |  0..1024 GeV  | 0.5 | 11 | Jet transverse energy. | :heavy_check_mark: |
| `jetIEta` $\eta$ |  -5..5  | 0.0870/2=0.0435 | 7+1 = 8 | The polar angle of the jet from the centre of the detector. | :heavy_check_mark: |
| `jetIPhi` $\varphi$  |  2π  | 2π/144 ~ 0.044 | 8 | The azimuthal angle of the jet from the centre of the detector. | :heavy_check_mark: |
| DISP |  -  | - | 1 | This bit is used to flag a jet as delayed/displaced based on HCAL timing and depth profiles that are indicative of a “long lived particle” decay. If this bit is set to 1, then the jet is tagged as an LLP. | :x: |
| `jetHwQual` quality flags  |  -  | - | 1 | Based on ECAL/HCAL energy ratio. If this ratio is higher, that means the jet is more likely to not be hadronic, but faked by a high energy lepton or photon. Either tight (2), medium (1), or loose (0). In reality, most jets are 0, with a few having quality 1. | :heavy_check_mark: |
| `jetRawEt` |  -  | - | - | What "raw" means here is undetermined: the branch is present in the L1TNtuple and in the converted parquet, but the `scales` pdf does not define it, and it has no `I` counterpart, the L1TNtuple carrying `jetRawEt` alone. The data ntuples leave it unfilled, so it is identically zero in every converted zero-bias run and only simulation gives it values. | :heavy_check_mark: |

## Egamma Objects

> [!NOTE]
> There are 12 egamma objects at most, the global trigger's capacity per event.

The L1TNtuple also carries `nEGs`, `egTowerIPhi`, `egTowerIEta`, `egRawEt`, `egIsoEt`, `egFootprintEt`, `egNTT`, `egShape`, `egTowerHoE`, `egHwQual`, and float versions of `egIEt`, `egIEta`, `egIPhi`, and `egIRawEt` (the same names without `I`).
None of these reaches the global trigger, so none is converted.

| Feature       |     Range     |      Step     |      Bits     |  Explanation  |      in       |
| ------------- | ------------- | ------------- | ------------- | ------------- | ------------- |
| `egIEt` $E_t$  |  0..256 GeV  | 0.5 | 9 | Transverse energy of the electron or photon. | :heavy_check_mark: |
| `egIEta` $\eta$ |  -5..5  | 0.0870/2=0.0435 | 7+1 = 8 | The polar angle of the electron or photon from the centre of the detector. | :heavy_check_mark: |
| `egIPhi` $\varphi$  |  2π  | 2π/144 ~ 0.044 | 8 | The azimuthal angle of the electron or photon from the centre of the detector. | :heavy_check_mark: |
| `egIso` iso  |  -  | - | 2 | Little activity around the cluster of energy representing the electron/photon means higher isolation: less likely to be a jet. The lowest bit is defined as `isolated` while the highest bit is named `undefined`. Three degrees of isolation are possible, but only two are used, i.e., the `isolated` bit is set and the other is optional, or vice versa. Thus, it's either these two options, or `no isolation`, when all bits are 0. Whatever quality is larger than 0 is treated as the same degree of isolation. Still unclear how these bits are set, i.e., based on exactly what parameters. | :heavy_check_mark: |

## Tau Objects

> [!NOTE]
> There are 12 tau objects at most, the global trigger's capacity per event.

The L1TNtuple also carries `nTaus`, `tauTowerIPhi`, `tauTowerIEta`, `tauRawEt`, `tauRawIEt`, `tauIsoEt`, `tauNTT`, `tauHasEM`, `tauIsMerged`, `tauHwQual`, and float versions of `tauIEt`, `tauIEta`, and `tauIPhi` (the same names without `I`).
None of these reaches the global trigger, so none is converted.

| Feature       |     Range     |      Step     |      Bits     |  Explanation  |      in       |
| ------------- | ------------- | ------------- | ------------- | ------------- | ------------- |
| `tauIEt` $E_t$  |  0..256 GeV  | 0.5 | 9 | Transverse energy of the tau candidate. | :heavy_check_mark: |
| `tauIEta` $\eta$ |  -5..5  | 0.0870/2=0.0435 | 7+1 = 8 | The polar angle of the tau candidate from the centre of the detector. | :heavy_check_mark: |
| `tauIPhi` $\varphi$  |  2π  | 2π/144 ~ 0.044 | 8 | The azimuthal angle of the tau candidate from the centre of the detector. | :heavy_check_mark: |
| `tauIso` iso  |  -  | - | 2 | Little activity around the cluster of energy representing the tau means higher isolation: less likely to be a jet. The lowest bit is defined as `isolated` while the highest bit is named `undefined`. Three degrees of isolation are possible, but only one is used: at least one of the bits needs to be set. Thus, it's either this or `no isolation`, when the bits are all 0. Whatever quality is larger than 0 is treated as the same degree of isolation. Still unclear how these bits are set, i.e., based on what parameters exactly. | :heavy_check_mark: |


## Cicada Objects

CICADA is a separate anomaly detection algorithm running on calorimeter tower data, and its score is the only part of it the global trigger sees.
The score lives in the calorimeter summary tree, so a conversion given no such tree writes no `cica` folder; the unpacked 2025 zero-bias ntuples are of that kind.

> [!NOTE]
> There is one cicada object, in a folder named `cica`, and it is the one column stored flat: one value per event, with no list around it.

| Feature       |     Range     |      Step     |      Bits     |  Explanation  |      in       |
| ------------- | ------------- | ------------- | ------------- | ------------- | ------------- |
| `CICADAScore` |  -  | - | 4 | Anomaly score generated using calorimeter tower data. | :heavy_check_mark: |

## Energy Objects

The level 1 tree gives the six sums one collection rather than a branch each, holding an entry per pair of sum type and bunch crossing, read through the branches `sumType`, `sumBx`, `sumIEt`, and `sumIPhi`.
Each column below is recovered by its `sumType` flag together with `sumBx == 0`, taking its value from `sumIPhi` when the column is a `phi` and from `sumIEt` otherwise, which is why `tower_count` is read from `sumIEt` despite not being an energy.
The flags are 0 for `ET` and 16 for its ECAL part, 1 for `HT` and 21 for its tower count, 2 for `MET`, 3 for `MHT`, 8 for `FET`, and 20 for `FHT`.
`_store_energies` in `src/adl1t_datamaker/root2parquet.py` applies them and `tests/test_sum_types.py` pins them, because a wrong flag yields a plausible column rather than an error: an earlier map read `ETTEM` with the `HT` flag, so every data set produced before the reconversion of 2026-08-08 carries a copy of `HT.Et` in `ET.ETTEM`.

> [!NOTE]
> There are 6 energy objects, one folder each.
> They carry a list layer like the particle collections but should hold exactly one entry per event: a zero would mean the sum was absent and a two that a neighbouring crossing survived the mask, and the summary fails a data set where either happens.

### ET ($E_t$)
The transverse energy object.

| Feature       |     Range     |      Step     |      Bits     |  Explanation  |      in       |
| ------------- | ------------- | ------------- | ------------- | ------------- | ------------- |
| `Et` $E_t$ |  0..2048 GeV  | 0.5 | 12 | Transverse energy of the whole event. | :heavy_check_mark: |
| `ETTEM` $E_t$ (ECAL) | 0..2048 GeV  | 0.5 | 12 | Transverse energy in the ECAL of the whole event. | :heavy_check_mark: |
| minimum bias HF  |  0..15  | - | 4 | *Not in the L1Ntuple.* Based on the Hadronic Forward Calorimeter fine grain bits. The algorithm foresees a trigger when one of the HF tower on at least one side of HF (OR) or one tower on each side (AND) is above a defined ADC threshold. | :x: |

### HT
The scalar sum of the jet transverse energies of the event, over ECAL and HCAL. The vectorial counterpart is `MHT`.

| Feature       |     Range     |      Step     |      Bits     |  Explanation  |      in       |
| ------------- | ------------- | ------------- | ------------- | ------------- | ------------- |
| `Et` $E_t$ |  0..2048 GeV  | 0.5 | 12 | Scalar sum of the jet transverse energies of the event. | :heavy_check_mark: |
| `tower_count` TOWERCOUNT | 0..8191 | 1 | 13 | Number of "towers" (experimental signatures left by hadrons in the calorimeter) measured in the HCAL. | :heavy_check_mark: |
| minimum bias HF  |  0..15  | - | 4 | *Not in the L1Ntuple.* Based on the Hadronic Forward Calorimeter fine grain bits. The algorithm foresees a trigger when one of the HF tower on at least one side of HF (OR) or one tower on each side (AND) is above a defined ADC threshold. | :x: |

### MET ($ET_\mathrm{miss}$)
The missing transverse energy object.

| Feature       |     Range     |      Step     |      Bits     |  Explanation  |      in       |
| ------------- | ------------- | ------------- | ------------- | ------------- | ------------- |
| `Et` $E_t$ |  0..2048 GeV  | 0.5 | 12 | The missing transverse energy magnitude. | :heavy_check_mark: |
| `phi` $\varphi$ | 2π  | 2π/144 ~ 0.044 | 8 | The azimuthal angle of the missing transverse energy vector. | :heavy_check_mark: |
| ASYMET | 0..255 | 1 | 8 | The asymmetry in the missing transverse energy vector. A measure of the energy imbalance in the Hadronic Calorimeter.  **Only used for heavy ion runs and thus ignored for the current parquet generation.** | :x: |
| minimum bias HF  |  0..15  | - | 4 | *Not in the L1Ntuple.* Based on the Hadronic Forward Calorimeter fine grain bits. The algorithm foresees a trigger when one of the HF tower on at least one side of HF (OR) or one tower on each side (AND) is above a defined ADC threshold. | :x: |

### MHT ($HT_\mathrm{miss}$)
The missing transverse hadronic energy object.

| Feature       |     Range     |      Step     |      Bits     |  Explanation  |      in       |
| ------------- | ------------- | ------------- | ------------- | ------------- | ------------- |
| `Et` $E_t$ |  0..2048 GeV  | 0.5 | 12 | The hadronic missing transverse energy magnitude. | :heavy_check_mark: |
| `phi` $\varphi$ | 2π  | 2π/144 ~ 0.044 | 8 | The azimuthal angle of the hadronic missing transverse energy vector. | :heavy_check_mark: |
| ASYMHT | 0..255 | 1 | 8 | The asymmetry in the missing hadronic transverse energy vector.  A measure of the energy imbalance in the Hadronic Calorimeter. **Only used for heavy ion runs and thus ignored for the current parquet generation.** | :x: |
| minimum bias HF  |  0..15  | - | 4 | *Not in the L1Ntuple.* Based on the Hadronic Forward Calorimeter fine grain bits. The algorithm foresees a trigger when one of the HF tower on at least one side of HF (OR) or one tower on each side (AND) is above a defined ADC threshold. | :x: |

### FET ($ET^\mathrm{HF}_\mathrm{miss}$)
The missing transverse energy object including data from the forward hadronic calorimeter object.

| Feature       |     Range     |      Step     |      Bits     |  Explanation  |      in       |
| ------------- | ------------- | ------------- | ------------- | ------------- | ------------- |
| `Et` $E_t$ |  0..2048 GeV  | 0.5 | 12 | The missing transverse energy magnitude including the missing transverse energy from the forward hadronic calorimeter. | :heavy_check_mark: |
| `phi` $\varphi$ | 2π  | 2π/144 ~ 0.044 | 8 | The azimuthal angle of the missing transverse energy vector including information from the forward hadronic calorimeter. | :heavy_check_mark: |
| ASYMETHF | 0..255 | 1 | 8 | The asymmetry in the forward missing transverse energy object.  A measure of the energy imbalance in the Hadronic Forward Calorimeter. **Only used for heavy ion runs and thus ignored for the current parquet generation.** | :x: |
| CENT[3:0] | - | - | 4 | The centrality of the missing transverse energy vector, defined by the first 4 bits. It specifies the degree of overlap between colliding ions. **Only used for heavy ion runs and thus ignored for the current parquet generation.**  | :x: |
| minimum bias HF  |  0..15  | - | 4 | *Not in the L1Ntuple.* Based on the Hadronic Forward Calorimeter fine grain bits. The algorithm foresees a trigger when one of the HF tower on at least one side of HF (OR) or one tower on each side (AND) is above a defined ADC threshold. | :x: |

### FHT ($HT^\mathrm{HF}_\mathrm{miss}$)
The missing hadronic transverse energy object including data from the forward hadronic calorimeter object.

| Feature       |     Range     |      Step     |      Bits     |  Explanation  |      in       |
| ------------- | ------------- | ------------- | ------------- | ------------- | ------------- |
| `Et` $E_t$ |  0..2048 GeV  | 0.5 | 12 | The hadronic missing transverse energy magnitude including the missing transverse energy from the forward hadronic calorimeter. | :heavy_check_mark: |
| `phi` $\varphi$ | 2π  | 2π/144 ~ 0.044 | 8 | The azimuthal angle of the hadronic missing transverse energy vector including information from the forward hadronic calorimeter. | :heavy_check_mark: |
| ASYMETHF | 0..255 | 1 | 8 | The asymmetry in the forward hadronic missing transverse energy object.  A measure of the energy imbalance in the Hadronic Forward Calorimeter. **Only used for heavy ion runs and thus ignored for the current parquet generation.** | :x: |
| CENT[7:4] | - | - | 4 | The centrality of the missing transverse energy vector, defined by the last 4 bits. It specifies the degree of overlap between colliding ions. **Only used for heavy ion runs and thus ignored for the current parquet generation.**  | :x: |
| minimum bias HF  |  0..15  | - | 4 | *Not in the L1Ntuple.* Based on the Hadronic Forward Calorimeter fine grain bits. The algorithm foresees a trigger when one of the HF tower on at least one side of HF (OR) or one tower on each side (AND) is above a defined ADC threshold. | :x: |

## Event Information

All the following features are integers, apart from `nPV_True` in recorded data.

| Feature       |  Explanation  |      in       |
| ------------- | ------------- | ------------- |
| `run` | The CMS run that the event corresponds to. | :heavy_check_mark: |
| `lumi` | The luminosity section, i.e., a range of events that the event is included in. | :heavy_check_mark: |
| `event` | The event number. | :heavy_check_mark: |
| `bx` | The bunch crossing number within the orbit, identifying which of the LHC's 3564 slots produced the event, so that over a run this column reflects the filling scheme. | :heavy_check_mark: |
| `orbit` | The orbit number, one orbit being a full revolution of the beam and hence a complete pass through the 3564 bunch crossing slots. Together with `bx` it places the event at a crossing. Simulation has neither to record and writes the all-ones value into both this column and `bx`. | :heavy_check_mark: |
| `time`  | The wall clock time of the event, packed as Unix seconds shifted left by 32 bits with the microseconds in the low word, i.e. `seconds = time >> 32` and `microseconds = time & 0xFFFFFFFF`. | :heavy_check_mark: |
| `nPV_True` | The pileup of the events, i.e., the number of auxiliary proton collisions that happen in the same event. The stored type follows the source: `float32` in recorded data, where the value is a brilcalc measurement per lumi section, and `int32` in simulation, where it is the generated count. Concatenating the two therefore needs an explicit cast. | :heavy_check_mark: |

## Level 1 Seeds

The `seeds` folder holds one boolean column per trigger algorithm: the final decision the global trigger reached for that algorithm on that event.
The columns are named after the algorithms, e.g. `L1_SingleMu22`, and each is a length-1 list per event.

Only the unprescaled algorithms are kept.
A prescaled algorithm records one accept in every `n`, so its column would measure the prescale rather than the physics; `unprescaled_names` in `src/adl1t_datamaker/components/l1_seeds.py` reads the menu CSV and keeps the algorithms whose prescale is 1.
Which algorithms survive therefore depends on the menu: runs 396102 and 398183 (`L1Menu_Collisions2025_v1_3_0`) leave 190 unprescaled, the Winter25 simulation (`L1Menu_Collisions2024_v1_3_0_last`) 164, and only 150 names are common to the two.
The columns are not in the same order either, so select by name, never by position.
The published release quotes 183, 161, and 147 for the same three numbers, because it drops the `L1_CICADA_*` columns as another anomaly trigger's output rather than detector input.

The conversion also writes one synthesised column, `L1bit`, the logical OR of every algorithm kept.
It appears in no menu, and it is computed at conversion time, so a downstream step that drops columns leaves `L1bit` describing the wider set it was built from.

The decision stored is the final one rather than the initial one: an algorithm that accepted an event can still read 0, because the trigger rules cap how often accepts may follow one another.
`get_initial_decision` and `get_final_decision` in the same module expose both.
