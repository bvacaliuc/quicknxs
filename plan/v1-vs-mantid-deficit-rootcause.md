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

## DB-assignment note (session13 input file) — CORRECTED 2026-05-29

**Earlier in this session I wrote that `correctReduction` is "single-DB" — that was
WRONG.** `correctReduction` is a **PAIRED** reduction (44159→44033, 44160→44034,
44161→44035); its `DB_ID=1/1/1` column is a **v2 writer bug** (pass-by-value int in
`quicknxs_io._get_cross_section_config_values`). The `[Direct Beam Runs]` block proves
paired: it lists three *different* DB run numbers (44033/44034/44035). The session13
`-correct-db-id.dat` relabels DB_ID→1/2/3, which is the *corrected* paired assignment.
**To reproduce `correctReduction`, reduce `--db-mode paired`** (or `header` on the
-correct-db-id file), NOT single. Full analysis + v1↔v2 interop matrix:
`plan/db-id-bug-and-interop.md`. (My single-DB end-to-end above is therefore the wrong
db-mode; the per-run raw-S numbers still hold for 44159 since single==paired there.)

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
- **Remaining residual is NOT a global scale.** Peak (specular-ridge) intensity ratio
  is ~0.94 (Off_Off) / 1.05 (On_Off) — **v1 matches the reference at the bright peak** —
  but the median (off-spec wings) is ~0.60 (q25 0.49, q75 0.77). So v1 is dimmer only in
  the *dim/wing* regions, i.e. higher contrast than the reference. The per-channel
  normalization is correct (controlled single-run raw-S ~1.0; peak ~1.0). Candidate
  cause was pinned by per-run raw-S (BG-off, scale=1, DB 44033, vs a controlled v2 run):

  | run | v1 S.sum | v2 S.sum | v1/v2 | note |
  |---|---|---|---|---|
  | 44159 | 1271 | 1368 | 0.93 | 1.4-band costs ~13% (low-angle artifact region) |
  | 44160 | 137 | 156 | 0.88 | mid-angle, ~ROI factor |
  | 44161 | 40 | 186 | **0.22** | **high-angle: 1.4-band cuts real signal** |

  **The 1.4 Å off-spec band-crop is the residual, and it is too blunt.** For 44161
  (highest angle, tth=5.63°) the legitimate high-Q signal sits at SHORT λ (~2.4 Å) —
  the *same band edge* as run 44159's low-angle 1-count artifact. Cropping to 1.4 Å
  removes both: 44161 S.sum 40→**200** and max 0.04→**7.1** when the band is widened to
  1.6 (then it matches v2's 186 to ~1.08, the ROI-bookkeeping factor — like the other
  runs). So **every run's per-run reduction is correct (~1.07 vs a controlled v2)**;
  ruled out: smoothing `xysigma0` (median invariant 0.59–0.61 over 0.06–0.20) and a
  global scale (peak matches). The crop's damage scales with angle (44159 −13%, 44160
  ~0, 44161 −78%); the merged median (~0.6) and the artifact (returns at 1.6) are the
  two horns of a fixed-λ crop that cannot separate a real high-angle edge from a
  low-angle artifact.

  **FIXED 2026-05-29 — flux floor replaces the band-crop.** `_calc_offspec` now masks
  TOF bins where the direct-beam flux is below `MANTID_OFFSPEC_FLUX_FLOOR` (=1e-3) of the
  DB's own peak flux, instead of cropping a fixed λ band. (Why fine binning, not v2,
  caused it: v1's 400 fine TOF bins leave one-count bins at the DB's poorly-illuminated
  edges; v2's coarse default `tof_bins`=400-µs-step bins average them away. The floor
  removes the spike at its cause for any binning.) PAIRED per-run raw-S validation
  (`plan/scripts/validate_fix_{v1,v2}.py`, BG-off, scale=1), v1-floor vs v2:

  | run | v1 S.sum | v2 S.sum | v1/v2 | 44161 was (band-crop) |
  |---|---|---|---|---|
  | 44159→44033 | 1439 | 1368 | 1.05 | — (artifact max 25.6 → **1.18**) |
  | 44160→44034 | 243 | 219 | 1.11 | — |
  | 44161→44035 | 137 | 136 | **1.01** | 0.22 (sum 40) → **retained** |

  All three now match v2 at the ~1.07 ROI-bookkeeping factor; **44161's high-angle signal
  is retained** (1.01 vs the band-crop's 0.22) and **44159's artifact is masked** (max
  1.18, the noisy low-flux edge that `correctReduction` smooths away). Regression tests:
  `qreduce_test.py::test_offspec_masks_low_flux_direct_beam_bins` +
  `::test_offspec_flux_floor_tames_low_flux_blowup`.

  **Full closure vs the ARCHIVED correctReduction** (still ~0.6 merged after a band
  fix) additionally needs matching its per-run scale convention (2.254/2.081) and exact
  bins/pipeline — generate a CONTROLLED v2 end-to-end (3-run merge, single-DB, BG-off,
  same scales/bins/smoothing) and compare; expect ~1.0.
  Scratch outputs (regenerable via `plan/scripts/` + `scripts/reduce_offspec_headless.py`):
  `/tmp/v1_rematch/{v1_pcfix_bgoff_*_*.dat,v1_band16_*.dat,v1_xys*_*.dat,cmp_*.json}`.

## Remaining to do

- [x] Per-channel proton-charge split in `from_event_h5_filtered` (commit 99baaa3).
- [x] `subtract_background` option + `--no-subtract-bg` (commit 5b6317b).
- [x] DB_ID investigation — it's a v2 writer bug; reproduce with `--db-mode paired`
      (`plan/db-id-bug-and-interop.md`).
- [x] Replace the band-crop with the direct-beam flux floor; per-run raw-S validated
      (44161 0.22→1.01, 44159 artifact masked).
- [ ] **End-to-end PAIRED + flux-floor + BG-off vs `correctReduction`** — blocked
      2026-05-29 by the `/SNS/users/6ov` sshfs mount (Errno 5 I/O error; the rclone
      `/SNS/REF_M` raw-NXS mount is fine). Retry when the sshfs mount recovers; expect a
      uniform near-1.0 (the GUI reference is coarse-binned + smoothed, so a small
      smoothing/bin difference may remain — quantify then).
- [ ] Expose `subtract_background` (and optionally the flux floor) in the GUI off-spec
      dialog so the operator can set BG-X off without the headless script.
- [ ] (Upstream) fix v2's `quicknxs_io` DB_ID writer; harden v1's reader to warn on a
      1/1/1 column with a multi-DB block (`plan/db-id-bug-and-interop.md`).

Diagnostic scripts (committed): `plan/scripts/` — `pc_probe.py`, `v1_load_probe.py`,
`v2_load_probe.py`, `pc_ratio_probe.py`, `pc_split_probe.py`, `verify_pc_split.py`,
`v1_offspec_S.py`, `v2_offspec_S.py`, `v1_offspec_allruns.py`, `v2_offspec_allruns.py`,
`reduce_band16.py`, `sweep_xysigma0.py`, `test_44161_crop.py`, `validate_fix_v1.py`,
`validate_fix_v2.py`. See `plan/scripts/README.md` for which env each needs and the run
order. Regenerable scratch outputs go to `/tmp/v1_rematch/`.
