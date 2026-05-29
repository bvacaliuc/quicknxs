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

  **Proper fix (replaces the band-crop):** guard the off-spec normalization on the
  direct-beam *flux* (e.g. mask only where the raw DB counts are genuinely ~0, the
  v2-faithful `norm_raw>0` on RAW integer counts), not a blanket λ-band crop. Then
  44159's artifact is masked at its true cause (no DB flux) while 44161's real signal
  (which HAS DB flux) is kept. NOTE: prompt-31 tried `norm.I` and called it a "no-op";
  re-examine why v2's RAW-count guard avoids the blow-up that v1's `I=Rraw` did.

  **Full closure vs the ARCHIVED correctReduction** (still ~0.6 merged after a band
  fix) additionally needs matching its per-run scale convention (2.254/2.081) and exact
  bins/pipeline — generate a CONTROLLED v2 end-to-end (3-run merge, single-DB, BG-off,
  same scales/bins/smoothing) and compare; expect ~1.0.
  Scratch outputs (regenerable via `plan/scripts/` + `scripts/reduce_offspec_headless.py`):
  `/tmp/v1_rematch/{v1_pcfix_bgoff_*_*.dat,v1_band16_*.dat,v1_xys*_*.dat,cmp_*.json}`.

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

Diagnostic scripts (committed): `plan/scripts/` — `pc_probe.py`, `v1_load_probe.py`,
`v2_load_probe.py`, `pc_ratio_probe.py`, `pc_split_probe.py`, `verify_pc_split.py`,
`v1_offspec_S.py`, `v2_offspec_S.py`, `v1_offspec_allruns.py`, `v2_offspec_allruns.py`,
`reduce_band16.py`, `sweep_xysigma0.py`, `test_44161_crop.py`. See `plan/scripts/README.md`
for which env each needs and the run order. Regenerable scratch outputs go to `/tmp/v1_rematch/`.
