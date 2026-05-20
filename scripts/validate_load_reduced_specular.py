#!/usr/bin/env python
"""Validate the "Load Reduced Data" path against a QuickNXS v2 reference.

Loads a QuickNXS v2 (4.3.0rc1) specular ``.dat`` file *through the same
``HeaderParser`` the GUI's "Load Extraction..." menu uses*, re-reconstructs
the ``Reflectivity`` objects from the embedded recipe (direct beams + data
runs + per-run scale factors), stitches them into a single R(Qz) curve and
compares it statistically to the reference ``[Data]`` table written in the
same file.

This proves quicknxsv1 can both *parse* a v2 reduced file (regression:
the ``[Global Options]`` single-space bug) and *reproduce* a statistically
similar specular curve from it.

Usage:
    pixi run python scripts/validate_load_reduced_specular.py \
        [--recipe /SNS/users/6ov/shared/REF_M/11486/correctReduction/REF_M_44159+44160+44161_peak1_Specular_Off_Off.dat]
"""
import argparse
import sys

import numpy as np

from quicknxs.qio import HeaderParser

DEFAULT_RECIPE = ("/SNS/users/6ov/shared/REF_M/11486/correctReduction/"
                  "REF_M_44159+44160+44161_peak1_Specular_Off_Off.dat")


def read_reference_table(path):
    """Return (Qz, R, dR) from the ``[Data]`` block of a QuickNXS .dat file."""
    qz, r, dr = [], [], []
    with open(path, "rb") as fh:
        text = fh.read().decode("utf8")
    for line in text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            qz.append(float(parts[0]))
            r.append(float(parts[1]))
            dr.append(float(parts[2]))
        except ValueError:
            continue
    return np.array(qz), np.array(r), np.array(dr)


def stitch_refls(refls):
    """Concatenate every reconstructed refl's positive-R points (R already
    carries options['scale']) and sort by Qz."""
    q, r = [], []
    for refl in refls:
        good = np.isfinite(refl.R) & (refl.R > 0) & np.isfinite(refl.Q)
        q.append(np.asarray(refl.Q)[good])
        r.append(np.asarray(refl.R)[good])
    q = np.concatenate(q)
    r = np.concatenate(r)
    order = np.argsort(q)
    return q[order], r[order]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recipe", default=DEFAULT_RECIPE,
                    help="QuickNXS v2 specular .dat reference/recipe file")
    args = ap.parse_args()

    print("Loading reduced data via HeaderParser (the GUI 'Load Extraction' path)")
    print("  recipe:", args.recipe)
    parser = HeaderParser(HeaderParser.read_file_header(args.recipe), parse_meta=True)
    print("  app/version:", parser.quicknxs_version, "type:", parser.export_type)
    parser.parse()
    print("  reconstructed: %d direct beams, %d refls"
          % (len(parser.norms), len(parser.refls)))
    if not parser.refls:
        print("FAIL: no refls reconstructed")
        return 1
    for refl in parser.refls:
        print("    refl %-10s scale=%.4g  Qz=[%.4f,%.4f]  pts=%d"
              % (refl.options.get("number"), refl.options.get("scale", 1.0),
                 float(np.nanmin(refl.Q)), float(np.nanmax(refl.Q)), len(refl.Q)))

    q_mine, r_mine = stitch_refls(parser.refls)
    q_ref, r_ref, _ = read_reference_table(args.recipe)
    print("\nReference curve: %d points  Qz=[%.4f,%.4f]"
          % (len(q_ref), q_ref.min(), q_ref.max()))
    print("Reproduced curve: %d points  Qz=[%.4f,%.4f]"
          % (len(q_mine), q_mine.min(), q_mine.max()))

    # Interpolate the reproduced curve onto the reference Qz grid over the
    # overlap region and compare in log space.
    lo = max(q_ref.min(), q_mine.min())
    hi = min(q_ref.max(), q_mine.max())
    mask = (q_ref >= lo) & (q_ref <= hi) & (r_ref > 0)
    q_cmp = q_ref[mask]
    r_ref_cmp = r_ref[mask]
    r_mine_interp = np.interp(q_cmp, q_mine, r_mine)
    good = (r_mine_interp > 0) & np.isfinite(r_mine_interp)
    q_cmp, r_ref_cmp, r_mine_interp = q_cmp[good], r_ref_cmp[good], r_mine_interp[good]

    if len(q_cmp) < 5:
        print("FAIL: insufficient overlap (%d points)" % len(q_cmp))
        return 1

    lr_ref = np.log10(r_ref_cmp)
    lr_mine = np.log10(r_mine_interp)
    corr = np.corrcoef(lr_ref, lr_mine)[0, 1]
    ratio = np.median(r_mine_interp / r_ref_cmp)
    rms_dex = float(np.sqrt(np.mean((lr_mine - lr_ref) ** 2)))

    print("\nComparison over Qz=[%.4f,%.4f] (%d points):" % (lo, hi, len(q_cmp)))
    print("  log-R Pearson correlation : %.4f" % corr)
    print("  median ratio (mine/ref)   : %.4f" % ratio)
    print("  RMS log10 residual (dex)  : %.4f" % rms_dex)

    ok = corr > 0.9 and 0.5 < ratio < 2.0
    print("\n%s: load+reproduce specular %s the v2 reference"
          % ("PASS" if ok else "WEAK",
             "statistically matches" if ok else "diverges from"))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
