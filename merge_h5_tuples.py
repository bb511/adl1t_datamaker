#!/usr/bin/python


from __future__ import print_function, division
import os, sys
import h5py
import numpy as np
import argparse

def merge_h5_tuples(output_file, input_files, bsm):

        #keys = ['l1Ele_cyl', 'l1Jet_cyl', 'l1Muon_cyl', 'l1Sum_cyl',
        #        'l1Ele_Iso', 'l1Muon_Iso', 'l1Muon_Dxy', 'L1bit']
        keys = h5py.File(input_files[0],'r').keys()
        data = {feature: np.array for feature in keys}

        input_files = [os.path.join(input_files[0], f) for f in os.listdir(input_files[0]) if os.path.isfile(os.path.join(input_files[0], f))] \
            if len(input_files)==1 else input_files
        for k in keys:
            data[k] = np.concatenate([ h5py.File(input_file, 'r')[k] for input_file in input_files], axis=0)            
	
        #write in data
        h5f = h5py.File(output_file, 'w')
        for feature in keys:
            h5f.create_dataset(feature, data=data[feature])
        h5f.close()

def merge_h5_tuples_bsm(output_file, input_files, bsm):

        h5f = h5py.File(output_file, 'w')

        bsm_types = [
            'HHHTo6B',
            'HHHto4B2Tau',
            'VBFHToTauTau',
            'ttHto2B',
            'ttHto2C',
            'GluGluHToGG_M-125',
            'GluGluHToGG_M-90',
            'GluGluHToBB_M-125',
            'GluGluHToTauTau',
            'GluGlutoHHto2B2WtoLNu2Q',
            'SMS-Higgsino',
            'SUSYGluGluToBBHToBB_NarrowWidth_M-1200',
            'SUSYGluGluToBBHToBB_NarrowWidth_M-120',
            'SUSYGluGluToBBHToBB_NarrowWidth_M-350',
            'SUSYGluGluToBBHToBB_NarrowWidth_M-600',
            'VBFHToCC',
            'VBFHToInvisible',
            'VBFHto2B',
            'WToTauTo3Mu',
            'ggXToJpsiJpsiTo2Mu2E_m7',
            'ggXToYYTo2Mu2E_m18',
            'ggXToYYTo2Mu2E_m26',
            'HTo2LongLivedTo4mu_MH-125_MFF-12_CTau-900mm',
            'HTo2LongLivedTo4mu_MH-125_MFF-25_CTau-1500mm',
            'HTo2LongLivedTo4mu_MH-125_MFF-50_CTau-3000mm',
            'HTo2LongLivedTo4b_MH-1000_MFF-450_CTau-100000mm',
            'HTo2LongLivedTo4b_MH-1000_MFF-450_CTau-10000mm',
            'HTo2LongLivedTo4b_MH-125_MFF-12_CTau-900mm',
            'HTo2LongLivedTo4b_MH-125_MFF-25_CTau-1500mm',
            'HTo2LongLivedTo4b_MH-125_MFF-50_CTau-3000mm',
            'haa4b-ma15-noPU'
            ]
              
        for bsm_type in bsm_types:
            print(bsm_type)
            input_file = [f for f in input_files if bsm_type in f][0]
            h5f.create_dataset(bsm_type, data=h5py.File(input_file, 'r').get('full_data_cyl'), compression='gzip')
            h5f.create_dataset(bsm_type + "_iso", data=h5py.File(input_file, 'r').get('full_data_iso'), compression='gzip')
            h5f.create_dataset(bsm_type + "_qual", data=h5py.File(input_file, 'r').get('full_data_qual'), compression='gzip')            
            h5f.create_dataset(bsm_type + "_dxy", data=h5py.File(input_file, 'r').get('full_data_dxy'), compression='gzip')
            h5f.create_dataset(bsm_type + "_upt", data=h5py.File(input_file, 'r').get('full_data_upt'), compression='gzip')
            h5f.create_dataset(bsm_type + "_ET", data=h5py.File(input_file, 'r').get('ET'), compression='gzip')
            h5f.create_dataset(bsm_type + "_HT", data=h5py.File(input_file, 'r').get('HT'), compression='gzip')
            h5f.create_dataset(bsm_type + "_genHT", data=h5py.File(input_file, 'r').get('genHT'), compression='gzip')
            h5f.create_dataset(bsm_type + "_l1bit", data=h5py.File(input_file, 'r').get('L1bit'), compression='gzip')
            h5f.create_dataset(bsm_type + "_nPV", data=h5py.File(input_file, 'r').get('event_info')[:,6], compression='gzip')
            keys = h5py.File(input_file,'r').keys()
            for key in keys:
                if "L1_" in key:
                    h5f.create_dataset(bsm_type + "_" + key, data=h5py.File(input_file, 'r').get(key), compression='gzip')
        h5f.close()
	
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-file', type=str, help='output file', required=True)
    parser.add_argument('--input-files', type=str, nargs='+', help='input files', required=True)
    parser.add_argument('--bsm', action='store_true')
    args = parser.parse_args()
    if not args.bsm:
        merge_h5_tuples(**vars(args))
    else:
        merge_h5_tuples_bsm(**vars(args))
