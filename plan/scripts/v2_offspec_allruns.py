#!/usr/bin/env python
"""v2 raw off-spec total(S) per run (44159/60/61), all normalized by DB 44033,
BG OFF, scale=1.0 — to check whether each run matches v1 (isolating per-run
normalization from the multi-run merge)."""
import numpy as np
from quicknxs.interfaces.configuration import Configuration
from quicknxs.interfaces.data_handling.data_set import NexusData
from quicknxs.interfaces.data_handling.off_specular import OffSpecular

v1 = np.load('/tmp/v1_44159.npz')
tof_edges = np.asarray(v1['tof_edges'], float)
BASE = '/SNS/REF_M/IPTS-34473/nexus/REF_M_%d.nxs.h5'
# run -> (x_pos, x_width)
RUNS = {44159: (172.3, 17), 44160: (172.3, 17), 44161: (173.3, 17)}


def load(run, peak_pos, peak_w, lr_pos, lr_w):
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
    nd = NexusData(BASE % run, c)
    xs = nd.load(update_parameters=False)
    for nm, cs in xs.items():
        cs.configuration.peak_position = peak_pos
        cs.configuration.peak_width = peak_w
        cs.configuration.low_res_position = lr_pos
        cs.configuration.low_res_width = lr_w
        cs.configuration.subtract_background = False
        cs.configuration.scaling_factor = 1.0
        cs.process_configuration()
        cs.prepare_plot_data()
    return xs


db = load(44033, 227, 12, 136, 100)['Off_Off']
print('DB 44033 Off_Off pc=%.4f' % db.proton_charge)
for run, (xp, xw) in RUNS.items():
    dr = load(run, xp, xw, 137.5, 55)['Off_Off']
    osp = OffSpecular(dr)
    osp(direct_beam=db)
    S = np.asarray(osp.S)
    print('%d Off_Off: pc=%.4f  S.sum=%.6e  S.max=%.4e' % (run, dr.proton_charge, np.nansum(S), np.nanmax(S)))
