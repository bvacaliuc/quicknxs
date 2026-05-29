#!/usr/bin/env python
"""v2 PAIRED per-run raw off-spec S (BG-off, scale=1) — the targets for the
flux-floor fix validation. Each data run normalized by its paired DB."""
import numpy as np
from quicknxs.interfaces.configuration import Configuration
from quicknxs.interfaces.data_handling.data_set import NexusData
from quicknxs.interfaces.data_handling.off_specular import OffSpecular

v1 = np.load('/tmp/v1_44159.npz')
tof_edges = np.asarray(v1['tof_edges'], float)
BASE = '/SNS/REF_M/IPTS-34473/nexus/REF_M_%d.nxs.h5'
PAIR = {44159: 44033, 44160: 44034, 44161: 44035}
DBREG = {44033: (227, 12, 136), 44034: (228.5, 16, 136), 44035: (230.5, 24, 134)}
DR = {44159: 172.3, 44160: 172.3, 44161: 173.3}


def load(run, peak_pos, peak_w, lr_pos, lr_w):
    c = Configuration(); c.tof_overwrite = tof_edges
    c.subtract_background = False; c.scaling_factor = 1.0
    c.force_peak_roi = True; c.force_low_res_roi = True; c.force_bck_roi = False
    c.peak_position = peak_pos; c.peak_width = peak_w
    c.low_res_position = lr_pos; c.low_res_width = lr_w
    nd = NexusData(BASE % run, c); xs = nd.load(update_parameters=False)
    for nm, cs in xs.items():
        cs.configuration.peak_position = peak_pos; cs.configuration.peak_width = peak_w
        cs.configuration.low_res_position = lr_pos; cs.configuration.low_res_width = lr_w
        cs.configuration.subtract_background = False; cs.configuration.scaling_factor = 1.0
        cs.process_configuration(); cs.prepare_plot_data()
    return xs['Off_Off']


dbs = {r: load(r, xp, xw, yp, 100) for r, (xp, xw, yp) in DBREG.items()}
for run, xp in DR.items():
    dr = load(run, xp, 17, 137.5, 55)
    osp = OffSpecular(dr); osp(direct_beam=dbs[PAIR[run]])
    S = np.asarray(osp.S)
    print('%d -> DB%d: S.sum=%.4e  S.max=%.4e' % (run, PAIR[run], np.nansum(S), np.nanmax(S)))
