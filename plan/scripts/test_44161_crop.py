#!/usr/bin/env python
"""Is run 44161's off-spec deficit the 1.4 A band-crop? Compare S.sum with the
crop at 1.4 (default) vs effectively off, plus the in-band lambda fraction."""
import numpy as np
import quicknxs.qreduce as q
from quicknxs.qreduce import NXSData, Reflectivity, OffSpecular

BASE = '/SNS/REF_M/IPTS-34473/nexus/REF_M_%d.nxs.h5'
nd_db = NXSData(BASE % 44033, use_caching=False, bins=400)
db_ch = nd_db['Off_Off'] if 'Off_Off' in nd_db.keys() else nd_db[list(nd_db.keys())[0]]
norm = Reflectivity(db_ch, normalization=None, x_pos=227, x_width=12,
                    y_pos=136, y_width=100, bg_pos=30, bg_width=20, dpix=226, tth=0)

nd = NXSData(BASE % 44161, use_caching=False, bins=400)
ch = nd['Off_Off']
print('44161 lambda_center=%s chopper_speed=%s' % (
    getattr(ch, 'lambda_center', None), getattr(ch, 'chopper_speed', None)))

for hb in (1.4, 1.6, 20.0):
    q.MANTID_OFFSPEC_HALF_BANDWIDTH = hb
    oS = OffSpecular(ch, scale=1.0, P0=0, PN=0, x_pos=173.3, x_width=17,
                     y_pos=137.5, y_width=55, bg_pos=30, bg_width=20,
                     extract_fan=False, dpix=168, tth=5.62792,
                     subtract_background=False, normalization=norm)
    S = np.asarray(oS.S)
    print('half-band=%5.1f A : S.sum=%.6e  S.max=%.4e  nonzero=%d' % (
        hb, np.nansum(S), np.nanmax(S), int((S != 0).sum())))
print('v2 target (no crop): S.sum=1.857825e+02  S.max=6.6038e+00')
