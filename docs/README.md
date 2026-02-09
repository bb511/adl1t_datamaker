# L1TNtuple to parquet

The scripts in this repo do not convert the data in the targeted L1TNtuples in its totality, but only a certain set of objects and corresponding features.
The description of each feature that is available in the global trigger and whether it is included in the converted parquet files is available below.
Whatever features are found in the root files and are not present in the following list do not pertain to what is available to our algorithm and hence are ignored.

The information presented here is a synthesis of the information available in the [scales](https://gitlab.cern.ch/cms-l1-ad/l1tntuple-maker/-/blob/new_h5generation/docs/scales_inputs_2_ugt.pdf?ref_type=heads) and [firmware](https://gitlab.cern.ch/cms-l1-ad/l1tntuple-maker/-/blob/new_h5generation/docs/gt-mp7-firmware-specification.pdf?ref_type=heads) pdf files.
Also, a lot of the descriptions are based on word of mouth and exchanges with the experts of each subsystem.

# Objects

Note, the `I` in the feature names is short for `Integer`, and specifies that the feature is obtained from hardware.
The features that do not have a `root_file_name` are not found in the current vesion of the L1TNtuples generated from the raw data.
Each object also has an associated `[object_name]Bx` feature in the L1TNtuple which specifies the bunch crossing that the object belongs to, since each event contains objects from ± 2 bunch crossings.

The generated parquet files follow the structure outlined in the rest of the readme.
For each converted data set, each object is stored in a separate folder.
Each object folder has a list of parquet files, each parquet file corresponding to the L1Ntuple file it was generated from.
A tick in the `in` column means that the feature is stored in the parquet files upon conversion.

## Muon Objects

> [!NOTE]
> There are 8 muon objects in the parquet files.
> The features of the muons and whether they are included in the parquet files are detailed below.

Additional to the features listed below, the L1TNtuples also contain the following muon variables: `nMuons`, `muonIEta`, `muonIDEta`, `muonIDPhi`, `nMuonShowers`, `muonShowerBx`, `muonShowerOneNominal`, `muonShowerOneTight`, `muonShowerTwoLoose`, `muonShowerTwoLooseDiffSectors`; as well as float versions of the `muonIEt`, `muonIEtUnconstrained`, `muonIEta`, `muonIPhi`, `muonIEtaAtVtx`, `muonIPhiAtVtx`, i.e., without `I` in the name.
These features are not converted to the produced parquet since they do not pertain to the global trigger, and hence not relevant for our algorithm.

| Feature       |     Range     |      Step     |      Bits     |  Explanation  |      in       |
| ------------- | ------------- | ------------- | ------------- | ------------- | ------------- |
| `muonIPhiAtVtx` $\varphi\mathrm{\,\,(extrapolated)}$  |  2 π  | 2π/576 ~ 0.011 | 10 | Muon azimuthal angle extrapolated to the centre of the detector. Layer 2 of the global trigger system is performing the extrapolation in a rudimentary way; if latency allows, a more sophisiticated extrapolation, e.g., using an ML method, is preferable. | :heavy_check_mark: |
| `muonIEt` $p_t$  |  0..256 GeV  | 0.5 | 9 | The muon transverse momentum (a proxy for its transverse energy). | :heavy_check_mark: |
| `muonQual` quality  |  -  | - | 4 | The muon quality is represented by 4 bits. A hit in each of the muon stations flips its corresponding bit to 1. Each of the four muon track finding systems, i.e., BMTF, OMTF, and EMTF assign quality differently. The BMTF records muons with $\eta < 0.8$, EMTF for $0.8 < \eta < 1.2$ and everything higher than that for the OMTF. Each of the systems requires a quality higher than 12, i.e., the first two bits are 1, but how this quality is determined is ultimately peculiar to each system. | :heavy_check_mark: |
| `muonIEtaAtVtx` $\eta \mathrm{\,\,(extrapolated)}$  |  2π  | 0.0870/8=0.010875 | 8+1 | Muon polar angle extrapolated to the centre of the detector. The explanation is the same as for $\phi$. | :heavy_check_mark: |
| `muonIso` iso  |  -  | - | 2 | Muon isolation. The isolation is stored in two bits, corresponding to two types of isolation. However, the meaning of this isolation is not defined yet in the uGMT system: the uGMT has the capability to create an isolation variable but the calorimeter links were never commisioned. | :x: |
| `muonChg` charge sign  |  -  | - | 1 | Muon charge determined from the muon bending trajectory. `-1` is negative charge while `1` is positive charge. | :heavy_check_mark: |
| charge valid  |  -  | - | 1 | This is set to `0` whenever one cannot determine the charge. This can happen when the track is too straight, e.g., in the case of very high momentum muons. | :x: |
| `muonTfMuonIdx` index bits |  -  | - | 7 | There are 7 index bits, which can encode 107 muons. These index bits encode the order of the muons in the GT muon system, i.e., which subsystem they belong to. The first 18 muons come from the EMTF, the next 18 from the OMTF, the next 36 from BMTF, then again the next 18 from OMTF, and finally the last 18 again from the EMTF. | :heavy_check_mark: |
| `muonIPhi` $\varphi$ (out)  |  2π  | 2π/576 ~ 0.011 | 10 | This is just the raw version of the extrapolated azimuthal angle mentioned above. One can use this to obtain more refined versions of the phi at vertex. | :heavy_check_mark: |
| `muonIEta` $\eta$ (out)  |  2π  | 0.0870/8=0.010875 | 8+1 | This is just the raw version of the extrapolated polar angle mentioned above. One can use this to obtain more refined versions of the eta at vertex. | :heavy_check_mark: |
| `muonIEtUnconstrained` unconstrained $p_t$  |  0..256 GeV  | 1 | 8 | The transverse momentum not constrained to the vertex. Lower resolution when compared with the momentum defined above, but useful in the case of offset muons, since it can be more precise than its constrained counterpart. | :heavy_check_mark: |
| hadronic shower trigger |  -  | - | 1 | Whether one observes a hadronic shower in the muon detectors. Very experimental feature and not useful for training the anomaly detector. | :x: |
| `muonDxy` impact parameter  |  -  | - | 2 | Displacement with respect to primary vertex. Not defined yet. | :x: |


## Jet Objects

> [!NOTE]
> There are 12 jet objects in the parquet files.
> The features of the jets and whether they are included in the parquet are detailed below.

Additional to the features listed below, the L1TNtuples contain the following jet variables: `jetSeedEt`, `jetTowerIEta`, `jetTowerIPhi`, `jetPUEt`, `jetPUDonutEt0`, `jetPUDonutEt1`, `jetPUDonutEt2`, `jetPUDonutEt3`; as well as float versions of the `jetIEt`, `jetIEta`, `jetIPhi`, and `jetIRawEt` features, i.e., without `I` in the name.
These features are not converted to the produced parquet since they do not pertain to the global trigger, and hence not relevant for our algorithm.

| Feature       |     Range     |      Step     |      Bits     |  Explanation  |      in       |
| ------------- | ------------- | ------------- | ------------- | ------------- | ------------- |
| `jetIEt` $E_t$  |  0..1024 GeV  | 0.5 | 11 | Jet transverse energy. | :heavy_check_mark: |
| `jetIEta` $\eta$ |  -5..5  | 0.0870/2=0.0435 | 7+1 = 8 | The polar angle of the jet from the centre of the detector. | :heavy_check_mark: |
| `jetIPhi` $\varphi$  |  2π  | 2π/144 ~ 0.044 | 8 | The azimuthal angle of the jet from the centre of the detector. | :heavy_check_mark: |
| DISP |  -  | - | 1 | This bit is used to flag a jet as delayed/displaced based on HCAL timing and depth profiles that are indicative of a “long lived particle” decay. If this bit is set to 1, then the jet is tagged as an LLP. | :x: |
| `jetHwQual` quality flags  |  -  | - | 1 | Based on ECAL/HCAL energy ratio. If this ratio is higher, that means the jet is more likely to not be hadronic, but faked by a high energy lepton or photon. Either tight (2), medium (1), or loose (0). In reality, most jets are 0, with a few having quality 1. | :heavy_check_mark: |
| `jetIRawEt` |  -  | - | - | Not sure what "raw" means in this context. Quantity is present in the L1TNtuple and the converted h5s, but is not defined in the `scales` pdf. | :heavy_check_mark: |

## Egamma Objects

> [!NOTE]
> There are 12 egamma objects in the parquet files.
> The features of the egammas and whether they are included in the parquet files are detailed below.

Additional to the features listed below, the L1TNtuples contain the following egamma variables: `nEGs`, `egTowerIPhi`, `egTowerIEta`, `egRawEt`, `egIsoEt`, `egFootprintEt`, `egNTT`, `egShape`, `egTowerHoE`, `egHwQual`; as well as float versions of the `egIEt`, `egIEta`, `egIPhi`, and `egIRawEt` features, i.e., without `I` in the name.
These features are not converted to the produced parquet since they do not pertain to the global trigger, and hence not relevant for our algorithm.

| Feature       |     Range     |      Step     |      Bits     |  Explanation  |      in       |
| ------------- | ------------- | ------------- | ------------- | ------------- | ------------- |
| `egIEt` $E_t$  |  0..256 GeV  | 0.5 | 9 | Transverse energy of the electron or photon. | :heavy_check_mark: |
| `egIEta` $\eta$ |  -5..5  | 0.0870/2=0.0435 | 7+1 = 8 | The polar angle of the electron or photon from the centre of the detector. | :heavy_check_mark: |
| `egIPhi` $\varphi$  |  2π  | 2π/144 ~ 0.044 | 8 | The azimuthal angle of the electron or photon from the centre of the detector. | :heavy_check_mark: |
| `egIso` iso  |  -  | - | 2 | Little activity around the cluster of energy representing the electron/photon means higher isolation: less likely to be a jet. The lowest bit is defined as `isolated` while the highest bit is named `undefined`. Three degrees of isolation are possible, but only two are used, i.e., the `isolated` bit is set and the other is optional, or vice versa. Thus, it's either these two options, or `no isolation`, when all bits are 0. Whatever quality is larger than 0 is treated as the same degree of isolation. Still unclear how these bits are set, i.e., based on exactly what parameters. | :heavy_check_mark: |

## Tau Objects

> [!NOTE]
> There are 12 tau objects in the parquet files.
> The features of the taus and whether they are included in the parquet files are detailed below.

Additional to the features listed below, the L1TNtuples contain the following tau variables: `nTaus`, `tauTowerIPhi`, `tauTowerIEta`, `tauRawEt`, `tauRawIEt`, `tauIsoEt`, `tauNTT`, `tauHasEM`, `tauIsMerged`, `tauHwQual`; as well as float versions of the `tauIEt`, `tauIEta`, and `tauIPhi` features, i.e., without `I` in the name.
These features are not included in the produced parquet files.

| Feature       |     Range     |      Step     |      Bits     |  Explanation  |      in       |
| ------------- | ------------- | ------------- | ------------- | ------------- | ------------- |
| `tauIEt` $E_t$  |  0..256 GeV  | 0.5 | 9 | Transverse energy of the electron or photon. | :heavy_check_mark: |
| `tauIEta` $\eta$ |  -5..5  | 0.0870/2=0.0435 | 7+1 = 8 | The polar angle of the electron or photon from the centre of the detector. | :heavy_check_mark: |
| `tauIPhi` $\varphi$  |  2π  | 2π/144 ~ 0.044 | 8 | The azimuthal angle of the electron or photon from the centre of the detector. | :heavy_check_mark: |
| `tauIso` iso  |  -  | - | 2 | Little activity around the cluster of energy representing the tau means higher isolation: less likely to be a jet. The lowest bit is defined as `isolated` while the highest bit is named `undefined`. Three degrees of isolation are possible, but only one is used: at least one of the bits needs to be set. Thus, it's either this or `no isolation`, when the bits are all 0. Whatever quality is larger than 0 is treated as the same degree of isolation. Still unclear how these bits are set, i.e., based on what parameters exactly. | :heavy_check_mark: |


## Cicada Objects

Anomaly detection algorithm that uses data from the calorimeter. The `modelIInput` is also available for this object.

> [!NOTE]
> There is one cicada object in the parquet files.
> The features of the cicada object and whether it is included in the parquet files is detailed below.

| Feature       |     Range     |      Step     |      Bits     |  Explanation  |      in       |
| ------------- | ------------- | ------------- | ------------- | ------------- | ------------- |
| `CICADAScore` |  -  | - | 4 | Anomaly score generated using calorimeter tower data. | :heavy_check_mark: |

## Energy Objects

The energy objects do not have `root_file_name` due to how they are stored in the root files.
For more details on how the energy objects are stored, see the `src/adl1t_datamaker/root2parquet.py`, namely the `_store_energies` method and the methods called therein.

> [!NOTE]
> There are 6 energy objects in the parquet files.
> The features of the each energy object are detailed below.

### $ET$
The transverse energy object.

| Feature       |     Range     |      Step     |      Bits     |  Explanation  |      in       |
| ------------- | ------------- | ------------- | ------------- | ------------- | ------------- |
| $E_t$ [ET] |  0..2048 GeV  | 0.5 | 12 | Transverse energy of the whole event. | :heavy_check_mark: |
| $E_t$ [ETTEM] | 0..2048 GeV  | 0.5 | 12 | Transverse energy in the ECAL of the whole event. | :heavy_check_mark: |
| minimum bias HF  |  0..15  | - | 4 | *Not in the L1Ntuple.* Based on the Hadronic Forward Calorimeter fine grain bits. The algorithm foresees a trigger when one of the HF tower on at least one side of HF (OR) or one tower on each side (AND) is above a defined ADC threshold. | :x: |

### $HT$
The `HT` is the magnitude of the vectorial sum of transverse energy jets over ECAL and HCAL.

| Feature       |     Range     |      Step     |      Bits     |  Explanation  |      in       |
| ------------- | ------------- | ------------- | ------------- | ------------- | ------------- |
| $E_t$ |  0..2048 GeV  | 0.5 | 12 | Transverse energy of the whole event. | :heavy_check_mark: |
| TOWERCOUNT | 0..8191 | 1 | 13 | Number of ``towers" (experimental signatures left by hadrons in the calorimeter) measured in the HCAL. | :heavy_check_mark: |
| minimum bias HF  |  0..15  | - | 4 | *Not in the L1Ntuple.* Based on the Hadronic Forward Calorimeter fine grain bits. The algorithm foresees a trigger when one of the HF tower on at least one side of HF (OR) or one tower on each side (AND) is above a defined ADC threshold. | :x: |

### $ET_\mathrm{miss}$
The missing transverse energy object.

| Feature       |     Range     |      Step     |      Bits     |  Explanation  |      in       |
| ------------- | ------------- | ------------- | ------------- | ------------- | ------------- |
| $E_t$ |  0..2048 GeV  | 0.5 | 12 | The missing transverse energy magnitude. | :heavy_check_mark: |
| $\varphi$ | 2π  | 2π/144 ~ 0.044 | 8 | The azimuthal angle of the missing transverse energy vector. | :heavy_check_mark: |
| ASYMET | 0..255 | 1 | 8 | The asymmetry in the missing transverse energy vector. A measure of the energy imbalance in the Hadronic Calorimeter.  **Only used for heavy ion runs and thus ignored for the current parquet generation.** | :x: |
| minimum bias HF  |  0..15  | - | 4 | *Not in the L1Ntuple.* Based on the Hadronic Forward Calorimeter fine grain bits. The algorithm foresees a trigger when one of the HF tower on at least one side of HF (OR) or one tower on each side (AND) is above a defined ADC threshold. | :x: |

### $HT_\mathrm{miss}$
The missing transverse hadronic energy object.

| Feature       |     Range     |      Step     |      Bits     |  Explanation  |      in       |
| ------------- | ------------- | ------------- | ------------- | ------------- | ------------- |
| $E_t$ |  0..2048 GeV  | 0.5 | 12 | The hadronic missing transverse energy magnitude. | :heavy_check_mark: |
| $\varphi$ | 2π  | 2π/144 ~ 0.044 | 8 | The azimuthal angle of the hadronic missing transverse energy vector. | :heavy_check_mark: |
| ASYMHT | 0..255 | 1 | 8 | The asymmetry in the missing hadronic transverse energy vector.  A measure of the energy imbalance in the Hadronic Calorimeter. **Only used for heavy ion runs and thus ignored for the current parquet generation.** | :x: |
| minimum bias HF  |  0..15  | - | 4 | *Not in the L1Ntuple.* Based on the Hadronic Forward Calorimeter fine grain bits. The algorithm foresees a trigger when one of the HF tower on at least one side of HF (OR) or one tower on each side (AND) is above a defined ADC threshold. | :x: |

### $ET^\mathrm{HF}_\mathrm{miss}$
The missing transverse energy object including data from the forward hadronic calorimeter object.

| Feature       |     Range     |      Step     |      Bits     |  Explanation  |      in       |
| ------------- | ------------- | ------------- | ------------- | ------------- | ------------- |
| $E_t$ |  0..2048 GeV  | 0.5 | 12 | The missing transverse energy magnitude including the missing transverse energy from the forward hadronic calorimeter. | :heavy_check_mark: |
| $\varphi$ | 2π  | 2π/144 ~ 0.044 | 8 | The azimuthal angle of the missing transverse energy vector including information from the forward hadronic calorimeter. | :heavy_check_mark: |
| ASYMETHF | 0..255 | 1 | 8 | The asymmetry in the forward missing transverse energy object.  A measure of the energy imbalance in the Hadronic Forward Calorimeter. **Only used for heavy ion runs and thus ignored for the current parquet generation.** | :x: |
| CENT[3:0] | - | - | 4 | The centrality of the missing transverse energy vector, defined by the first 4 bits. It specifies the degree of overlap between colliding ions. **Only used for heavy ion runs and thus ignored for the current parquet generation.**  | :x: |
| minimum bias HF  |  0..15  | - | 4 | *Not in the L1Ntuple.* Based on the Hadronic Forward Calorimeter fine grain bits. The algorithm foresees a trigger when one of the HF tower on at least one side of HF (OR) or one tower on each side (AND) is above a defined ADC threshold. | :x: |

### $HT^\mathrm{HF}_\mathrm{miss}$
The missing transverse energy object including data from the forward hadronic calorimeter object.

| Feature       |     Range     |      Step     |      Bits     |  Explanation  |      in       |
| ------------- | ------------- | ------------- | ------------- | ------------- | ------------- |
| $E_t$ |  0..2048 GeV  | 0.5 | 12 | The hadronic missing transverse energy magnitude including the missing transverse energy from the forward hadronic calorimeter. | :heavy_check_mark: |
| $\varphi$ | 2π  | 2π/144 ~ 0.044 | 8 | The azimuthal angle of the hadronic missing transverse energy vector including information from the forward hadronic calorimeter. | :heavy_check_mark: |
| ASYMETHF | 0..255 | 1 | 8 | The asymmetry in the forward hadronic missing transverse energy object.  A measure of the energy imbalance in the Hadronic Forward Calorimeter. **Only used for heavy ion runs and thus ignored for the current parquet generation.** | :x: |
| CENT[7:4] | - | - | 4 | The centrality of the missing transverse energy vector, defined by the last 4 bits. It specifies the degree of overlap between colliding ions. **Only used for heavy ion runs and thus ignored for the current parquet generation.**  | :x: |
| minimum bias HF  |  0..15  | - | 4 | *Not in the L1Ntuple.* Based on the Hadronic Forward Calorimeter fine grain bits. The algorithm foresees a trigger when one of the HF tower on at least one side of HF (OR) or one tower on each side (AND) is above a defined ADC threshold. | :x: |

## Event Information

All the following features are integers. 

| Feature       |  Explanation  |      in       |
| ------------- | ------------- | ------------- |
| `run` | The CMS run that the event corresponds to. | :heavy_check_mark: |
| `lumi` | The luminosity section, i.e., a range of events that the event is included in. | :heavy_check_mark: |
| `event` | The event number. | :heavy_check_mark: |
| `bx` | The bunch crossing number. Bunches of protons are collided at the LHC. The highest energy event in the bunch crossing is recorded.  | :heavy_check_mark: |
| `orbit` | The orbit includes all bunch crossings that happen in the time it takes for the 2500 bunches introduced into the LHC to complete one orbit. | :heavy_check_mark: |
| `time`  | The time since the start of the run in seconds. | :heavy_check_mark: |
| `nPV_true` | The pileup of the events, i.e., the number of auxiliary proton collisions that happen in the same event. | :heavy_check_mark: |
