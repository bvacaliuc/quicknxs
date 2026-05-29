#!/usr/bin/env python
"""Probe proton-charge fields in the REF_M .nxs.h5 files to test the
v1-vs-v2 normalization hypothesis.

v1 (qreduce.from_event_h5): proton_charge = DASlogs/proton_charge/value.sum()
v2/Mantid (NormalizeByCurrent): gd_prtn_chrg = entry/proton_charge (total)
"""
import h5py
import numpy as np

RUNS = {
    44159: '/SNS/REF_M/IPTS-34473/nexus/REF_M_44159.nxs.h5',
    44160: '/SNS/REF_M/IPTS-34473/nexus/REF_M_44160.nxs.h5',
    44161: '/SNS/REF_M/IPTS-34473/nexus/REF_M_44161.nxs.h5',
    44033: '/SNS/REF_M/IPTS-34473/nexus/REF_M_44033.nxs.h5',
    44034: '/SNS/REF_M/IPTS-34473/nexus/REF_M_44034.nxs.h5',
    44035: '/SNS/REF_M/IPTS-34473/nexus/REF_M_44035.nxs.h5',
}


def attrs(ds):
    try:
        return {k: ds.attrs[k] for k in ds.attrs}
    except Exception:
        return {}


print(f"{'run':>6} {'entry/proton_charge':>22} {'units':>10} "
      f"{'DASlog.sum()':>16} {'units':>8} {'npulse':>8} {'sum/entry':>10}")
for rn, p in RUNS.items():
    try:
        with h5py.File(p, 'r') as f:
            ekey = 'entry' if 'entry' in f else list(f.keys())[0]
            entry = f[ekey]
            # entry-level total proton charge (what Mantid's gd_prtn_chrg uses)
            pc_entry = None
            pc_entry_units = ''
            if 'proton_charge' in entry:
                pc_entry = float(np.asarray(entry['proton_charge'])[()].sum())
                pc_entry_units = attrs(entry['proton_charge']).get('units', '')
            # DASlogs time series (what v1 sums)
            das_sum = None
            das_units = ''
            npulse = 0
            dpath = 'DASlogs/proton_charge/value'
            if dpath in entry:
                v = np.asarray(entry[dpath][()])
                das_sum = float(v.sum())
                npulse = v.size
                das_units = attrs(entry['DASlogs/proton_charge/value']).get('units', '')
            ratio = (das_sum / pc_entry) if (das_sum and pc_entry) else float('nan')
            print(f"{rn:>6} {pc_entry!s:>22} {str(pc_entry_units):>10} "
                  f"{das_sum!s:>16} {str(das_units):>8} {npulse:>8} {ratio:>10.4f}")
    except Exception as e:
        print(f"{rn:>6}  ERROR: {e}")
