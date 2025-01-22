#!/bin/bash

#### variables to be configured ####
COMMAND=cmsdriver
LNFOUTDIRBASE=/store/group/lpctrig/jngadiub/L1TNtupleRun3-133XWinter24/
NEVENTS=5 #number of events per job (central MC) -- number of files per job (private MC)
SITE=T3_US_FNALLPC
DATASETS=mc-run3-samples-list.txt
USEPARENT=""
#USEPARENT="--use-parent" # only for crab with cmsdriver_reco config 
CONFIG=mc_run3.py
CRABDIR=crab_projects_mc_run3
#for private MC
TAG=haa-4b-ma15-POWHEG_mcRun3_Run3Winter24Digi-133XnoPU_v8-v2
FILELIST=privatemc-filelist/haa4b-ma15-powheg-133X-noPU.txt
###################################

if [ $COMMAND == "cmsdriver" ]; then

 cmsDriver.py l1Ntuple -s RAW2DIGI --python_filename=$CONFIG -n 10 --nThreads 4 --nConcurrentLumis 1 --no_output --no_exec \
      --era=Run3 --mc --conditions=133X_mcRun3_2024_realistic_v8 \
      --customise=L1Trigger/Configuration/customiseReEmul.L1TReEmulMCFromRAWSimHcalTP \
      --customise=L1Trigger/L1TNtuples/customiseL1Ntuple.L1NtupleRAWEMUGEN_MC \
      --customise=L1Trigger/Configuration/customiseSettings.L1TSettingsToCaloParams_2023_v0_4 \
      --filein=/store/mc/Run3Winter24Digi/SingleNeutrino_Pt-2To20-gun/GEN-SIM-RAW/133X_mcRun3_2024_realistic_v8-v2/2540000/038bda40-23b3-4038-a546-6397626ae3e2.root 
fi

#outdated (120X branch)
#if [ $COMMAND == "cmsdriver_reco" ]; then

# cmsDriver.py l1Ntuple -s RAW2DIGI --python_filename=$CONFIG -n 20 --nThreads 4 --nConcurrentLumis 1 --no_output --no_exec \
#      --era=Run3 --mc --conditions=120X_mcRun3_2021_realistic_v9 \
#      --customise=L1Trigger/Configuration/customiseReEmul.L1TReEmulMCFromRAW \
#      --customise=L1Trigger/L1TNtuples/customiseL1Ntuple.L1NtupleAODRAWEMUGEN_MC \
#      --customise=L1Trigger/Configuration/customiseSettings.L1TSettingsToCaloParams_2021_v0_2 \
#      --filein=/store/mc/Run3Summer21DRPremix/VBFHToInvisible_M125_TuneCP5_14TeV-powheg-pythia8/GEN-SIM-RECO/120X_mcRun3_2021_realistic_v6-v2/2550000/d5316bb9-43f5-4cb9-a5a1-619ba8d648f5.root \
#      --secondfilein=/store/mc/Run3Summer21DRPremix/VBFHToInvisible_M125_TuneCP5_14TeV-powheg-pythia8/GEN-SIM-DIGI-RAW/120X_mcRun3_2021_realistic_v6-v2/2550000/01420064-229e-4fd5-8e45-7def355ff317.root
#fi
      
if [ $COMMAND == "crab_dryrun" ]; then

      python3 crab.py -p $CONFIG -t mcRun3 -i $DATASETS --num-cores 4 --max-memory 6000 --send-python \
                      -s EventAwareLumiBased -n $NEVENTS --work-area $CRABDIR --site $SITE --no-publication \
                      -o $LNFOUTDIRBASE $USEPARENT \
                      --dryrun
 
fi

if [ $COMMAND == "crab_submit" ]; then

 python3 crab.py -p $CONFIG -t mcRun3 -i $DATASETS --num-cores 4 --max-memory 6000 --send-python \
                -s EventAwareLumiBased -n $NEVENTS --work-area $CRABDIR --site $SITE --no-publication \
                -o $LNFOUTDIRBASE $USEPARENT
 
fi

if [ $COMMAND == "crab_status" ]; then

 python3 crab.py -p $CONFIG -t mcRun3 -i $DATASETS --work-area $CRABDIR --status --no-resubmit
 
fi

if [ $COMMAND == "crab_resubmit" ]; then

 python3 crab.py -p $CONFIG -t mcRun3 -i $DATASETS --work-area $CRABDIR --resubmit
 
fi

if [ $COMMAND == "privatemc_crab_dryrun" ]; then

 python3 crab.py -p $CONFIG -t $TAG -i $FILELIST --set-input-files --num-cores 4 --max-memory 6000 --send-python \
                -s FileBased -n $NEVENTS --work-area $CRABDIR --site $SITE --no-publication \
                -o $LNFOUTDIRBASE \
                --dryrun
 
fi

if [ $COMMAND == "privatemc_crab_submit" ]; then

 python3 crab.py -p mc_run3.py -t $TAG -i $FILELIST --set-input-files --inputfile $FILELIST --num-cores 4 --max-memory 6000 --send-python \
                -s FileBased -n $NEVENTS --work-area $CRABDIR --site $SITE --no-publication \
                -o $LNFOUTDIRBASE
 
fi
