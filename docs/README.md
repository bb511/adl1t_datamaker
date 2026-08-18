# L1TNtuple to parquet

The conversion code in this repository constructs parquet files that contain information on what the global trigger (uGT) records during a run,
along with metadata corresponding to each event.
The inputs to these scripts are L1Ntuples, which are in CERN ROOT tree data format.
The code in this repository only keeps a subset of the data available in the L1TNtuples;
the rest are dropped: float reconstructions, detector-level branches that never reach the trigger boards, and the objects of neighbouring bunch crossings.
The tables below describe every feature that reaches the parquet files.

The ranges, steps, and bit widths come from the [scales](./scales_inputs_2_ugt.pdf) and [firmware](./gt-mp7-firmware-specification.pdf) specifications.
The explanatory text was assembled from exchanges with subsystem experts.
If a description says a quantity is not yet defined, that reports the state of the subsystem, not a gap in this document.

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

An `I` in a feature name abbreviates `Integer` and marks a quantity taken straight from hardware.
The absence of `I` does not signify float values: for example, `muonQual`, `muonChg`, `muonTfMuonIdx`, `jetHwQual`, `jetRawEt`, `egIso`, and `tauIso` are hardware integers too.
Every value is in hardware units.
If you want GeV or radians, apply the `Step` column.

Each event contains objects from five bunch crossings, ±2 around the one that fired.
The conversion keeps only crossing 0, selected through each particle collection's `Bx` branch and through `sumBx` for the energy sums, and drops the `Bx` column itself.

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
| `muonIPhiAtVtx` $\varphi\mathrm{\,\,(extrapolated)}$  |  2 π  | 2π/576 ~ 0.011 | 10 | Muon azimuthal angle extrapolated to the centre of the detector. The global muon trigger (uGMT) performs the extrapolation in a rudimentary way and forwards it to the global trigger system. | :heavy_check_mark: |
| `muonIEt` $p_t$  |  0..256 GeV  | 0.5 | 9 | The muon transverse momentum (a proxy for its transverse energy). Hardware index `0` means invalid muon. Hence, to convert to GeV, subtract `1` from the hardware value before conversion. | :heavy_check_mark: |
| `muonQual` quality  |  -  | - | 4 | The muon quality is represented by 4 bits. These 4 bits represent a quality class assigned by each track finder. The quality classes are derived by each system through LUTs based on the station's hit pattern and associated attributes, like angular distribution. The three muon track finding systems each cover a different detector area: the BMTF covers the barrel, $\lvert\eta\rvert \lesssim 0.83$, the OMTF the overlap, $0.83 \lesssim \lvert\eta\rvert \lesssim 1.24$, and the EMTF the endcaps beyond that. The single muon triggers apply a quality cut of at least 12. For example, a `muonQual` of 12-15 means that the two most significant bits are set. | :heavy_check_mark: |
| `muonIEtaAtVtx` $\eta \mathrm{\,\,(extrapolated)}$  |  -2.45..2.45  | 0.0870/8=0.010875 | 8+1 | Muon pseudorapidity extrapolated to the centre of the detector. The explanation is the same as for $\phi$. | :heavy_check_mark: |
| `muonIso` iso  |  -  | - | 2 | Muon isolation. The isolation is stored in two bits, corresponding to two types of isolation. However, the meaning of this isolation is not defined yet in the uGMT system: the uGMT has the capability to create an isolation variable but the calorimeter links were never commissioned. | :x: |
| `muonChg` charge sign  |  -  | - | 1 | Muon charge determined from the muon bending trajectory. `-1` is negative charge while `1` is positive charge. `0` means the charge-valid bit is unset. | :heavy_check_mark: |
| charge valid  |  -  | - | 1 | This is set to `0` whenever one cannot determine the charge. This can happen when the track is too straight, e.g., in the case of very high momentum muons. | :x: |
| `muonTfMuonIdx` index bits |  -  | - | 7 | Seven index bits are enough to number the 108 muon slots the track finders deliver to the global trigger, and the position within that ordering says which subsystem a muon came from. The first 18 slots come from the EMTF, the next 18 from the OMTF, the next 36 from the BMTF, then a further 18 from the OMTF, and the last 18 again from the EMTF. | :heavy_check_mark: |
| `muonIPhi` $\varphi$ (out)  |  2π  | 2π/576 ~ 0.011 | 10 | This is just the raw version of the extrapolated azimuthal angle mentioned above. One can use this to obtain more refined versions of the phi at vertex. | :heavy_check_mark: |
| `muonIEta` $\eta$ (out)  |  -2.45..2.45  | 0.0870/8=0.010875 | 8+1 | This is just the raw version of the extrapolated pseudorapidity mentioned above. One can use this to obtain more refined versions of the eta at vertex. | :heavy_check_mark: |
| `muonIEtUnconstrained` unconstrained $p_t$  |  0..256 GeV  | 1 | 8 | The transverse momentum not constrained to the vertex. Hardware index `0` means invalid muon. Hence, to convert to GeV, subtract `1` from the hardware value before conversion. Lower resolution when compared with the momentum defined above, but useful in the case of offset muons, since it can be more precise than its constrained counterpart. | :heavy_check_mark: |
| hadronic shower trigger |  -  | - | 1 | Whether one observes a hadronic shower in the muon detectors. Very experimental feature and not useful for training the anomaly detector. | :x: |
| `muonDxy` impact parameter  |  -  | - | 2 | Displacement with respect to primary vertex. Not used yet, seeds that contain this are disabled. | :x: |


## Jet Objects

> [!NOTE]
> There are 12 jet objects at most, the global trigger's capacity per event.

The L1TNtuple also carries `jetSeedEt`, `jetTowerIEta`, `jetTowerIPhi`, `jetPUEt`, `jetPUDonutEt0`, `jetPUDonutEt1`, `jetPUDonutEt2`, `jetPUDonutEt3`, and float versions of `jetIEt`, `jetIEta`, and `jetIPhi` (the same names without `I`).
None of these reaches the global trigger, so none is converted.

| Feature       |     Range     |      Step     |      Bits     |  Explanation  |      in       |
| ------------- | ------------- | ------------- | ------------- | ------------- | ------------- |
| `jetIEt` $E_t$  |  0..1024 GeV  | 0.5 | 11 | Jet transverse energy. | :heavy_check_mark: |
| `jetIEta` $\eta$ |  -5..5  | 0.0870/2=0.0435 | 7+1 = 8 | The pseudorapidity of the jet from the centre of the detector. | :heavy_check_mark: |
| `jetIPhi` $\varphi$  |  2π  | 2π/144 ~ 0.044 | 8 | The azimuthal angle of the jet from the centre of the detector. | :heavy_check_mark: |
| `jetHwQual` quality flags  |  -  | - | 1 | This bit is set to `1` when a jet contains two or more HCAL-delayed towers. There is an unused 2-bit quality-adjacent field based on ECAL/HCAL energy ratio, either tight (2), medium (1), or loose (0). If this ratio is higher, that means the jet is more likely to not be hadronic, but faked by a high energy lepton or photon. | :heavy_check_mark: |
| `jetRawEt` |  -  | - | - | Raw is the tower sum before pile-up subtraction and calibration. The unpacker never fills this. It is `0` throughout for the ZB data and filled for the `Winter25` simulation. | :heavy_check_mark: |


## Egamma Objects

> [!NOTE]
> There are 12 egamma objects at most, the global trigger's capacity per event.

The L1TNtuple also carries `nEGs`, `egTowerIPhi`, `egTowerIEta`, `egRawEt`, `egIsoEt`, `egFootprintEt`, `egNTT`, `egShape`, `egTowerHoE`, `egHwQual`, and float versions of `egIEt`, `egIEta`, and `egIPhi` (the same names without `I`).
None of these reaches the global trigger, so none is converted.

| Feature       |     Range     |      Step     |      Bits     |  Explanation  |      in       |
| ------------- | ------------- | ------------- | ------------- | ------------- | ------------- |
| `egIEt` $E_t$  |  0..256 GeV  | 0.5 | 9 | Transverse energy of the electron or photon. | :heavy_check_mark: |
| `egIEta` $\eta$ |  -5..5  | 0.0870/2=0.0435 | 7+1 = 8 | The pseudorapidity of the electron or photon from the centre of the detector. | :heavy_check_mark: |
| `egIPhi` $\varphi$  |  2π  | 2π/144 ~ 0.044 | 8 | The azimuthal angle of the electron or photon from the centre of the detector. | :heavy_check_mark: |
| `egIso` iso  |  -  | - | 2 | This entry is based on two lookup tables (LUTs). Bit 0 is the pass flag of egIsolationLUT and bit 1 is the pass flag of egIsolationLUT2. These represent two independent isolation working points, both computed from the energy of the towers, a threshold depending on eta and pt, and tower count. The bit set to 0 is the "Iso" flag and set to 1 is the "LooseIso" flag in the menu. | :heavy_check_mark: |


## Tau Objects

> [!NOTE]
> There are 12 tau objects at most, the global trigger's capacity per event.

The L1TNtuple also carries `nTaus`, `tauTowerIPhi`, `tauTowerIEta`, `tauRawEt`, `tauIsoEt`, `tauNTT`, `tauHasEM`, `tauIsMerged`, `tauHwQual`, and float versions of `tauIEt`, `tauIEta`, and `tauIPhi` (the same names without `I`).
None of these reaches the global trigger, so none is converted.

| Feature       |     Range     |      Step     |      Bits     |  Explanation  |      in       |
| ------------- | ------------- | ------------- | ------------- | ------------- | ------------- |
| `tauIEt` $E_t$  |  0..256 GeV  | 0.5 | 9 | Transverse energy of the tau candidate. | :heavy_check_mark: |
| `tauIEta` $\eta$ |  -5..5  | 0.0870/2=0.0435 | 7+1 = 8 | The pseudorapidity of the tau candidate from the centre of the detector. | :heavy_check_mark: |
| `tauIPhi` $\varphi$  |  2π  | 2π/144 ~ 0.044 | 8 | The azimuthal angle of the tau candidate from the centre of the detector. | :heavy_check_mark: |
| `tauIso` iso  |  -  | - | 2 | Only the first bit is ever set. The second bit is commented out in the emulator. Little activity around the cluster of energy representing the tau means higher isolation: less likely to be a jet. The available bit is set when the isolation energy (tower sum around the cluster minus the tau footprint) passes an eta-, pt- and tower-count-dependent LUT threshold. | :heavy_check_mark: |


## Cicada Objects

CICADA is a separate anomaly detection algorithm running on calorimeter tower data, and its score is the only part of it the global trigger sees.
The score lives in the calorimeter summary tree, so a conversion given no such tree writes no `cica` folder; the unpacked 2025 zero-bias ntuples are of that kind.

> [!NOTE]
> There is one cicada object, in a folder named `cica`, and it is the one column stored flat: one value per event, with no list around it.

| Feature       |     Range     |      Step     |      Bits     |  Explanation  |      in       |
| ------------- | ------------- | ------------- | ------------- | ------------- | ------------- |
| `CICADAScore` |  0..256  | 1/256 | 16 | Anomaly score generated using calorimeter tower data. The precision is `ap_ufixed<16,8>`, i.e., 8 integer bits and 8 fractional bits. | :heavy_check_mark: |


## Energy Objects

The level 1 tree gives the six sums one collection rather than a branch each, holding an entry per pair of sum type and bunch crossing, read through the branches `sumType`, `sumBx`, `sumIEt`, and `sumIPhi`.
Each column below is recovered by its `sumType` flag together with `sumBx == 0`, taking its value from `sumIPhi` when the column is a `phi` and from `sumIEt` otherwise, which is why `tower_count` is read from `sumIEt` despite not being an energy.
The flags are the values of the CMSSW `EtSum::EtSumType` enumeration (`DataFormats/L1Trigger/interface/EtSum.h`), which the L1TNtuple stores verbatim:

| Folder | Column(s)      | `sumType` flag | CMSSW enum name |
| ------ | -------------- | -------------- | --------------- |
| `ET`   | `Et`           | 0              | `kTotalEt`      |
| `ET`   | `ETTEM`        | 16             | `kTotalEtEm`    |
| `HT`   | `Et`           | 1              | `kTotalHt`      |
| `HT`   | `tower_count`  | 21             | `kTowerCount`   |
| `MET`  | `Et`, `phi`    | 2              | `kMissingEt`    |
| `MHT`  | `Et`, `phi`    | 3              | `kMissingHt`    |
| `FET`  | `Et`, `phi`    | 8              | `kMissingEtHF`  |
| `FHT`  | `Et`, `phi`    | 20             | `kMissingHtHF`  |

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
| minimum bias HF  |  0..15  | - | 4 | *Present in the L1Ntuple as a sum type but not converted.* Based on the Hadronic Forward Calorimeter fine grain bits. The algorithm foresees a trigger when one of the HF tower on at least one side of HF (OR) or one tower on each side (AND) is above a defined ADC threshold. | :x: |

### HT
The scalar sum of the jet transverse energies of the event, over ECAL and HCAL. The vectorial counterpart is `MHT`.

| Feature       |     Range     |      Step     |      Bits     |  Explanation  |      in       |
| ------------- | ------------- | ------------- | ------------- | ------------- | ------------- |
| `Et` $E_t$ |  0..2048 GeV  | 0.5 | 12 | Scalar sum of the jet transverse energies of the event. | :heavy_check_mark: |
| `tower_count` TOWERCOUNT | 0..8191 | 1 | 13 | Number of "towers" (experimental signatures left by hadrons in the calorimeter) measured in the HCAL. | :heavy_check_mark: |
| minimum bias HF  |  0..15  | - | 4 | *Present in the L1Ntuple as a sum type but not converted.* Based on the Hadronic Forward Calorimeter fine grain bits. The algorithm foresees a trigger when one of the HF tower on at least one side of HF (OR) or one tower on each side (AND) is above a defined ADC threshold. | :x: |

### MET ($ET_\mathrm{miss}$)
The missing transverse energy object.

| Feature       |     Range     |      Step     |      Bits     |  Explanation  |      in       |
| ------------- | ------------- | ------------- | ------------- | ------------- | ------------- |
| `Et` $E_t$ |  0..2048 GeV  | 0.5 | 12 | The missing transverse energy magnitude. | :heavy_check_mark: |
| `phi` $\varphi$ | 2π  | 2π/144 ~ 0.044 | 8 | The azimuthal angle of the missing transverse energy vector. | :heavy_check_mark: |
| ASYMET | 0..255 | 1 | 8 | The asymmetry in the missing transverse energy vector. A measure of the energy imbalance in the Hadronic Calorimeter.  **Only used for heavy ion runs and thus ignored for the current parquet generation.** | :x: |
| minimum bias HF  |  0..15  | - | 4 | *Present in the L1Ntuple as a sum type but not converted.* Based on the Hadronic Forward Calorimeter fine grain bits. The algorithm foresees a trigger when one of the HF tower on at least one side of HF (OR) or one tower on each side (AND) is above a defined ADC threshold. | :x: |

### MHT ($HT_\mathrm{miss}$)
The missing transverse hadronic energy object.

| Feature       |     Range     |      Step     |      Bits     |  Explanation  |      in       |
| ------------- | ------------- | ------------- | ------------- | ------------- | ------------- |
| `Et` $E_t$ |  0..2048 GeV  | 0.5 | 12 | The hadronic missing transverse energy magnitude. | :heavy_check_mark: |
| `phi` $\varphi$ | 2π  | 2π/144 ~ 0.044 | 8 | The azimuthal angle of the hadronic missing transverse energy vector. | :heavy_check_mark: |
| ASYMHT | 0..255 | 1 | 8 | The asymmetry in the missing hadronic transverse energy vector.  A measure of the energy imbalance in the Hadronic Calorimeter. **Only used for heavy ion runs and thus ignored for the current parquet generation.** | :x: |
| minimum bias HF  |  0..15  | - | 4 | *Present in the L1Ntuple as a sum type but not converted.* Based on the Hadronic Forward Calorimeter fine grain bits. The algorithm foresees a trigger when one of the HF tower on at least one side of HF (OR) or one tower on each side (AND) is above a defined ADC threshold. | :x: |

### FET ($ET^\mathrm{HF}_\mathrm{miss}$)
The missing transverse energy object including data from the forward hadronic calorimeter object.

| Feature       |     Range     |      Step     |      Bits     |  Explanation  |      in       |
| ------------- | ------------- | ------------- | ------------- | ------------- | ------------- |
| `Et` $E_t$ |  0..2048 GeV  | 0.5 | 12 | The missing transverse energy magnitude including the missing transverse energy from the forward hadronic calorimeter. | :heavy_check_mark: |
| `phi` $\varphi$ | 2π  | 2π/144 ~ 0.044 | 8 | The azimuthal angle of the missing transverse energy vector including information from the forward hadronic calorimeter. | :heavy_check_mark: |
| ASYMETHF | 0..255 | 1 | 8 | The asymmetry in the forward missing transverse energy object.  A measure of the energy imbalance in the Hadronic Forward Calorimeter. **Only used for heavy ion runs and thus ignored for the current parquet generation.** | :x: |
| CENT[3:0] | - | - | 4 | The centrality of the missing transverse energy vector, defined by the first 4 bits. It specifies the degree of overlap between colliding ions. **Only used for heavy ion runs and thus ignored for the current parquet generation.**  | :x: |

### FHT ($HT^\mathrm{HF}_\mathrm{miss}$)
The missing hadronic transverse energy object including data from the forward hadronic calorimeter object.

| Feature       |     Range     |      Step     |      Bits     |  Explanation  |      in       |
| ------------- | ------------- | ------------- | ------------- | ------------- | ------------- |
| `Et` $E_t$ |  0..2048 GeV  | 0.5 | 12 | The hadronic missing transverse energy magnitude including the missing transverse energy from the forward hadronic calorimeter. | :heavy_check_mark: |
| `phi` $\varphi$ | 2π  | 2π/144 ~ 0.044 | 8 | The azimuthal angle of the hadronic missing transverse energy vector including information from the forward hadronic calorimeter. | :heavy_check_mark: |
| ASYMHTHF | 0..255 | 1 | 8 | The asymmetry in the forward hadronic missing transverse energy object.  A measure of the energy imbalance in the Hadronic Forward Calorimeter. **Only used for heavy ion runs and thus ignored for the current parquet generation.** | :x: |
| CENT[7:4] | - | - | 4 | The centrality of the missing transverse energy vector, defined by the last 4 bits. It specifies the degree of overlap between colliding ions. **Only used for heavy ion runs and thus ignored for the current parquet generation.**  | :x: |

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

The `seeds` folder contains one boolean column per trigger algorithm: the final decision the global trigger reached for that algorithm on that event.
The columns are named after the algorithms, e.g. `L1_SingleMu22`, and each is a length-1 list per event.

The global trigger makes an accept decision in three stages.
First, for every algorithm and every bunch crossing, the global trigger computes an initial decision: whether the algorithm's condition is met.
Second, a prescale is applied to every algorithm, which keeps every $n$-th accept; a prescale of $0$ disables the algorithm and a prescale of $1$ passes everything.
Third, a per-algorithm trigger mask is applied, giving the final decision.
Both the initial and the final decisions are stored per algorithm in the L1TNtuple, which correspond to after the first decision is applied and after all three steps are applied, respectively.

The workflow here keeps only the unprescaled trigger algorithms in the menu, with $n=1$; additionally, we remove all the anomaly-related seeds `L1_AXO_*` and `L1_CICADA_*`.
This is done to keep the physics-based accepts of all enabled trigger algorithms for the studied runs/simulations, except the anomaly ones (which would be circular to include).
Then, the conversion reads the final decisions, branch `m_algoDecisionFinal` of the uGT tree, matches each algorithm name to its bit through the tree's aliases, and writes one boolean column per kept algorithm.
The `L1bit` column is produced by the converter and is the logical OR of the final decisions given by the kept trigger algorithms.
`L1bit` does not appear in any menu; it exists only in the parquet generated here.
Look at `get_initial_decision` and `get_final_decision` in `src/adl1t_datamaker/components/l1_seeds.py` for the code that precisely handles the seeds and the prescale filtering.
