#!/usr/bin/env python
"""Validate the flux-floor fix (band-crop removed): PAIRED per-run raw off-spec
S, BG-off, scale=1. Expect 44159 artifact suppressed (no huge max) and 44161
high-angle signal RETAINED (S.sum ~200, not ~40)."""
import numpy as np
from quicknxs.qreduce import NXSData, Reflectivity, OffSpecular
import quicknxs.qreduce as q

BASE = '/SNS/REF_M/IPTS-34473/nexus/REF_M_%d.nxs.h5'
PAIR = {44159: 44033, 44160: 44034, 44161: 44035}
DBREG = {44033: (227, 12, 136), 44034: (228.5, 16, 136), 44035: (230.5, 24, 134)}
DR = {44159: (172.3, 17, 0.975739), 44160: (172.3, 17, 2.30687), 44161: (173.3, 17, 5.62792)}

print('MANTID_OFFSPEC_FLUX_FLOOR =', q.MANTID_OFFSPEC_FLUX_FLOOR)
norms = {}
for dbrun, (xp, xw, yp) in DBREG.items():
    nd = NXSData(BASE % dbrun, use_caching=False, bins=400)
    ch = nd['Off_Off'] if 'Off_Off' in nd.keys() else nd[list(nd.keys())[0]]
    norms[dbrun] = Reflectivity(ch, normalization=None, x_pos=xp, x_width=xw,
                                y_pos=yp, y_width=100, bg_pos=30, bg_width=20, dpix=226, tth=0)
    del nd

for run, (xp, xw, tth) in DR.items():
    nd = NXSData(BASE % run, use_caching=False, bins=400)
    ch = nd['Off_Off']
    oS = OffSpecular(ch, scale=1.0, P0=0, PN=0, x_pos=xp, x_width=xw,
                     y_pos=137.5, y_width=55, bg_pos=30, bg_width=20, extract_fan=False,
                     dpix=168, tth=tth, subtract_background=False, normalization=norms[PAIR[run]])
    S = np.asarray(oS.S)
    print('%d -> DB%d: S.sum=%.4e  S.max=%.4e  nonzero=%d'
          % (run, PAIR[run], np.nansum(S), np.nanmax(S), int((S != 0).sum())))
    del nd, oS
