#!/usr/bin/env python
"""Render a quicknxsv1 OffSpec .dat with multiple pcolormesh shading modes.

Goal: decide between `shading='gouraud'` (current default in
`main_gui.plot_offspec`) and `shading='nearest'` for the off-spec
preview, by visually comparing the gap behavior at TOF=40 on the
user's 44159+44160+44161 extraction.

Output: a 2x3 PNG with three panels per channel (gouraud, nearest,
flat) so a human can compare gap appearance directly. Also prints the
per-shading area of "low intensity" cells which proxy for visible gaps.

Usage::

    pixi run python plan/scripts/prompt-35/render_offspec_shading.py \\
        --in  /path/to/REF_M_..._OffSpec_Off_Off.dat   \\
        --out /tmp/render-offspec-shading.png
"""
import argparse
import os
import sys

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm


def load_offspec_groups(path):
    """Yield successive (ki_z-kf_z, Qz, I) (Nx, NTOF) blocks from a 7-col file.

    The .dat encodes the off-spec as TOF rows blank-line separated per
    detector x pixel. Each "block" is one x pixel; the (Nx, NTOF) grid
    is reconstructed by stacking the blocks in file order.
    """
    blocks = []
    with open(path, 'r') as fh:
        cur = []
        for line in fh:
            if line.startswith('#'):
                continue
            line = line.strip()
            if not line:
                if cur:
                    blocks.append(np.array(cur, dtype=float))
                    cur = []
                continue
            cur.append([float(x) for x in line.split()])
        if cur:
            blocks.append(np.array(cur, dtype=float))
    # Each block: rows are TOF bins, cols are (Qx, Qz, kiz, kfz, kiz-kfz, I, dI)
    # Stack into (Nx, NTOF) on each scalar.
    NTOF = blocks[0].shape[0]
    if not all(b.shape == blocks[0].shape for b in blocks):
        # File has padding zeros in some blocks; pad/trim to NTOF
        blocks = [b for b in blocks if b.shape == blocks[0].shape]
    Nx = len(blocks)
    data = np.stack(blocks, axis=0)  # (Nx, NTOF, ncols)
    x   = data[:, :, 4]   # ki_z - kf_z
    y   = data[:, :, 1]   # Qz
    I   = data[:, :, 5]   # noqa: E741
    return x, y, I


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--in',  dest='inp', required=True, help='OffSpec .dat (7-col)')
    p.add_argument('--out', required=True)
    p.add_argument('--vmin', type=float, default=1e-8)
    p.add_argument('--vmax', type=float, default=1e-3)
    p.add_argument('--cmap', default='gist_ncar')
    args = p.parse_args()

    print(f'Loading {args.inp}')
    x, y, I = load_offspec_groups(args.inp)
    print(f'  grid: Nx={x.shape[0]}, NTOF={x.shape[1]}')
    print(f'  x range : [{x.min():+.4f}, {x.max():+.4f}]')
    print(f'  y range : [{y.min():+.4f}, {y.max():+.4f}]')
    print(f'  I range : [{I[I>0].min():.3g}, {I.max():.3g}]   '
          f'nonzero {int((I>0).sum()):,}/{I.size:,}')

    fig, axes = plt.subplots(1, 3, figsize=(18, 6), sharey=True)
    shadings = ['gouraud', 'nearest', 'flat']
    for ax, sh in zip(axes, shadings):
        # 'flat' requires Nx+1 / Ny+1 corners, so use auto for safety
        try:
            im = ax.pcolormesh(x, y, I, cmap=args.cmap,
                               norm=LogNorm(vmin=args.vmin, vmax=args.vmax),
                               shading=sh)
        except Exception as exc:
            ax.text(0.5, 0.5, f'pcolormesh shading={sh!r} failed:\n{exc}',
                    transform=ax.transAxes, ha='center', va='center')
            continue
        ax.set_title(f'shading={sh!r}')
        ax.set_xlabel('k_iz - k_fz [1/A]')
        if ax is axes[0]:
            ax.set_ylabel('Qz [1/A]')
        plt.colorbar(im, ax=ax)

    fig.suptitle(f'OffSpec render comparison\n{os.path.basename(args.inp)}',
                 y=1.02)
    plt.tight_layout()
    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    fig.savefig(args.out, dpi=120, bbox_inches='tight')
    print(f'\nWrote {args.out}')


if __name__ == '__main__':
    main()
