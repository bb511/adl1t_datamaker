import os
import yaml
import argparse
import shutil
import glob


def temp_file_creator(config):
    root_dir = config["DATA_DIR"]
    output_dir = config["OUTPUT_DIR"]

    root_list = glob.glob(os.path.join(root_dir, "*.root"))

    for root_file in root_list:
        name = root_file.split("/")[-1].split(".root")[0]
        temp_name = name + ".temp"
        temp_file = os.path.join(output_dir, temp_name)

        f = open(temp_file, "a")
        f.write(
            "[Caution] This is a temporary file that the worker uses to pick its jobs. It will be deleted automatically. Please do not delete this file !!!"
        )
        f.close()

    print("Temp file creation completed")
    print("EXITING...")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process some configuration.")
    parser.add_argument(
        "--config-file",
        type=str,
        required=True,
        help="Path to the configuration YAML file containing the master config",
    )
    parser.add_argument("--job_name", type=str, default="Ntupliser")
    parser.add_argument(
        "--submit_flag", default=True
    )  # This is just added for making the CI control easier in practice this should not be turned off
    args = parser.parse_args()

    # Read the YAML configuration file
    with open(args.config_file, "r") as f:
        config = yaml.safe_load(f)

    job_id = args.job_name
    sflag = args.submit_flag
    # This program will create the intermidiate config files that will be consumed by the WORKERS

    INPATHS = config["INPATHS"]
    process_config = config["PROCESS_CONFIG"]
    for name in list(INPATHS.keys()):
        inpath = INPATHS[name]
        outpath = os.path.join(config["OUTPUT_DIR"], name)
        outpath_afs = os.path.join(config["AFS_DIR"], name)

        # ---------------------------------------------------------------
        # This following code block will delete any previous history ..
        if os.path.exists(outpath):
            shutil.rmtree(outpath)  # <----- Take a look here
        os.mkdir(outpath)

        if os.path.exists(outpath_afs):
            shutil.rmtree(outpath_afs)  # <----- Take a look here
        os.mkdir(outpath_afs)
        # ---------------------------------------------------------------
        # Preparing the config files
        config_path = os.path.join(outpath, "config.yml")
        config_ = {
            "DATA_DIR": inpath,
            "OUTPUT_DIR": outpath,
            "PROCESS_CONFIG": process_config,
        }
        with open(config_path, "w") as yaml_file:
            yaml.dump(config_, yaml_file, default_flow_style=False)

        temp_file_creator(config=config_)  # Preparing the temp files
        # ---------------------------------------------------------------
        # Preparing the python job script

        job_script_path = os.path.join(
            outpath_afs, "job.sh"
        )  # Since HTCondor Jobs cannot be submitted from EOS

        job_script_ = f"""#!/bin/bash
source /cvmfs/sft.cern.ch/lcg/views/LCG_105a/x86_64-el9-gcc12-opt/setup.sh

python3 {os.path.join(config["LIB_DIR"],"worker.py")} --config-file {config_path}

wait
"""
        with open(job_script_path, "w") as job_file:
            job_file.write(job_script_)

        submit_script_path = os.path.join(
            outpath_afs, "submit.sub"
        )  # Since HTCondor Jobs cannot be submitted from EOS

        # ---------------------------------------------------------------
        # Preparing the submit script

        submit_script_ = f"""Executable = {job_script_path}
error = {outpath_afs}/$(ClusterId).$(ProcId).err
output = {outpath_afs}/$(ClusterId).$(ProcId).out

requirements = (OpSysAndVer =?= "AlmaLinux9")
+JobGroup = "{job_id}"
Queue {config["JOBS_PER_DIR"]}
"""

        with open(submit_script_path, "w") as sub_file:
            sub_file.write(submit_script_)

        # ---------------------------------------------------------------
        # Submitting the jobs >
        if sflag is True:
            os.system(f"condor_submit {submit_script_path}")
        else:
            pass
