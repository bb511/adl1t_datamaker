import os
import yaml
import argparse
import shutil

def help_config(nthreads, datapath, outdir, afsdir, libdir, event_tree_name, gen_tree_name, hw, mc, prescale_file, tree_name, uGT_tree_name):

    inpath = None

    if mc:
        BSM_FOLDER = datapath
        folder_list = get_folders(BSM_FOLDER)
        signal_names = os.listdir(os.path.join(BSM_FOLDER))
        inpath_dict = {}
        
        for i, signal in enumerate(signal_names):
            inpath_dict[signal] = folder_list[i]

        inpath = inpath_dict.copy()

    else:
        ZB_FOLDER = datapath
        inpath = {"ZB": ZB_FOLDER}

    config = {
        'INPATHS': inpath,
        'OUTPUT_DIR': outdir,
        'AFS_DIR': afsdir,
        'LIB_DIR': libdir,
        'JOBS_PER_DIR': nthreads,
        'PROCESS_CONFIG': {
            'event_tree_name': event_tree_name,
            'gen_tree_name': gen_tree_name,
            'hw': hw,
            'mc': mc,
            'prescale_file': prescale_file,
            'tree_name': tree_name,
            'uGT_tree_name': uGT_tree_name,
        }
    }
    return config

# Helper functions
#########################################################################################
def get_folders(root_dir):
    last_nodes = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        if not dirnames and filenames:
            last_nodes.append(dirpath)
    return last_nodes
#########################################################################################

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument('--type',
                        choices=["MC", "ZB"],
                        help="Mandatory flag. MC for Monte-Carlo generated data. ZB for Zero-Bias data",
                        required=True)
    parser.add_argument('--nthreads',
                        help="The Number of threads to use to process the data. For MC the actual number of threads is nthreads*nprocs",
                        default=2)
    parser.add_argument("--datapath",
                        help="Path to the data. For MC give the parent folder containing all the processes. For ZB give the folder containing the .root files",
                        required=True)
    parser.add_argument("--outdir",
                        help="Path where the H5 files will be stored.",
                        required=True)
    parser.add_argument("--afsdir",
                        help="Temporary AFS directory required for JOB Scheduling. Give the AFS directory for user NOT PROJECT!",
                        required=True)
    parser.add_argument("--prescale_file",
                        help="Path to the prescale file.",
                        required=True)
    
    parser.add_argument("--event_tree_name",
                        help="Name of the event tree.",
                        default="l1EventTree/L1EventTree")
    parser.add_argument("--gen_tree_name",
                        help="Name of the generator tree.",
                        default="l1GeneratorTree/L1GenTree")
    parser.add_argument("--hw",
                        help="Hardware flag.",
                        default=True)
    parser.add_argument("--mc",
                        help="Monte Carlo flag.",
                        default=True)
    parser.add_argument("--tree_name",
                        help="Name of the tree.",
                        default="l1UpgradeEmuTree/L1UpgradeTree")
    parser.add_argument("--uGT_tree_name",
                        help="Name of the uGT tree.",
                        default="l1uGTEmuTree/L1uGTTree")

    args = parser.parse_args()

    # Mandatory arguments
    data_type = args.type                       # Accessing the 'type' argument
    nthreads = args.nthreads                    # Accessing the 'nthreads' argument
    datapath = args.datapath                    # Accessing the 'datapath' argument
    outdir = args.outdir                        # Accessing the 'outdir' argument
    afsdir = args.afsdir                        # Accessing the 'afsdir' argument
    prescale_file = args.prescale_file          # Accessing the 'prescale_file' argument

    datapath = os.path.abspath(datapath)
    outdir = os.path.abspath(outdir)
    afsdir = os.path.abspath(afsdir)
    prescale_file = os.path.abspath(prescale_file)

    # Optional arguments with default values
    event_tree_name = args.event_tree_name      # Accessing the 'event_tree_name' argument
    gen_tree_name = args.gen_tree_name          # Accessing the 'gen_tree_name' argument
    hw = args.hw                                # Accessing the 'hw' argument
    mc = args.mc                                # Accessing the 'mc' argument
    tree_name = args.tree_name                  # Accessing the 'tree_name' argument
    uGT_tree_name = args.uGT_tree_name          # Accessing the 'uGT_tree_name' argument

    libdir = os.path.dirname(os.path.realpath(__file__))

    if data_type == "MC":
        mc = True
        config = help_config(nthreads,
                             datapath,
                             outdir,
                             afsdir,
                             libdir,
                             event_tree_name,
                             gen_tree_name, 
                             hw,
                             mc,
                             prescale_file,
                             tree_name,
                             uGT_tree_name)
        
    else:
        mc = False
        config = help_config(nthreads,
                            datapath,
                            outdir,
                            afsdir,
                            libdir,
                            event_tree_name,
                            gen_tree_name,
                            hw,
                            mc,
                            prescale_file,
                            tree_name,
                            uGT_tree_name)
    
    # This config will be stored in the given AFS directory under the folder CONFIGS and a copy will also be stored in the EOS storage
    print(yaml.dump(config, allow_unicode=True, default_flow_style=False))

    afs_config_dir = os.path.join(afsdir, "CONFIGS")
    eos_config_dir = os.path.join(outdir, "CONFIGS")  # Assuming EOS storage path is the same as output directory
    
    # Ensure the directories exist
    os.makedirs(afs_config_dir, exist_ok=True)
    os.makedirs(eos_config_dir, exist_ok=True)
    
    # Define the config file names
    config_filename = f"{data_type}_config.yaml"
    
    # Save the config to AFS directory
    afs_config_path = os.path.join(afs_config_dir, config_filename)
    with open(afs_config_path, 'w') as afs_file:
        yaml.dump(config, afs_file, allow_unicode=True, default_flow_style=False)
    
    # Save a copy of the config to EOS storage
    eos_config_path = os.path.join(eos_config_dir, config_filename)
    shutil.copy(afs_config_path, eos_config_path)
    
    # Print the paths where the config has been saved
    print(f"Config saved to AFS: {afs_config_path}")
    print(f"Config saved to EOS: {eos_config_path}")

