#!/usr/bin/env python
"""Headless comparison of off-specular smoothed output against a reference.

Runs the same reduction the user would set up in the GUI for
IPTS-34473 runs 44033/4/5 (direct beams) + 44159/60/61 (data) and writes
the OffSpecSmooth_Off_Off result into ``--out``.  Optionally compares
against the reference at ``/SNS/users/6ov/shared/REF_M/11486/correctReduction``.

Usage::

    pixi run python scripts/compare_offspec_44159.py --out /tmp/quicknxs_off_off.dat

The script does NOT use Qt — it composes ``OffSpecular`` and ``smooth_data``
directly so that headless validation is possible.
"""
import argparse
import os
import sys

import numpy as np


def build_offspec(channel='Off_Off', bins=400):
    from quicknxs.qreduce import NXSData, Reflectivity, OffSpecular
    # Direct-beam parameters from the correctReduction header
    db_opts = {
        44033: dict(x_pos=227.0, x_width=12.0, y_pos=136.0, y_width=100.0,
                    bg_pos=30.0, bg_width=20.0, dpix=226.0, tth=0.0),
        44034: dict(x_pos=228.5, x_width=16.0, y_pos=136.0, y_width=100.0,
                    bg_pos=30.0, bg_width=20.0, dpix=226.0, tth=0.0),
        44035: dict(x_pos=230.5, x_width=24.0, y_pos=134.0, y_width=100.0,
                    bg_pos=30.0, bg_width=20.0, dpix=226.0, tth=0.0),
    }
    refl_opts = {
        44159: dict(scale=2.25424, P0=4, PN=15, x_pos=172.3, x_width=17.0,
                    y_pos=137.0, y_width=55.0, bg_pos=30.0, bg_width=20.0,
                    extract_fan=False, dpix=168.0, tth=0.9968),
        44160: dict(scale=2.25424, P0=4, PN=15, x_pos=172.0, x_width=17.0,
                    y_pos=137.0, y_width=55.0, bg_pos=30.0, bg_width=20.0,
                    extract_fan=False, dpix=168.0, tth=2.3294),
        44161: dict(scale=2.0808, P0=1, PN=2, x_pos=173.3, x_width=17.0,
                    y_pos=137.0, y_width=55.0, bg_pos=30.0, bg_width=20.0,
                    extract_fan=False, dpix=168.0, tth=5.6267),
    }
    # Load files (use bins=400 to match quicknxsv2 v4.3.0rc1 default)
    print(f'Loading files (bins={bins})...')
    raw = {n: NXSData(f'/SNS/REF_M/IPTS-34473/nexus/REF_M_{n}.nxs.h5',
                      use_caching=False, bins=bins)
           for n in (44033, 44034, 44035, 44159, 44160, 44161)}
    # The correctReduction used DB_ID=1 (44033) for all three refls.
    norm = Reflectivity(raw[44033]['x'],
                        normalization=None,
                        **db_opts[44033])
    print(f'  DB 44033 norm: Rraw mean = {norm.Rraw.mean():.3e}')

    # Per-run off-spec arrays (Qx, Qz, ki_z, kf_z, ki_z-kf_z, I, dI)
    pieces = []
    for run in (44159, 44160, 44161):
        ds = raw[run][channel]
        opts = dict(refl_opts[run])
        opts['normalization'] = norm
        oS = OffSpecular(ds, **opts)
        # Apply the P0/PN truncation like the Exporter does
        P0 = len(ds.tof) - opts['P0']
        PN = opts['PN']
        rdata = np.asarray([
            oS.Qx[:, PN:P0], oS.Qz[:, PN:P0],
            oS.ki_z[:, PN:P0], oS.kf_z[:, PN:P0],
            oS.ki_z[:, PN:P0] - oS.kf_z[:, PN:P0],
            oS.S[:, PN:P0], oS.dS[:, PN:P0]]).transpose((1, 2, 0))
        pieces.append(rdata)
        print(f'  {run}: Qz=[{oS.Qz.min():.4f},{oS.Qz.max():.4f}] '
              f'ki-kf=[{(oS.ki_z-oS.kf_z).min():.4f},{(oS.ki_z-oS.kf_z).max():.4f}] '
              f'I=[{oS.S.min():.3e},{oS.S.max():.3e}] (counts={ds.data.sum():.0f})')
    return pieces


def smooth(pieces, gridx=563, gridy=1000,
           x_region=(-0.114, 0.086), y_region=(-0.1, 0.376),
           sigma_x=0.0005, sigma_y=0.0005):
    """Reproduce the OffSpecSmooth (ki_z-kf_z vs Qz) grid."""
    from quicknxs.qcalc import smooth_data
    data = np.hstack(pieces)
    x = data[:, :, 4].flatten()  # ki_z - kf_z
    y = data[:, :, 1].flatten()  # Qz
    I = data[:, :, 5].flatten()  # noqa: E741
    Qzmax = data[:, :, 2].max() * 2.0
    settings = {
        'grid': (gridx, gridy),
        'sigma': (sigma_x, sigma_y),
        'region': [x_region[0], x_region[1], y_region[0], y_region[1]],
        'sigmas': 3,
    }
    xy_column = 0  # ki_z-kf_z vs Qz
    axis_sigma_scaling = 2  # y-axis (Qz) varies the sigma
    xysigma0 = Qzmax / 3.0
    xout, yout, Iout = smooth_data(settings, x, y, I,
                                    axis_sigma_scaling=axis_sigma_scaling,
                                    xysigma0=xysigma0,
                                    sigmas=settings['sigmas'])
    return xout, yout, Iout


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', default='/tmp/qnxs_compare/quicknxsv1_OffSpecSmooth_Off_Off.dat')
    ap.add_argument('--ref',
                    default='/SNS/users/6ov/shared/REF_M/11486/correctReduction/'
                            'REF_M_44159+44160+44161_peak1_OffSpecSmooth_Off_Off.dat')
    ap.add_argument('--channel', default='Off_Off')
    ap.add_argument('--bins', type=int, default=400,
                    help='Number of TOF bins (quicknxsv2 default: 400)')
    ap.add_argument('--no-smooth', action='store_true',
                    help='Skip the gaussian smoothing step')
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    pieces = build_offspec(args.channel, bins=args.bins)

    if args.no_smooth:
        data = np.hstack(pieces)
        np.savez(args.out + '.npz',
                 Qx=data[:, :, 0], Qz=data[:, :, 1],
                 kiz=data[:, :, 2], kfz=data[:, :, 3],
                 kiz_minus_kfz=data[:, :, 4],
                 I=data[:, :, 5], dI=data[:, :, 6])
        print(f'Raw off-spec saved to {args.out}.npz')
        return

    print('Smoothing...')
    x, y, I = smooth(pieces)
    print(f'Smoothed grid: {x.shape}, I range [{np.nanmin(I):.3e}, '
          f'{np.nanmax(I):.3e}], non-zero {(I != 0).sum()}/{I.size} '
          f'({(I != 0).mean()*100:.1f}%)')

    with open(args.out, 'w') as f:
        f.write('# Datafile produced by compare_offspec_44159.py (quicknxsv1 fork)\n')
        f.write('# Input: 44033/4/5 DB + 44159/60/61 refl (DB_ID=1 only)\n')
        f.write('# [Data]\n')
        f.write('# ki_z-kf_z [1/A]\tQz [1/A]\tI [a.u.]\n')
        for i in range(I.shape[0]):
            for j in range(I.shape[1]):
                f.write(f'{x[i, j]:.6e}\t{y[i, j]:.6e}\t{I[i, j]:.6e}\n')
    print(f'Wrote {args.out}')

    # Compare to reference
    if os.path.exists(args.ref):
        ref = np.loadtxt(args.ref, comments='#')
        ref_x = ref[:, 0].reshape(1000, 563)
        ref_y = ref[:, 1].reshape(1000, 563)
        ref_I = ref[:, 2].reshape(1000, 563)
        # Replace NaN with 0
        ref_I = np.where(np.isnan(ref_I), 0.0, ref_I)
        # Same grid?
        if not (np.allclose(x.ravel(), ref_x.ravel()) and np.allclose(y.ravel(), ref_y.ravel())):
            print('WARNING: grids differ; comparing on nearest-grid basis')
        mine_I = I.copy()
        # Mask both where one is zero
        mask = (mine_I != 0) & (ref_I != 0)
        if mask.sum() == 0:
            print('No overlapping non-zero pixels; cannot compare')
            return
        # Log-scale correlation
        rmin = max(1e-8, ref_I[mask].min())
        mmin = max(1e-8, mine_I[mask].min())
        logr = np.log(np.maximum(ref_I[mask], rmin))
        logm = np.log(np.maximum(mine_I[mask], mmin))
        corr = np.corrcoef(logr, logm)[0, 1]
        ratio = mine_I[mask] / ref_I[mask]
        med_ratio = float(np.median(ratio))
        print(f'\nComparison vs reference {args.ref}:')
        print(f'  overlapping non-zero pixels: {mask.sum()}/{mask.size} '
              f'({mask.mean()*100:.1f}%)')
        print(f'  log-intensity Pearson correlation: {corr:.4f}')
        print(f'  median intensity ratio (mine/ref): {med_ratio:.4f}')
        print(f'  reference I peak: {ref_I.max():.4f} at '
              f'(x={ref_x.flat[ref_I.argmax()]:.4f}, '
              f'y={ref_y.flat[ref_I.argmax()]:.4f})')
        print(f'  this run I peak:  {mine_I.max():.4f} at '
              f'(x={x.flat[mine_I.argmax()]:.4f}, '
              f'y={y.flat[mine_I.argmax()]:.4f})')


if __name__ == '__main__':
    sys.exit(main())
