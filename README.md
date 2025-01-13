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
