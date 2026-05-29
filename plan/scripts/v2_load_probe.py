#!/usr/bin/env python
"""Load REF_M_44159 via quicknxsv2 (Mantid MRFilterCrossSections) and report
per-channel counts on v1's exact tof binning, to compare loaded histograms."""
import numpy as np
from quicknxs.interfaces.configuration import Configuration
from quicknxs.interfaces.data_handling.data_set import NexusData

PATH = '/SNS/REF_M/IPTS-34473/nexus/REF_M_44159.nxs.h5'
v1 = np.load('/tmp/v1_44159.npz')
tof_edges = np.asarray(v1['tof_edges'], dtype=float)
print('v1 tof_edges: n=%d range=[%.1f, %.1f]' % (len(tof_edges), tof_edges[0], tof_edges[-1]))

conf = Configuration()
conf.tof_overwrite = tof_edges  # force v1's binning bin-for-bin
print('conf: peak_position=%s subtract_background=%s tof_bins=%s tof_bin_type=%s'
      % (conf.peak_position, conf.subtract_background, conf.tof_bins, conf.tof_bin_type))

nd = NexusData(PATH, conf)
xs = nd.load()
print('channels:', list(xs.keys()))
for name, cs in xs.items():
    try:
        cs.process_configuration()
        cs.prepare_plot_data()
        data = np.asarray(cs.data)  # (x, y, tof)
        roi = data[:, 110:166, :].sum(axis=(0, 1))
        print(f'{name:>10}: shape={data.shape}  raw_events={cs.total_counts:.6e}  '
              f'binned_total={data.sum():.6e}  ROI(y110:166)={roi.sum():.6e}  '
              f'pc={float(cs.proton_charge):.6e}')
        np.savez(f'/tmp/v2_44159_{name}.npz', Itof_roi=roi, total=data.sum(),
                 raw_events=cs.total_counts, pc=float(cs.proton_charge),
                 shape=np.asarray(data.shape))
    except Exception as e:
        import traceback
        print(f'{name}: ERROR {e}')
        traceback.print_exc()
