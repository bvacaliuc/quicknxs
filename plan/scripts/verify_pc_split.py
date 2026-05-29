#!/usr/bin/env python
"""Validate per-channel proton-charge integration vs Mantid's split
(44159: Off_Off=142.716, On_Off=155.258 µAh). h5py only."""
import h5py
import numpy as np

PATH = '/SNS/REF_M/IPTS-34473/nexus/REF_M_44159.nxs.h5'
PC_PER_UAH = 3.6e9

with h5py.File(PATH, 'r') as f:
    e = f['entry']
    sf1_v = e['DASlogs/SF1/value'][()]
    sf1_t = e['DASlogs/SF1/time'][()]
    sf2_single = True
    sf2_v = sf2_t = None
    if 'DASlogs/SF2' in e:
        sf2_v = e['DASlogs/SF2/value'][()]
        sf2_t = e['DASlogs/SF2/time'][()]
        sf2_single = (len(np.unique(sf2_v)) == 1)
    event_tz = e['bank1_events/event_time_zero'][()]
    pc_v = e['DASlogs/proton_charge/value'][()]
    pc_t = e['DASlogs/proton_charge/time'][()]
    print('n_pulse(event_tz)=%d  n_pc=%d  n_pc_time=%d  n_sf1=%d  sf2_single=%s'
          % (len(event_tz), len(pc_v), len(pc_t), len(sf1_v), sf2_single))

    p1i = np.clip(np.searchsorted(sf1_t, event_tz, side='right') - 1, 0, len(sf1_v) - 1)
    pulse_sf1 = sf1_v[p1i]
    if not sf2_single:
        p2i = np.clip(np.searchsorted(sf2_t, event_tz, side='right') - 1, 0, len(sf2_v) - 1)
        pulse_sf2 = sf2_v[p2i]
    else:
        pulse_sf2 = np.zeros_like(pulse_sf1)

    veto = np.ones(len(event_tz), dtype=bool)
    for vk in ['DASlogs/SF1_Veto', 'DASlogs/SF2_Veto']:
        if vk in e:
            vv = e[vk + '/value'][()]
            vt = e[vk + '/time'][()]
            vi = np.clip(np.searchsorted(vt, event_tz, side='right') - 1, 0, len(vv) - 1)
            veto &= (vv[vi] == 0)

    # Map proton charge to each pulse (searchsorted on pc time base)
    pci = np.clip(np.searchsorted(pc_t, event_tz, side='right') - 1, 0, len(pc_v) - 1)
    pc_per_pulse = pc_v[pci]
    # If pc log is per-pulse aligned 1:1, direct indexing should match
    direct_ok = (len(pc_v) == len(event_tz))

    states = {(0, 0): 'Off_Off', (1, 0): 'On_Off', (0, 1): 'Off_On', (1, 1): 'On_On'}
    tot = pc_v.sum()
    for (s1, s2), nm in states.items():
        m = (pulse_sf1 == s1) & (pulse_sf2 == s2) & veto
        if m.sum() == 0:
            continue
        ch_ss = pc_per_pulse[m].sum()
        line = ('%s: pulses=%d  pc(searchsorted)=%.4f uAh  frac=%.4f'
                % (nm, int(m.sum()), ch_ss / PC_PER_UAH, ch_ss / tot))
        if direct_ok:
            ch_dir = pc_v[m].sum()
            line += '   pc(direct)=%.4f uAh' % (ch_dir / PC_PER_UAH)
        print(line)
    print('total pc = %.4f uAh' % (tot / PC_PER_UAH))
    print('MANTID target: Off_Off=142.716  On_Off=155.258  total=297.973 uAh')
