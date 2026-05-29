#!/usr/bin/env python
"""v2 raw off-spec S for 44159 Off_Off normalized by DB 44033, BG OFF."""
import numpy as np
from quicknxs.interfaces.configuration import Configuration
from quicknxs.interfaces.data_handling.data_set import NexusData
from quicknxs.interfaces.data_handling.off_specular import OffSpecular

v1 = np.load('/tmp/v1_44159.npz')
tof_edges = np.asarray(v1['tof_edges'], float)
DR = '/SNS/REF_M/IPTS-34473/nexus/REF_M_44159.nxs.h5'
DB = '/SNS/REF_M/IPTS-34473/nexus/REF_M_44033.nxs.h5'


def load(path, peak_pos, peak_w, lr_pos, lr_w):
    c = Configuration()
    c.tof_overwrite = tof_edges
    c.subtract_background = False
    c.scaling_factor = 1.0
    c.force_peak_roi = True
    c.force_low_res_roi = True
    c.force_bck_roi = False
    c.peak_position = peak_pos
    c.peak_width = peak_w
    c.low_res_position = lr_pos
    c.low_res_width = lr_w
    nd = NexusData(path, c)
    xs = nd.load(update_parameters=False)
    for nm, cs in xs.items():
        cs.peak_position = peak_pos
        cs.configuration.peak_position = peak_pos
        cs.configuration.peak_width = peak_w
        cs.configuration.low_res_position = lr_pos
        cs.configuration.low_res_width = lr_w
        cs.configuration.subtract_background = False
        cs.configuration.scaling_factor = 1.0
        cs.process_configuration()
        cs.prepare_plot_data()
    return xs


dr = load(DR, 172.3, 17, 137.5, 55)
db = load(DB, 227, 12, 136, 100)
dr_off = dr['Off_Off']
db_off = db['Off_Off']
print('DR Off_Off pc=%.4f  DB Off_Off pc=%.4f  (µAh)' % (dr_off.proton_charge, db_off.proton_charge))
print('DR low_res_roi', dr_off.configuration.low_res_roi, ' DB peak_roi', db_off.configuration.peak_roi,
      ' DB low_res_roi', db_off.configuration.low_res_roi)

osp = OffSpecular(dr_off)
osp(direct_beam=db_off)
S = np.asarray(osp.S)
print('v2 S shape=%s  sum=%.6e  max=%.4e  nonzero=%d' %
      (S.shape, np.nansum(S), np.nanmax(S), int((S != 0).sum())))
np.savez('/tmp/v2_S.npz', S=S, dk=np.asarray(osp.ki_z - osp.kf_z), Qz=np.asarray(osp.Qz),
         pc_dr=dr_off.proton_charge, pc_db=db_off.proton_charge)
