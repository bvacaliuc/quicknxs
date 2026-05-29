#!/usr/bin/env python
"""v1 raw off-spec S for 44159 Off_Off normalized by DB 44033, BG OFF
(reconstructed from oS.I / norm.I, no band-crop), to compare with v2."""
import numpy as np
from quicknxs.qreduce import NXSData, Reflectivity, OffSpecular

DR = '/SNS/REF_M/IPTS-34473/nexus/REF_M_44159.nxs.h5'
DB = '/SNS/REF_M/IPTS-34473/nexus/REF_M_44033.nxs.h5'

nd_dr = NXSData(DR, use_caching=False, bins=400)
nd_db = NXSData(DB, use_caching=False, bins=400)
print('DR channels', list(nd_dr.keys()), ' DB channels', list(nd_db.keys()))

db_ch = nd_db['Off_Off'] if 'Off_Off' in nd_db.keys() else nd_db[list(nd_db.keys())[0]]
norm = Reflectivity(db_ch, normalization=None,
                    x_pos=227, x_width=12, y_pos=136, y_width=100,
                    bg_pos=30, bg_width=20, dpix=226, tth=0)

dr_ch = nd_dr['Off_Off']
oS = OffSpecular(dr_ch, scale=1.0, P0=0, PN=0,
                 x_pos=172.3, x_width=17, y_pos=137.5, y_width=55,
                 bg_pos=30, bg_width=20, extract_fan=False,
                 dpix=168, tth=0.975739, normalization=norm)

# BG-off, no-crop reconstruction: S_nobg = I * scale_opt / norm.I  (scale_opt=1)
I = np.asarray(oS.I)          # (x, tof) pre-BG, pre-norm intensity
normI = np.asarray(norm.I)    # (tof,)
S = np.zeros_like(I, dtype=float)
idx = normI > 0
S[:, idx] = I[:, idx] / normI[idx]
print('DR proton_charge=%.6e pC  DB proton_charge=%.6e pC  ratio db/dr=%.6f'
      % (dr_ch.proton_charge, db_ch.proton_charge, db_ch.proton_charge / dr_ch.proton_charge))
print('v1 S_nobg shape=%s  sum=%.6e  max=%.4e  nonzero=%d'
      % (S.shape, np.nansum(S), np.nanmax(S), int((S != 0).sum())))
np.savez('/tmp/v1_S.npz', S=S, pc_dr=dr_ch.proton_charge, pc_db=db_ch.proton_charge)
