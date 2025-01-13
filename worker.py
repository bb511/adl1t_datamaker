import numpy as np
import os
import sys
import glob
import h5py
import convert_to_h5 as ch
import preprocess as pre
import time
import yaml
import argparse
import random

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Process some configuration.')
    parser.add_argument('--config-file', type=str, required=True, help='Path to the configuration YAML file')
    args = parser.parse_args()
    # Read the YAML configuration file
    with open(args.config_file, "r") as f:
        config = yaml.safe_load(f)
    
    config_dat = config["PROCESS_CONFIG"]
    
    root_dir = config["DATA_DIR"]
    output_dir = config["OUTPUT_DIR"]
    #-----> A LOOP will go here to prevent exit
    while(True):
    # Adding a random sleep to prevent race conditions
        stime = abs(5*np.random.randn())
        time.sleep(stime)    

        temp_list = glob.glob(os.path.join(output_dir,"*.temp"))
        
        # Exit condition
        if len(temp_list) == 0:
            sys.exit(0)

        random.shuffle(temp_list)
        file = temp_list[0]

        #----> The temp file removed as soon as it is read to prevent racing
        os.remove(file) # Now this file can no longer be accessed

        print("Processing File",file)
        entity = file.split("/")[-1].split(".temp")[0]
        
        inpath = os.path.join(root_dir, (entity+".root"))
        outpath = os.path.join(output_dir,(entity+".h5"))
        outpath_preprocessed = os.path.join(output_dir,"pro_"+(entity+".h5"))

        #----------------------------------------------------
        # Conversion...
        #----------------------------------------------------

        ch.convert_to_h5(input_file = inpath,
                    output_file = outpath,
                    **config_dat
                    )
        #----------------------------------------------------
        # Visualisation
        #----------------------------------------------------
        f = h5py.File(outpath,"r")
        ## Add more plots/stats here if you want regarding the data :>
        #-----------------------------------------------------
        # Preprocessing of the data
        #----------------------------------------------------
        pre.preprocess(input_file=outpath,
                    output_file=outpath_preprocessed)

        #----------------------------------------------------
        #Deletes the raw data, NOT RECOMMENDED, uncomment to delete it
        #----------------------------------------------------
        # os.remove(outpath)
        #----------------------------------------------------


