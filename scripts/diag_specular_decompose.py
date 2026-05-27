#!/usr/bin/env python
"""Decompose the quicknxsv1 specular reduction vs a QuickNXS v2 reference,
PER SEGMENT, to localize the intensity discrepancy.

Background
----------
Loading a v2 reduced ``Specular_*.dat`` through quicknxsv1's "Load Extraction"
path reproduces the v2 R(Qz) *shape* well (log-R Pearson ~0.96) but the
*intensity* is low.  ``validate_load_reduced_specular.py`` reports the median
ratio over the whole stitched curve (~0.31, i.e. "~3.2x dim").

This script shows that the offset is NOT a single global constant: in each
run's *exclusive* Qz range (where that run alone feeds the stitched reference,
so the per-run stitch ``scale`` cancels and the comparison is effectively
per-run RAW v1/v2), the median ratio varies with incident angle, e.g. for
REF_M_44159+44160+44161:

    44159  ai=0.00786 rad   median v1/ref ~= 0.38
    44160  ai=0.01948 rad   median v1/ref ~= 0.31
    44161  ai=0.04831 rad   median v1/ref ~= 0.19

The footprint scale ``0.005/sin(ai)`` and the ROI-area ratio are *identical*
between v1 and the v2/mr_reduction reference (see plan/prompt-31-load-reduced-data.md),
so this angle-correlated, per-run residual is produced inside Mantid's
``MagnetismReflectometryReduction`` algorithm (not reproduced here).

Usage
-----
    pixi run python scripts/diag_specular_decompose.py [--recipe <v2 Specular .dat>]
"""
import argparse

import numpy as np
from numpy import sin

from quicknxs.qio import HeaderParser
from quicknxs.qreduce import NXSData  # noqa: F401  (import side effects / parity)

DEFAULT_RECIPE = ("/home/bvacaliuc/shared/REF_M/11486/correctReduction/"
                  "REF_M_44159+44160+44161_peak1_Specular_Off_Off.dat")


def reg_and_size(opt):
    """Replicate Reflectivity._calc_normal's integer ROI + 2D pixel area."""
    xw, yw, xp, yp = opt['x_width'], opt['y_width'], opt['x_pos'], opt['y_pos']
    reg = [int(round(xp - xw / 2.)), int(round(xp + xw / 2. + 1)),
           int(round(yp - yw / 2.)), int(round(yp + yw / 2. + 1))]
    return reg, float((reg[3] - reg[2]) * (reg[1] - reg[0]))


def read_reference_table(path):
    qz, rr = [], []
    with open(path) as fh:
        for line in fh:
            if line.startswith('#') or not line.strip():
                continue
            p = line.split()
            if len(p) >= 3:
                try:
                    qz.append(float(p[0])); rr.append(float(p[1]))
                except ValueError:
                    pass
    return np.array(qz), np.array(rr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recipe", default=DEFAULT_RECIPE)
    args = ap.parse_args()

    parser = HeaderParser(HeaderParser.read_file_header(args.recipe), parse_meta=True)
    parser.parse()
    refls = parser.refls
    qz, rr = read_reference_table(args.recipe)

    extents = [(float(np.nanmin(r.Q)), float(np.nanmax(r.Q))) for r in refls]

    def exclusive_range(i):
        lo, hi = extents[i]
        for j, (lo2, hi2) in enumerate(extents):
            if j == i:
                continue
            if lo2 <= lo <= hi2:
                lo = max(lo, hi2)
            if lo2 <= hi <= hi2:
                hi = min(hi, lo2)
        return lo, hi

    print("seg number  ai(rad)  sin(ai)  sin_scale  scale   pc         size  "
          "excl_Qz             n  median(v1/ref)")
    for i, refl in enumerate(refls):
        _, size = reg_and_size(refl.options)
        k = int(np.argmax(refl.Iraw > 0))
        pc = (refl.Iraw[k] / refl.I[k]) / size if refl.I[k] else float('nan')
        sscale = 0.005 / sin(refl.ai)
        lo, hi = exclusive_range(i)
        q = np.asarray(refl.Q); R = np.asarray(refl.R)
        good = np.isfinite(R) & (R > 0) & np.isfinite(q) & (q >= lo) & (q <= hi)
        ratios = [RR / float(np.interp(qq, qz, rr))
                  for qq, RR in zip(q[good], R[good])
                  if qz.min() <= qq <= qz.max() and np.interp(qq, qz, rr) > 0]
        med = float(np.median(ratios)) if ratios else float('nan')
        print(f"{i}   {refl.options.get('number')}  {refl.ai:.5f}  {sin(refl.ai):.5f}  "
              f"{sscale:.4f}    {refl.options.get('scale'):.4f}  {pc:.3e}  {int(size)}  "
              f"[{lo:.4f},{hi:.4f}]   {len(ratios):3d}  {med:.4f}")


if __name__ == "__main__":
    main()
