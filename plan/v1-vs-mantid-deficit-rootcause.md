# v1-vs-Mantid off-spec "deficit" — ROOT CAUSE FOUND (2026-05-28)

Session on `feature/read-event-nexus`, using the now-available Mantid envs
(`mr_reduction/.pixi`, `quicknxsv2/.pixi`) and Mantid source (`mantid/`).
Resolves prompt-31 §1 ("specular intensity FIX, DEFERRED — needs Mantid") and §4
(off-spec magnitude gap). **The deficit is NOT inside Mantid MRR.**

## TL;DR

v1 normalizes **every polarization channel by the FULL-run proton charge**.
v2/QuickNXS-4.x normalizes each channel by its **per-channel (spin-state) proton
charge**, because `MRFilterCrossSections` splits the run by SF1/SF2 state and the
charge accrued in each state is only a fraction of the total. For these runs the
direct beams are 100% Off_Off (polarizer out) while the sample runs are ~50/50,
so v1's reflectivity is low by **≈ the data run's time-fraction in that channel**.

This is a real **quicknxsv1 bug for polarized data** in the `.nxs.h5` event path,
not a dialog setting and not a Mantid scaling.

## Evidence chain (all measured this session)

1. **Off-spec extraction code is identical** v1 `OffSpecular._calc_offspec`
   (`qreduce.py:3250`) ≡ v2 `off_specular.py:OffSpecular.__call__`. Same y-width
   normalization, same raw-DB-flux denominator (`norm.I` ≡ v2 `norm_raw`), neither
   applies the `0.005/sin(ai)` footprint. **Only difference:** v1 always does
   `S = I - BG` (line 3314); v2 gates it on `config.subtract_background`.
2. **Loaded (x,y,tof) histograms are identical.** Loading REF_M_44159 in v1
   (`NXSData`, bins=400) vs v2 (`MRFilterCrossSections` + RebinToWorkspace on v1's
   exact tof_edges): Off_Off total 4.079020e5 (v1) vs 4.079090e5 (v2); ROI 4.015190e5
   vs 4.015250e5. Equal to 5 sig figs (the ~1e-5 is v1's unconditional dead-time).
3. **proton_charge total matches** (`entry/proton_charge` == `DASlogs/proton_charge
   /value.sum()` == Mantid `gd_prtn_chrg`, all = 1.0727e12 pC = 297.97 µAh for 44159).
4. **But the per-channel split differs in how each engine USES it:**
   - v1 `NXSData`: Off_Off pc == On_Off pc == 1.0727e12 pC (FULL run; v1 does not split).
   - v2: Off_Off=142.716 µAh, On_Off=155.258 µAh (sum=297.97). Per-channel.
5. **Channel time-fractions** (`getProtonCharge()` per `MRFilterCrossSections` group):

   | run | Off_Off frac | On_Off frac | note |
   |---|---|---|---|
   | 44159 | 0.4790 | 0.5210 | sample |
   | 44160 | 0.5073 | 0.4927 | sample |
   | 44161 | 0.4635 | 0.5365 | sample |
   | 44033 | 1.0000 | (none)  | DB, polarizer out |
   | 44034 | 1.0000 | (none)  | DB |
   | 44035 | 1.0000 | (none)  | DB |

6. **Predicted deficit** v1/v2 = frac_C(DR)/frac_C(DB). DB frac=1, so deficit ≈
   the data run's channel fraction: Off_Off 0.479/0.507/0.464, On_Off 0.521/0.493/0.536
   (On_Off normalized by the DB's only (Off_Off) channel). Matches uvdl3's BG-off
   "uniform ~0.51×" and the per-run 0.38/0.31/0.19 "angle-correlated" specular gap.

## How v1 loses the split

`from_event_h5` (`qreduce.py:1332+`) sets `output.proton_charge = tof_pc.sum()`
(the whole `DASlogs/proton_charge/value`) and only AFTER that splits events into
channels via `_filter_events_by_polarization`. The per-channel `MRDataset` objects
all inherit the same full-run `proton_charge`. The fix must integrate proton_charge
only over each channel's SF-state time intervals (same quantity Mantid's
`MRFilterCrossSections` computes).

## The two stacked factors (off-spec, vs the v4.3.0rc1 `correctReduction`)

- **Factor A — per-channel proton charge (THIS bug):** v1 ≈ frac_C × reference,
  uniform per channel (~0.48–0.54). Per-run ⇒ looks angle-correlated.
- **Factor B — BG subtraction (settings):** v1 always subtracts; `correctReduction`
  was BG-X-OFF (Valeria 2025-04-08; confirmed by uvdl3 commit 5d38124). Adds extra
  off-spec attenuation in the wings (I≈BG there) and the specular/off-spec asymmetry.
  v1 has NO toggle — needs one (v2: `Configuration.subtract_background`).

## What "default settings" can vs cannot do

Settings alone (BG-X off, single-DB to match `correctReduction`'s DB_ID=1/1/1,
dead-time off, bins, band) get to uvdl3's ~0.5× — they CANNOT close Factor A.
Factor A requires a **code fix** (split proton charge per channel). After that the
off-spec should match the reference to ~1.0 (structure already matches:
log-Pearson 0.86–0.97).

## DB-assignment note (session13 input file)

`session13/..._OffSpecSmooth_Off_Off-correct-db-id.dat` header says DB_ID=1/2/3
(paired) but is byte-identical data to `correctReduction` which is DB_ID=1/1/1
(single, all→44033). To match `correctReduction`, reduce **single-DB**, not the
paired header.

## CONFIRMED empirically (2026-05-28)

Direct raw-S run, 44159 Off_Off / DB 44033 / BG-off, both engines:
- v1 S sum = 7.0349e2, v2 S sum = 1.3683e3 → **v1/v2 = 0.5142**.
- Decomposes exactly: pc-split **0.4789** × region-bookkeeping **1.0746** = 0.5146 ≈ 0.5142.
  (region factor = (55/56 y-width) × (1313/1200 DB area) from my probe's ±1px ROI
  mismatch — an artifact of this probe, ~1.0 with identically-set regions.)
- So the *physics* deficit is the **pc-split 0.479**; everything else is bookkeeping.

## End-to-end result (2026-05-28) — fix committed `99baaa3`, BG toggle added

Loaded the session13 extraction, Reduced **single-DB + `--no-subtract-bg`** (pc-fix
active), bins=400, compared to `correctReduction` via `plot_offspec_compare.py`:

| metric (v1/correctReduction) | pre-fix BG-on | **post-fix + BG-off** |
|---|---|---|
| Off_Off median ratio | 0.154 | **0.605** |
| Off_Off spec / offspec | 0.246 / 0.148 | **0.602 / 0.605** |
| On_Off median ratio | 0.175 | **0.604** |
| On_Off spec / offspec | 0.276 / 0.168 | **0.591 / 0.604** |
| log-Pearson (spec) | 0.947 | **0.967–0.969** |
| peak Δ(dx,dy) | (−0.074, 0.105) | **(~0, ~0)** |

- **Asymmetry eliminated** (spec ≈ offspec) → BG-X-off confirmed as the asymmetry cause.
- **~4× magnitude jump** → the pc-split fix.
- **Remaining: a single uniform ~0.6× (≈1.65×)** — identical for both channels and for
  spec vs offspec, so a global scale, NOT the per-channel normalization (the controlled
  single-run raw-S test matches v2 to ~1.0). Candidate causes: off-spec smoothing-kernel
  params (headless `xysigma0≈Qzmax/3≈0.04` vs v2 GUI 0.06 → v1 over-smooths) or
  `correctReduction`'s unrecorded bins/scale. **Definitive next step:** generate a
  controlled v2 off-spec end-to-end (single-DB, BG-off, bins=400) and compare — expect ~1.0.
  Outputs: `/tmp/v1_rematch/{v1_pcfix_bgoff_single_*.dat,cmp_*.png,cmp_*.json}`.

## Remaining to do

- [x] Confirm with a direct raw-S run (DONE: ratio 0.5142 = 0.479 pc × 1.075 region).
- [x] Implement per-channel proton-charge split (DONE, commit 99baaa3).
- [x] Add `subtract_background` option + `--no-subtract-bg` (DONE).
- [x] End-to-end vs correctReduction (DONE: 0.15 → 0.60 uniform, asymmetry gone).
- [ ] Pin the residual ~0.6× with a controlled v2 end-to-end (smoothing-param vs scale).
- [ ] Implement per-channel proton-charge split in `from_event_h5` (TDD).
- [ ] Add `subtract_background` option to v1 `OffSpecular`/`Reflectivity` (default
      preserve current behavior; expose in GUI off-spec dialog).
- [ ] End-to-end: load session13 extraction, Reduce single-DB + BG-off + pc-fix,
      compare to `correctReduction/**`.

Scripts (mode 600): /tmp/pc_probe.py, /tmp/v1_load_probe.py, /tmp/v2_load_probe.py,
/tmp/pc_ratio_probe.py, /tmp/pc_split_probe.py.
