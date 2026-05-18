#!/usr/bin/env python
"""Side-by-side comparison plot of two OffSpecSmooth .dat files."""
import argparse
import os
import sys

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def load(path):
    data = np.loadtxt(path, comments='#')
    # 1000 rows × 563 cols, columns: [x, y, intensity]
    return (data[:, 0].reshape(1000, 563),
            data[:, 1].reshape(1000, 563),
            data[:, 2].reshape(1000, 563))  # noqa: E741


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ref',
                    default='/SNS/users/6ov/shared/REF_M/11486/correctReduction/'
                            'REF_M_44159+44160+44161_peak1_OffSpecSmooth_Off_Off.dat')
    ap.add_argument('--rver', default='v2 v4.3.0rc1')
    ap.add_argument('--mine',
                    default='/SNS/users/6ov/shared/REF_M/11486/correctReduction/'
                            'REF_M_44159+44160+44161_peak1_OffSpecSmooth_Off_Off.dat')
    ap.add_argument('--mver', default='v2 v4.3.0rc1')
    ap.add_argument('--out', default='/tmp/offspec_compare.png')
    ap.add_argument('--xmin', type=float, default=-0.1)
    ap.add_argument('--xmax', type=float, default=+0.1)
    ap.add_argument('--ymin', type=float, default=+0.0)
    ap.add_argument('--ymax', type=float, default=+0.35)
    args = ap.parse_args()

    # TODO: extract version info from:
    # Datafile created by QuickNXS 4.3.0rc1
    # Datafile created using Mantid 6.12.0
    # Date: 2025-04-08 16:11:14
    # For now, we specifiy on the command line for --rver, --mver

    fig, axs = plt.subplots(1, 3, figsize=(15, 5))
    for ax, (label, path) in zip(axs[:2], [(f'Reference ({args.rver})', args.ref),
                                           (f'This ({args.mver})', args.mine)]):
        if not os.path.exists(path):
            ax.text(0.5, 0.5, f'missing\n{path}',
                    ha='center', va='center', transform=ax.transAxes)
            ax.set_title(label)
            continue
        x, y, I = load(path)  # noqa: E741
        # Mask NaN as transparent
        I_plot = np.where(np.isnan(I), 0, I)
        im = ax.pcolormesh(x, y, np.maximum(I_plot, 1e-6),
                           norm=matplotlib.colors.LogNorm(vmin=1e-6, vmax=2.0),
                           cmap='turbo', shading='nearest')
        ax.set_title(label)
        ax.set_xlabel(r'$k_{i,z} - k_{f,z}$ [Å$^{-1}$]')
        ax.set_ylabel(r'$Q_z$ [Å$^{-1}$]')
        ax.set_xlim(args.xmin, args.xmax)
        ax.set_ylim(args.ymin, args.ymax)
        plt.colorbar(im, ax=ax, label='I [a.u.]')

    # Difference / ratio panel
    if os.path.exists(args.ref) and os.path.exists(args.mine):
        rx, ry, rI = load(args.ref)
        mx, my, mI = load(args.mine)
        # Both on same grid?
        if rx.shape == mx.shape:
            rI_c = np.where(np.isnan(rI), 0, rI)
            mI_c = np.where(np.isnan(mI), 0, mI)
            mask = (rI_c > 0.01) & (mI_c > 0.01)
            ratio = np.where(mask, mI_c / np.maximum(rI_c, 1e-9), np.nan)
            im = axs[2].pcolormesh(rx, ry, ratio,
                                   norm=matplotlib.colors.LogNorm(vmin=0.1, vmax=10),
                                   cmap='RdBu_r', shading='nearest')
            axs[2].set_title('Ratio: mine / correct')
            axs[2].set_xlabel(r'$k_{i,z} - k_{f,z}$ [Å$^{-1}$]')
            axs[2].set_ylabel(r'$Q_z$ [Å$^{-1}$]')
            axs[2].set_xlim(args.xmin, args.xmax)
            axs[2].set_ylim(args.ymin, args.ymax)
            plt.colorbar(im, ax=axs[2], label='ratio')
            # Print summary
            med = float(np.nanmedian(ratio))
            print(f'Median intensity ratio (mine/correct) where both > 0.01: {med:.4f}')
            print(f'Ratio spread: 25%={np.nanpercentile(ratio, 25):.3f}, '
                  f'50%={np.nanpercentile(ratio, 50):.3f}, '
                  f'75%={np.nanpercentile(ratio, 75):.3f}')
        else:
            axs[2].text(0.5, 0.5, f'shape mismatch {rx.shape} vs {mx.shape}',
                        ha='center', va='center', transform=axs[2].transAxes)

    plt.tight_layout()
    plt.savefig(args.out, dpi=110)
    print(f'Wrote {args.out}')


if __name__ == '__main__':
    sys.exit(main())
