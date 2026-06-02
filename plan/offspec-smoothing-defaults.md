# How quicknxsv1 picks Off-Specular smoothing defaults

This document captures the rule the `SmoothDialog` (`quicknxs/gui_utils.py:668`)
uses to seed its **Grid Region**, **Sigma**, and **Grid Size** fields when it
opens. It is reference material; the goal is so that future sessions (and a
potential v2 port of these defaults) can decide whether the existing rule is
appropriate for a given dataset without having to re-derive it from the code.

## What the dialog seeds

The dialog (label "QuickNXS — Smooth Off-Specular") shows three groups of
controls on the right:

| Group        | Fields              | Source for default                                                       |
|--------------|---------------------|--------------------------------------------------------------------------|
| Grid Region  | X1, X2, Y1, Y2      | A **5% inset** of the data extent where the off-spec preview has `I > 0` |
| Grid Size    | X, Y (int)          | Computed from region span and sigma (see formula below)                  |
| Sigma        | X, Y                | **0.5% of the region span**, floored at `1e-4 Å⁻¹`                       |
| R [Sigmas]   | (single)            | Constant default `3.0` — kernel reach in sigma units                     |

The (X1, X2, Y1, Y2) values are in whichever (x, y) coordinate system the user
has selected in the "Off-Specular Preview" radio button:

- **(kiz-kfz) vs Qz**  → x is `ki_z - kf_z`, y is `Q_z`. σx, σy **coupled** by default.
- **(Qx vs Qz)**       → x is `Q_x`,         y is `Q_z`. σx, σy **uncoupled**.
- **(ki_z vs kf_z)**   → x is `ki_z`,        y is `kf_z`. σx, σy **coupled**.

## Exact formula (current behavior, 2026-06-02)

`SmoothDialog.drawPlot` computes the seed values as:

```python
grid_percentage  = 0.05      # 5% inset
sigma_percentage = 0.005     # 0.5% of region span
min_sigma_size   = 0.0001    # floor in 1/Å

# 1. data extent over pixels with I > 0
x_min, x_max, y_min, y_max = bbox of (x, y) where I > 0 in any reduction-list item

# 2. region box (5% inset on each side)
x1 = x_min + grid_percentage  * (x_max - x_min)
x2 = x_max - grid_percentage  * (x_max - x_min)
y1 = y_min + grid_percentage  * (y_max - y_min)
y2 = y_max - grid_percentage  * (y_max - y_min)

# 3. sigma (per axis, floored)
sigma_x = max(sigma_percentage * (x2 - x1), min_sigma_size)
sigma_y = max(sigma_percentage * (y2 - y1), min_sigma_size)

# (kizmkfz / kiz mode): force σy = σx (coupled)
if coupled_mode:
    sigma_y = sigma_x

# 4. grid size (gridSizeCoupled checkbox seeds the spin fields)
grid_x = int( (x2 - x1) / sigma_x * 1.41 )   # sqrt(2)
grid_y = int( (y2 - y1) / sigma_y * 1.41 )

# 5. R [Sigmas]: constant
sigmas = 3.0
```

The `* 1.41` factor (≈ √2) makes the cell diagonal ≈ σ, so each output grid
cell receives contributions from a sigma-circle's worth of input points.

## Worked example (the user's REF_M 44159+44160+44161, Off_Off, take 1)

Off-spec preview in (kiz-kfz) vs Qz mode, after reducing at TOF=400.

| Quantity        | Computed value | Where it comes from |
|-----------------|---------------:|---------------------|
| `x_min, x_max`  | -0.12047, 0.08739 | data extent where `I > 0` (4 active runs) |
| `x2 - x1` span  | 0.20786 | 95% of (x_max - x_min) → -0.1144, 0.0859 |
| `y_min, y_max`  | -0.0494, 0.3953 | data extent where `I > 0` |
| `y2 - y1` span  | 0.4043 | 95% of (y_max - y_min) → -0.0297, 0.3746 |
| `sigma_x`       | 0.001004 | 0.005 × 0.20786 ≈ 0.001039 (after coupling re-snap) |
| `sigma_y`       | 0.001004 | coupled to σx in kizmkfz mode |
| `grid_x`        | 291 | int(0.20786 / 0.001004 × 1.41) |
| `grid_y`        | 567 | int(0.4043 / 0.001004 × 1.41) |
| `sigmas`        | 3.0 | constant default |

These match the screenshots in `~/shared/REF_M/QuickNXSv1/prompt34/`:

- `quicknxs-offspecular-smoothing-options-default.png` — the seeded defaults exactly
- `quicknxs-offspecular-smoothing-options-000525.png`  — user-tuned: σ → 0.000525,
  Y1 → 0.0 (cut unphysical negative Qz)
- `quicknxs-offspecular-smoothing-options-000525-take2.png` — same tuning, fresh session

## Why the user typically has to tune

1. **σ is uniform but the axes are not**.
   In (kizmkfz)-vs-Qz mode, σ is COUPLED — same value in both axes in data units.
   But the y axis (Qz) is typically 2× wider than the x axis (kiz-kfz). So the
   coupled σ spot looks elongated on screen — narrow along x, fat along y.
   The user can either:
   - Tune σ down to the smaller axis's "natural" length (~0.0005), then accept
     a fatter y-spot, or
   - Uncouple σ and tune them independently.
   The current default picks the **mean** of both axes (via the
   `sigma_percentage * (x2-x1)` choice, which uses the X span only).

2. **Y1 is seeded NEGATIVE** because the off-spec extraction emits points
   slightly into negative Qz at the band-edge rows of the lowest-angle run.
   These are noise. The user typically clamps Y1 to 0.

3. **The 5% inset can leave a small ring of un-smoothed border pixels** that
   show up as a faint bright fringe along the region rectangle. Not catastrophic
   but cosmetically unwanted.

## What v4.17.0rc5 / quicknxsv2 do (different — not yet harmonized)

The v2 `smooth_dialog` uses similar `grid_percentage` and `sigma_percentage`
constants but stores them as project-wide settings (not inlined) and the
"sigmas coupling" defaults to **off** in (kizmkfz)-vs-Qz mode rather than on.
The v2 dialog also writes a smoothed `_OffSpec_*_smooth.dat` that includes the
smoothing parameters in the header; v1 writes them only to the per-channel
`*Smooth_*.dat` files via `Exporter.export_offspec_smoothed`.

## What might be worth changing (deferred — not in this prompt's scope)

- **Seed σx and σy from each axis's own span**, not just x.  Today:
  `sigma_x = sigma_y = max(0.005 * (x_span), 1e-4)` in coupled modes.  Better:
  `sigma_x = max(0.005 * x_span, 1e-4); sigma_y = max(0.005 * y_span, 1e-4)`
  even with coupling on, then take the geometric mean for the coupled value.
- **Clamp Y1 ≥ 0 by default** (Qz cannot be negative in a meaningful sense for
  reflectivity). User has to do this manually today.
- **Persist last-used σ across dialog opens** so an iterating user does not have
  to retype 0.000525 every reduce.

These are quality-of-life items for a future session, captured here so they are
on record.
