#!/usr/bin/env python
"""Load REF_M_44159 in v1's NXSData and report channel counts / I(tof)."""
import numpy as np
from quicknxs.qreduce import NXSData

PATH = '/SNS/REF_M/IPTS-34473/nexus/REF_M_44159.nxs.h5'
BINS = 400

nxs = NXSData(PATH, use_caching=False, bins=BINS)
print('channels:', list(nxs.keys()))
print()

# y ROI for the data run 44159: y_pos=137, y_width=55 -> [110:166]
y0, y1 = 110, 166
out = {}
for ch in nxs.keys():
    ds = nxs[ch]
    data = ds.data  # (x, y, tof)
    tot = float(data.sum())
    roi = data[:, y0:y1, :].sum(axis=(0, 1))  # I(tof) over full-x, y-ROI
    pc = float(ds.proton_charge)
    print(f'{ch:>8}: data.shape={data.shape}  total_counts={tot:.6e}  '
          f'proton_charge={pc:.6e}  ROI_sum={roi.sum():.6e}')
    out[f'{ch}_Itof'] = roi
    out[f'{ch}_total'] = tot
    out[f'{ch}_pc'] = pc

ds0 = nxs[list(nxs.keys())[0]]
out['tof_edges'] = np.asarray(ds0.tof_edges)
out['lamda'] = np.asarray(getattr(ds0, 'lamda', np.array([])))
out['shape'] = np.asarray(ds0.data.shape)
np.savez('/tmp/v1_44159.npz', **out)
print('\nsaved /tmp/v1_44159.npz; tof bins =', len(ds0.tof_edges) - 1)
print('lambda_center =', getattr(ds0, 'lambda_center', None),
      ' chopper_speed =', getattr(ds0, 'chopper_speed', None))
