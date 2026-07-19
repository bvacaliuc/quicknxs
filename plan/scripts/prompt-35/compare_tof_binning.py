#!/usr/bin/env python
"""Compare two quicknxsv1 off-spec exports that differ ONLY in TOF binning.

The two inputs come from REDUCING THE SAME RAW DATA with two values
of `bins` (event-mode TOF bin count): one at 40, one at 400.
If reduction is bin-invariant (the user's expectation) the two grids
should converge to the same intensity over their common (Qx, Qz)
region after we coarse-grain the finer one onto the same cells as
the coarser one.

This script:
1. Loads both 7-column OffSpec .dat files (Qx, Qz, kiz, kfz, kiz-kfz, I, dI)
2. Bins each onto a COMMON Cartesian (Qx, Qz) grid using
   the COARSER input's cell size (so the comparison is fair)
3. Computes per-cell intensity ratio prop/ref, total integrated I,
   number of "valid" (positive, both sides) cells, and the share
   of cells where one binning has signal and the other doesn't.

Output: stdout summary table + an artifact PNG with side-by-side
maps + ratio map + ratio histogram.

Usage:
  pixi run python plan/scripts/prompt-35/compare_tof_binning.py \
    --tof40  /path/to/REF_M_..._OffSpec_*_Off.dat   \
    --tof400 /path/to/REF_M_..._OffSpec_*_Off.dat   \
    --out    /tmp/compare-tof-binning.png

The user's claim is that TOF binning is a *display* / statistical
parameter and must NOT alter the underlying physical data.  If that
holds, ratio histograms should peak near 1.0 with narrow spread and
the integrated intensities should agree.
"""
import argparse
import os
import sys

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm


def load_offspec_7col(path):
    """Return (Qx, Qz, I, dI) flat arrays from a 7-column OffSpec.dat."""
    data = np.loadtxt(path, comments='#')
    # cols: 0=Qx, 1=Qz, 2=kiz, 3=kfz, 4=kiz-kfz, 5=I, 6=dI
    return data[:, 0], data[:, 1], data[:, 5], data[:, 6]


def grid_bin(Qx, Qz, I, xbins, ybins):
    """Bin scattered (Qx, Qz, I) into a 2D grid using mean of nonzero cells.

    Cells with no contributions are NaN; cells with at least one contribution
    are the mean of contributing I values.  This treats the input as a sparse
    sampling of a continuous field — the right comparison when one input is
    a finer/sparser sampling than the other.
    """
    H_sum, *_ = np.histogram2d(Qx, Qz, bins=[xbins, ybins], weights=I)
    H_cnt, *_ = np.histogram2d(Qx, Qz, bins=[xbins, ybins])
    with np.errstate(invalid='ignore', divide='ignore'):
        H = np.where(H_cnt > 0, H_sum / H_cnt, np.nan)
    return H


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--tof40',  required=True, help='TOF=40 OffSpec .dat')
    p.add_argument('--tof400', required=True, help='TOF=400 OffSpec .dat')
    p.add_argument('--out',    required=True, help='output PNG')
    p.add_argument('--nx', type=int, default=60, help='shared Qx bin count')
    p.add_argument('--ny', type=int, default=80, help='shared Qz bin count')
    p.add_argument('--qzmax', type=float, default=0.30)
    p.add_argument('--qxmax', type=float, default=0.006)
    args = p.parse_args()

    print(f'Loading TOF=40  : {args.tof40}')
    Qx40, Qz40, I40, dI40 = load_offspec_7col(args.tof40)
    print(f'  rows={len(Qx40):,}  nonzero_I={(I40 > 0).sum():,}  '
          f'sum_I={I40.sum():.4g}')
    print(f'Loading TOF=400 : {args.tof400}')
    Qx400, Qz400, I400, dI400 = load_offspec_7col(args.tof400)
    print(f'  rows={len(Qx400):,}  nonzero_I={(I400 > 0).sum():,}  '
          f'sum_I={I400.sum():.4g}')

    # Common Cartesian grid spanning the intersect.
    xbins = np.linspace(-args.qxmax, args.qxmax, args.nx + 1)
    ybins = np.linspace(0.0,        args.qzmax, args.ny + 1)

    H40  = grid_bin(Qx40,  Qz40,  I40,  xbins, ybins)
    H400 = grid_bin(Qx400, Qz400, I400, xbins, ybins)

    both_valid = ~np.isnan(H40) & ~np.isnan(H400)
    only40     =  ~np.isnan(H40) &  np.isnan(H400)
    only400    =   np.isnan(H40) & ~np.isnan(H400)
    both_pos   = both_valid & (H40 > 0) & (H400 > 0)

    if both_pos.any():
        ratio = H400[both_pos] / H40[both_pos]
        log_r = np.log10(ratio)
        median_r = np.median(ratio)
        q25, q75 = np.quantile(ratio, [0.25, 0.75])
    else:
        median_r = q25 = q75 = float('nan')
        ratio = np.array([])

    print()
    print('On common Cartesian (Qx, Qz) grid:')
    print(f'  cells_both_valid    {both_valid.sum():,}')
    print(f'  cells_only_TOF40    {only40.sum():,}')
    print(f'  cells_only_TOF400   {only400.sum():,}')
    print(f'  cells_both_positive {both_pos.sum():,}')
    if both_pos.any():
        print(f'  median ratio (400/40) {median_r:.4f}')
        print(f'  IQR ratio (400/40)    [{q25:.4f}, {q75:.4f}]')
    print(f'  total_I_TOF40       {np.nansum(H40):.4g}')
    print(f'  total_I_TOF400      {np.nansum(H400):.4g}')

    # Visual
    fig, ax = plt.subplots(2, 3, figsize=(15, 10))
    extent = (xbins[0], xbins[-1], ybins[0], ybins[-1])
    vmin, vmax = 1e-9, 1e-4
    # row 0: maps
    for col, H, title in [(0, H40,  'TOF=40 (binned-to-shared-grid)'),
                          (1, H400, 'TOF=400 (binned-to-shared-grid)')]:
        Hplot = np.where(np.isnan(H), 0, H).T
        im = ax[0, col].imshow(Hplot, origin='lower', aspect='auto',
                                extent=extent,
                                norm=LogNorm(vmin=vmin, vmax=vmax),
                                cmap='gist_ncar')
        ax[0, col].set_title(title)
        ax[0, col].set_xlabel('Qx [1/A]')
        ax[0, col].set_ylabel('Qz [1/A]')
        plt.colorbar(im, ax=ax[0, col])

    # row 0 col 2: ratio map
    R = np.where(both_pos, H400 / H40, np.nan).T
    im = ax[0, 2].imshow(R, origin='lower', aspect='auto',
                         extent=extent, vmin=0.5, vmax=2.0, cmap='RdBu_r')
    ax[0, 2].set_title('Ratio TOF400/TOF40 (per cell)')
    ax[0, 2].set_xlabel('Qx [1/A]')
    ax[0, 2].set_ylabel('Qz [1/A]')
    plt.colorbar(im, ax=ax[0, 2])

    # row 1 col 0: ratio histogram
    if both_pos.any():
        ax[1, 0].hist(ratio, bins=np.logspace(-1, 1, 60))
        ax[1, 0].set_xscale('log')
        ax[1, 0].axvline(1.0,    color='k', linestyle='--', label='ratio=1')
        ax[1, 0].axvline(median_r, color='r', linestyle='-',  label=f'median={median_r:.3f}')
        ax[1, 0].set_xlabel('I(TOF=400) / I(TOF=40)')
        ax[1, 0].set_ylabel('cells')
        ax[1, 0].set_title('per-cell ratio distribution (both positive)')
        ax[1, 0].legend()

    # row 1 col 1: coverage by Qz row
    qz_centers = 0.5 * (ybins[:-1] + ybins[1:])
    n_both    = both_valid.sum(axis=0)
    n_only40  = only40.sum(axis=0)
    n_only400 = only400.sum(axis=0)
    ax[1, 1].plot(qz_centers, n_both,    label='both have data')
    ax[1, 1].plot(qz_centers, n_only40,  label='only TOF=40')
    ax[1, 1].plot(qz_centers, n_only400, label='only TOF=400')
    ax[1, 1].set_xlabel('Qz [1/A]')
    ax[1, 1].set_ylabel('cell count')
    ax[1, 1].set_title('Where do the two coverages differ?')
    ax[1, 1].legend()

    # row 1 col 2: total intensity per Qz row
    I_qz_40  = np.nansum(H40,  axis=0)
    I_qz_400 = np.nansum(H400, axis=0)
    ax[1, 2].plot(qz_centers, I_qz_40,  label='TOF=40')
    ax[1, 2].plot(qz_centers, I_qz_400, label='TOF=400')
    ax[1, 2].set_yscale('log')
    ax[1, 2].set_xlabel('Qz [1/A]')
    ax[1, 2].set_ylabel('sum I [a.u.]')
    ax[1, 2].set_title('Integrated I per Qz row (both binnings)')
    ax[1, 2].legend()

    plt.tight_layout()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    fig.savefig(args.out, dpi=120)
    print(f'\nWrote {args.out}')


if __name__ == '__main__':
    main()
