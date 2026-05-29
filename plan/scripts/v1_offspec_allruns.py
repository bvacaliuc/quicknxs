#!/usr/bin/env python
"""v1 raw off-spec total(S) per run (44159/60/61), all normalized by DB 44033,
BG OFF (via the new subtract_background option), scale=1.0 — compare to v2."""
import numpy as np
from quicknxs.qreduce import NXSData, Reflectivity, OffSpecular

BASE = '/SNS/REF_M/IPTS-34473/nexus/REF_M_%d.nxs.h5'
RUNS = {44159: (172.3, 17, 0.975739), 44160: (172.3, 17, 2.30687), 44161: (173.3, 17, 5.62792)}

nd_db = NXSData(BASE % 44033, use_caching=False, bins=400)
db_ch = nd_db['Off_Off'] if 'Off_Off' in nd_db.keys() else nd_db[list(nd_db.keys())[0]]
norm = Reflectivity(db_ch, normalization=None, x_pos=227, x_width=12,
                    y_pos=136, y_width=100, bg_pos=30, bg_width=20, dpix=226, tth=0)
print('DB 44033 pc=%.6e pC' % db_ch.proton_charge)

for run, (xp, xw, tth) in RUNS.items():
    nd = NXSData(BASE % run, use_caching=False, bins=400)
    ch = nd['Off_Off']
    oS = OffSpecular(ch, scale=1.0, P0=0, PN=0, x_pos=xp, x_width=xw,
                     y_pos=137.5, y_width=55, bg_pos=30, bg_width=20,
                     extract_fan=False, dpix=168, tth=tth,
                     subtract_background=False, normalization=norm)
    S = np.asarray(oS.S)
    print('%d Off_Off: pc=%.6e pC  S.sum=%.6e  S.max=%.4e' % (run, ch.proton_charge, np.nansum(S), np.nanmax(S)))
