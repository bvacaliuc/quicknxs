# TOF bin count and off-specular coverage — what is and is NOT bin-invariant

This document captures the 2026-06-02 finding that a quicknxsv1 user
challenged: "the selection of how to partition the TOF bins is a purely
statistical choice that the scientist has to control the level of detail
they observe — it MUST NOT in any way alter the data." The investigation
confirms a nuanced answer:

- **Per-cell intensity IS bin-invariant** (within statistical noise) —
  the underlying reduction math (`OffSpecular._calc_offspec`) produces
  a `S(Qx, Qz) ≈ I_sample / I_DB` ratio in which both numerator and
  denominator are *per-bin* sums of events; doubling the bin width
  doubles both, leaving the ratio essentially unchanged.
- **Coverage IS NOT bin-invariant** — the exported off-spec .dat is a
  list of *sample points* in (Qx, Qz), not a regularly-gridded 2D
  histogram. At bins=40 each per-run band has 22–40 Qz points; at
  bins=400, 200–400 points. On a fine Cartesian render the sparse
  sampling at bins=40 leaves visible gaps between adjacent runs'
  bands; the dense sampling at bins=400 fills the same area.
- **Integrated intensity IS NOT bin-invariant** — the .dat row count
  scales with bin count, and each row is an intensity *per bin* (not
  *per unit area*). Total Σ I over all rows is linear in bin count.

These three properties together explain everything the user saw.

## The measurement

Source artifacts (in `~/shared/REF_M/QuickNXSv1/prompt34/`):

| binning | OffSpec.dat              | OffSpec preview                                                   |
|--------:|--------------------------|-------------------------------------------------------------------|
|     40  | `reduced-prompt-34.7/`   | `quicknxsv1-offspec-preview-tof-40-after-prompt-34.7.png` (gaps)  |
|    400  | `reduced-tof-400/`       | `quicknxsv1-offspec-preview-tof-400-flux-10e-8.png` (no gaps)     |

Run from a checked-out quicknxsv1 worktree:

```bash
pixi run python plan/scripts/prompt-35/compare_tof_binning.py \
  --tof40  ~/shared/REF_M/QuickNXSv1/prompt34/reduced-prompt-34.7/REF_M_44159+44160+44161_OffSpec_Off_Off.dat \
  --tof400 ~/shared/REF_M/QuickNXSv1/prompt34/reduced-tof-400/REF_M_44159+44160+44161_OffSpec_Off_Off.dat \
  --out    /tmp/compare-tof-binning-OffSpec-Off_Off.png
```

Result, after binning both onto a common Cartesian (Qx, Qz) grid using
the COARSER input's cell size:

```
rows           : tof40 = 24,016    tof400 = 351,424   (ratio ≈ 14.6×)
nonzero rows   : tof40 = 16,422    tof400 =  93,286   (ratio ≈ 5.7×)
sum_I (total)  : tof40 =   297.5   tof400 =   4047    (ratio ≈ 13.6×)
cells_both     :  1,561           (cells with data in both)
cells_only_40  :      0
cells_only_400 :    623           (covered ONLY at tof400)
cells_both_pos :  1,421
median ratio (I_400 / I_40) on common cells :  0.93
IQR                                          : [0.78, 1.09]
```

### What this means

- `median ratio ≈ 0.93` and `IQR ⊂ [0.78, 1.09]` — per cell the two
  reductions agree to within ~10%. The 7% bias is consistent with the
  Qz/lambda-cell centroid shift that comes from coarser binning, not a
  reduction error.
- `cells_only_400 = 623` and `cells_only_40 = 0` — the TOF=400 grid is
  a strict superset of TOF=40's coverage. There are NO (Qx, Qz) cells
  the user "loses" by going to TOF=400; coarse binning is purely a
  loss of sampling density.
- `sum_I` scales ≈ 14× — total intensity follows the row count, NOT
  the underlying physical signal. Treating the OffSpec .dat as a
  "histogram in (Qx, Qz)" and integrating it gives a number that
  depends on the binning, which is wrong physically. Don't do that
  comparison.

## Why the gaps appear at coarse binning

Each run measures a *band* in (Qx, Qz) at its own angle θ:

```
Qz_run(λ) = (4π/λ) sin(θ/2) cos(α_f - α_i)/2     # roughly
```

At fixed θ, varying λ traces a Qz range. The three runs in the user's
extraction sit at θ ≈ 0.98°, 2.31°, 5.63° and cover roughly disjoint
Qz bands (gaps between them are PHYSICAL — the experiment did not
measure those Qz values). The .dat samples each band at the chosen
binning's λ resolution:

```
bins=40,  band ≈ 22 Qz points  ->  sparse, holes appear between adjacent runs
bins=400, band ≈ 394 Qz points ->  dense, holes (smaller than a pixel) disappear
```

The off-spec preview uses `pcolormesh(..., shading='gouraud')`, which
interpolates between vertices. A masked cell (S=0 from the flux floor)
between two valid cells appears as a black hole at low binning; at
high binning the hole spans only one or two of the dense vertices and
Gouraud blending fills it.

## What is honest to report and what is not

OK to report bin-count-dependent:
- Visual coverage / "no gap" claims about a specific binning.
- Total row count (it is what it is — a sampling count).

NOT OK to report bin-count-dependent:
- Per-(Qx, Qz) intensity should agree across binnings to within ~10%.
- Integrated intensity over the .dat rows (it scales linearly with
  bin count and tells you nothing about the underlying physics).
- A reduction is "right" or "wrong" because of how its sum_I compares
  to a different binning's sum_I.

## Why "use bins=400" is good operating practice

For the kinds of off-spec features the REF_M user looks at (broad,
smooth bands plus a few sharp specular peaks), bins=400 leaves no
visible coverage gaps and the per-cell ratio against bins=40 is ~0.93
median — well below other systematic biases. There is no measured
physical reason to prefer the coarser binning.

The exception is **memory pressure** — bins=400 produces ~14× more rows
in the .dat (47 MB vs 3 MB in the user's case). If a downstream tool
or smoothing pipeline cannot handle that data volume, the coarser
binning is a reasonable trade-off. For interactive use the dialog and
the export both finish in seconds either way.

## What the off-spec preview SHOULD probably do (deferred)

The gaps the user sees at bins=40 are a *visualization* artifact of
sparse (Qx, Qz) sampling with `shading='gouraud'`. Two ways to fix:

1. **Switch shading to 'nearest' or 'flat'**: each (Qx, Qz) cell is
   filled edge-to-edge with the vertex value. Sparse vertices give
   chunky cells but NO gaps between them. Trade-off: 'gouraud' produces
   smoother-looking high-binning plots, which the user likes.
2. **Render onto a fine regular (Qx, Qz) grid by interpolation**: pre-
   smooth in the preview the same way `qcalc.smooth_data` already does
   for the output. Cost: more latency per preview redraw; ties into
   the N4 freeze-mitigation work.

Option 1 is the cheap experiment captured as T2 part 2 in
`plan/prompt-35-todo.md`. Option 2 is design-deferred.
