import os
import json
import h5py
import argparse
import numpy as np
from sklearn.preprocessing import scale
from sklearn.preprocessing import StandardScaler

def read_data(input_file):
    f = h5py.File(input_file, 'r')

    #MET
    mydata = np.array(f.get('l1Sum_cyl'))
    met_cyl = mydata
    met_cyl = np.reshape(met_cyl, (met_cyl.shape[0],1,3))
    del mydata

    #Electron
    mydata = np.array(f.get('l1Ele_cyl'))
    e_cyl = mydata
    del mydata

    #Muon
    mydata = np.array(f.get('l1Muon_cyl'))
    m_cyl = mydata
    del mydata
    #Jet
    mydata = np.array(f.get('l1Jet_cyl'))
    j_cyl = mydata
    del mydata

    #Electron Isolation
    mydata = np.array(f.get('l1Ele_Iso'))
    e_iso = mydata
    del mydata

    #Muon Isolation
    mydata = np.array(f.get('l1Muon_Iso'))
    m_iso = mydata
    del mydata

    #Muon Quality
    mydata = np.array(f.get('l1Muon_Qual'))
    m_qual = mydata
    del mydata   

    #Muon Dxy
    mydata = np.array(f.get('l1Muon_Dxy'))
    m_dxy = mydata
    del mydata

    #Muon upT
    mydata = np.array(f.get('l1Muon_Upt'))
    m_upt = mydata
    del mydata

    #ET
    mydata = np.array(f.get('l1ET'))
    ET = mydata
    del mydata        

    #HT
    mydata = np.array(f.get('l1HT'))
    HT = mydata
    del mydata

    #genHT
    mydata = np.array(f.get('genHT'))
    genHT = mydata
    del mydata    

    #L1bit
    mydata = np.array(f.get('L1bit'))
    l1bit = mydata
    del mydata

    #L1 seeds
    keys = f.keys()
    seednames = []
    seedinfo = {}
    for key in keys:
        if "L1_" in key:
            seednames.append(key)
    for seed in seednames:
        mydata = np.array(f.get(seed))
        seedinfo[seed] = mydata
        del mydata

    #Event info
    mydata = np.array(f.get('EventInfo'))
    evt_info = mydata
    del mydata
    
    print('The MET data shape is: ', met_cyl.shape)
    print('The ET data shape is: ', ET.shape)
    print('The HT data shape is: ', HT.shape)
    print('The gen HT data shape is: ', genHT.shape)
    print('The e/gamma data shape is: ', e_cyl.shape, e_iso.shape)
    print('The muon data shape is: ', m_cyl.shape, m_iso.shape, m_dxy.shape, m_qual.shape)
    print('The jet data shape is: ', j_cyl.shape)
    print('The L1bit data shape is: ', l1bit.shape)
    print("The event info data shape is: ",evt_info.shape)

    full_data_cyl = np.concatenate([met_cyl, e_cyl, m_cyl, j_cyl], axis=1)
    #TODO: how best to include e_iso, m_iso, m_dxy?
    full_data_iso = np.concatenate([np.zeros([met_cyl.shape[0],met_cyl.shape[1]],dtype=np.float16), e_iso, m_iso, np.zeros([j_cyl.shape[0],j_cyl.shape[1]],dtype=np.float16)], axis=1)
    full_data_dxy = np.concatenate([np.zeros([met_cyl.shape[0],met_cyl.shape[1]],dtype=np.float16), np.zeros([e_cyl.shape[0],e_cyl.shape[1]],dtype=np.float16), m_dxy, np.zeros([j_cyl.shape[0],j_cyl.shape[1]],dtype=np.float16)], axis=1)
    full_data_upt = np.concatenate([np.zeros([met_cyl.shape[0],met_cyl.shape[1]],dtype=np.float16), np.zeros([e_cyl.shape[0],e_cyl.shape[1]],dtype=np.float16), m_upt, np.zeros([j_cyl.shape[0],j_cyl.shape[1]],dtype=np.float16)], axis=1)
    full_data_qual = np.concatenate([np.zeros([met_cyl.shape[0],met_cyl.shape[1]],dtype=np.float16), np.zeros([e_cyl.shape[0],e_cyl.shape[1]],dtype=np.float16), m_qual, np.zeros([j_cyl.shape[0],j_cyl.shape[1]],dtype=np.float16)], axis=1)
    print('Done concatenating')
    print('The full cyl data shape is: ',full_data_cyl.shape)
    print('The full iso data shape is: ',full_data_iso.shape)
    print('The full dxy data shape is: ',full_data_dxy.shape)
    print('The full qual data shape is: ',full_data_qual.shape)
    return full_data_cyl, full_data_iso, full_data_dxy, full_data_upt, full_data_qual, ET, HT, genHT, l1bit, seedinfo, evt_info

def preprocess(input_file, output_file):

    full_data_cyl, full_data_iso, full_data_dxy, full_data_upt, full_data_qual, ET, HT, genHT, l1bit, seedinfo, evt_info = read_data(input_file)

    #Save this full_data_cyl
    h5f = h5py.File(output_file, 'w')
    h5f.create_dataset('full_data_cyl', data=full_data_cyl, compression='gzip')
    h5f.create_dataset('full_data_iso', data=full_data_iso, compression='gzip')
    h5f.create_dataset('full_data_dxy', data=full_data_dxy, compression='gzip')
    h5f.create_dataset('full_data_upt', data=full_data_upt, compression='gzip')
    h5f.create_dataset('full_data_qual', data=full_data_qual, compression='gzip')
    h5f.create_dataset('ET', data=ET, compression='gzip')
    h5f.create_dataset('HT', data=HT, compression='gzip')
    h5f.create_dataset('genHT', data=genHT, compression='gzip')
    h5f.create_dataset('L1bit', data=l1bit, compression='gzip')
    h5f.create_dataset('event_info', data=evt_info, compression='gzip')
    for seed, seed_data in seedinfo.items():
        h5f.create_dataset(seed, data=seed_data, compression='gzip')
    h5f.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-file', type=str, help='Path to the input file', required=True)
    parser.add_argument('--output-file', type=str, help='Path to the input file', required=True)
    args = parser.parse_args()
    preprocess(**vars(args))
