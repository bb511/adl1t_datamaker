# Instructions to make L1T emulator ntuple and convert to h5 dataset

## Make L1T ntuple for Campaign Run3Summer22DR (CMSSW_12_4_X)

Modified instructions from [L1 twiki](https://twiki.cern.ch/twiki/bin/view/CMSPublic/SWGuideL1TStage2Instructions#Environment_Setup_with_Integrati).

Selected Summer23-130X samples can be found in the [mc-run3-samples-list.txt](https://gitlab.cern.ch/cms-l1-ad/l1tntuple-maker/-/blob/124X/mc-run3-samples-list.txt)

### Prepare L1T CMSSW area

```
cmsrel CMSSW_13_3_0
cd CMSSW_13_3_0/src
cmsenv
git cms-init
git cms-addpkg L1Trigger/L1TCalorimeter
git cms-addpkg L1Trigger/L1TNtuples
git cms-addpkg L1Trigger/Configuration
git cms-addpkg L1Trigger/L1TGlobal
git cms-addpkg L1Trigger/L1TCommon
git cms-addpkg L1Trigger/L1TZDC
mkdir L1Trigger/L1TZDC/data
cd L1Trigger/L1TZDC/data
wget https://raw.githubusercontent.com/cms-data/L1Trigger-L1TCalorimeter/master/zdcLUT_HI_v0_1.txt
cd -
git clone https://github.com/cms-l1t-offline/L1Trigger-L1TCalorimeter.git L1Trigger/L1TCalorimeter/data
git cms-checkdeps -A -a
scram b -j 8
```

### Download this repo to be used

```
git clone https://gitlab.cern.ch/l1a/l1tntuple-maker.git
cd l1tntuple-maker
```

### Make config file with cmsDriver and submit crab jobs

First set up crab environment `source /cvmfs/cms.cern.ch/crab3/crab.sh`. For more info on CRAB3 usage visit [this page](https://twiki.cern.ch/twiki/bin/view/CMSPublic/WorkBookCRAB3Tutorial).

The `submit_mc_Run3.sh` script makes the config file with cmsDriver and also the config file for crab jobs depending on the value of the `COMMAND` variable at the top of the script:

1. `COMMAND=cmsdriver` : make production config file to be run with cmsRun (the name of the output config file is defined by the `CONFIG` variable)
2. `COMMAND=cmsdriver_reco`: same as 1 but the config file also includes a sequence to save reco variables in the output ntuple
3. `COMMAND=crab_dryrun`: make crab config files for each of the sample in the `DATASETS` list to be reviewed by you
4. `COMMAND=crab_submit`: make crab config file and submit jobs for each of the sample in the `DATASETS` list
5. `COMMAND=privatemc_crab_dryrun`: same as 3 but for privately produced MC samples
6. `COMMAND=privatemc_crab_submit`: same as 4 but for privately produced MC samples
7. `COMMAND=crab_status`: monitor status of all submitted jobs

If you run the command in 2 you must use the samples list `mc-run3-samples-list-forReco.txt` by changing the variable `DATASETS` at the top of the script and also set the variable `USEPARENT=True`.

There are other variables that can be set at the top of the script.
The variable `NEVENTS` is the number of events per job based on the `EventAwareLumiBased` splitting.
The `SITE` corresponds to the `config.Site.storageSite` in the crab config and should also be set.
The `LNFOUTDIRBASE` is the directory where you want to transfer the output files in the accepeted format by CRAB.

1. Example on lxplus: `LNFOUTDIRBASE = /store/group/cmst3/group/l1tr/jngadiub/L1TNtupleRun3/` - `SITE = T2_CH_CERN`
2. Example on LPC: `LNFOUTDIRBASE = /store/group/lpctrig/jngadiub/L1TNtupleRun3/` - `SITE = T3_US_FNALLPC`

Additional variables can be configured when running over privately produced samples. The variable `NEVENTS` now indicates the number of files per job. The `TAG` used to name crab output files and folders and should be of the format
`<process_name>_mcRun3_<campaing_name>_<release>` without `_` in the `<process_name>` (example: `haa4b_mcRun3_Run3Summer21DRPremix-120X`). The last argument `FILELIST` should be a txt file with the list of files from the private MC production where the files should
either start with `/store/` or use the full path with `file:` in front.

Once you ahave chosen which command to run and you have set the configuration at the top of the script you can run it as:

```
./submit_mc_Run3.sh
```

Before submitting crab jobs you can also run a local test. Ex: `cmsRun mc_run3.py`

## Convert L1T ntuple to h5 dataset

### Converting Individual Files

The converion of `.root` files are straight forward. It can be converted using the following recipe:

```
python convert_to_h5.py --input-file L1Ntuple.root --output-file L1Ntuple.h5 --prescale-file L1Menu_Collisions2023_v1_2_0.csv
```

Preprocess the output file to obtain a new h5 file where the separate MET, electrons (4), muons (4), and jets (10) info arrays are concatenated in that order:

```
python preprocess.py --input-file L1Ntuple.h5 --output-file L1Ntuple_preprocessed.h5
```
### Distributed convertion for Large Scale Datasets
For huge datasets we follow the following pipeline to distribute the workload across multiple HTCondor Workers speeding up the overal process.
### STEP 1: Configuration File Generation Guide

This documentation provides detailed instructions on generating configuration files required for processing data using the `config_helper.py` script. The script is designed to facilitate the setup of configuration parameters for Monte-Carlo (MC) generated data or Zero-Bias (ZB) data, storing the configuration in both AFS and EOS directories.

#### Overview

The `config_helper.py` script automates the creation of YAML configuration files. These files define the necessary paths and parameters for processing data. The script uses command-line arguments to customize the configuration based on user input.

#### Prerequisites

Before using the `config_helper.py` script, ensure that the following dependencies are installed in your Python environment:

- `numpy`
- `os`
- `sys`
- `glob`
- `json`
- `yaml`
- `argparse`
- `shutil`

#### Usage

To generate a configuration file, execute the `config_helper.py` script with the appropriate command-line arguments. The script requires several mandatory arguments and allows for optional arguments with default values.

##### Command-Line Arguments

- `--type` (Required): Specifies the type of data. Acceptable values are `MC` for Monte-Carlo data or `ZB` for Zero-Bias data.
- `--nthreads` (Optional): Number of threads to use for processing. Default is `1`.
- `--datapath` (Required): Path to the data directory. For MC, this should be the parent folder containing all processes; for ZB, it should be the folder with `.root` files.
- `--outdir` (Required): Directory where the generated H5 files will be stored.
- `--afsdir` (Required): Temporary AFS directory used for job scheduling.
- `--event_tree_name` (Optional): Name of the event tree. Default is `l1EventTree/L1EventTree`.
- `--gen_tree_name` (Optional): Name of the generator tree. Default is `l1GeneratorTree/L1GenTree`.
- `--hw` (Optional): Hardware flag. Default is `True`.
- `--mc` (Optional): Monte Carlo flag. Default is `True`.
- `--prescale_file` (Optional): Path to the prescale file. Default is `/afs/cern.ch/user/d/diptarko/CODE/NTUPLE/l1tntuple-maker/L1Menu_Collisions2023_v1_2_0.csv`.
- `--tree_name` (Optional): Name of the tree. Default is `l1UpgradeEmuTree/L1UpgradeTree`.
- `--uGT_tree_name` (Optional): Name of the uGT tree. Default is `l1uGTEmuTree/L1uGTTree`.

> **⚠️ Warning: `--prescale_file` is needed to be specified in most cases although this is kept optional; otherwise, the code might fail.**


##### Example Usage for MC Data

To generate a configuration file for Monte-Carlo data with 4 threads, use the following command:

```bash
python config_helper.py --type MC --nthreads 4 --datapath /path/to/data --outdir /path/to/output --afsdir /path/to/afs
```

##### Example Usage for Zero-Bias Data

To generate a configuration file for Zero-Bias (ZB) data with 2 threads, use the following command:

```bash
python config_helper.py --type ZB --nthreads 2 --datapath /path/to/data --outdir /path/to/output --afsdir /path/to/afs
```

### STEP 2: Main Processing Script

After generating the configuration files, the next step is to run the main processing script. This script utilizes the previously generated YAML configuration file to set up and execute data processing tasks. The script is designed to prepare intermediate configuration files, create job scripts, and submit these jobs to HTCondor for parallel processing.

#### Overview

The main processing script reads the YAML configuration file and performs the following steps:

1. **Read Configuration**: The script reads the configuration settings from the provided YAML file.
2. **Setup Output Directories**: It creates necessary output directories, removing any previous content to ensure a clean environment.
3. **Generate Intermediate Configuration Files**: For each dataset specified in the configuration, the script generates intermediate YAML configuration files.
4. **Create Job and Submit Scripts**: The script prepares job scripts and HTCondor submit files for each dataset.
5. **Submit Jobs to HTCondor**: Finally, the script submits the jobs to HTCondor for execution.

#### Usage

To run the main processing script (`bundler.py`), use the following command:

```bash
python bundler.py --config-file /path/to/generated/config.yaml
```
#### Command-Line Arguments

The script accepts the following command-line argument:

##### `--config-file`

- **Type**: `str`
- **Required**: Yes
- **Description**: This argument specifies the path to the YAML configuration file that was created using the `config_helper.py` script. The file should include all necessary configurations for the data processing workflow.
- **Example**:
  - For Monte-Carlo data: `--config-file /path/to/output/CONFIGS/MC_config.yaml`
  - For Zero-Bias data: `--config-file /path/to/output/CONFIGS/ZB_config.yaml`




