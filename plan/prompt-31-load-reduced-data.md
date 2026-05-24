# prompt-31: Load Reduced Data from QuickNXS v2 files

Goal (from the session that produced commits `1b2439f`, `ddb7944`):
quicknxsv1 should open a QuickNXS **v2** reduced `.dat` file via
**File → Load Extraction…** ("Load Reduced Data"), reconstruct the recipe
(direct beams + data runs + scale factors), and reproduce a statistically
similar reduction.

Reference data on this machine:
`/SNS/users/6ov/shared/REF_M/11486/correctReduction/` — 7 files written by
QuickNXS 4.3.0rc1 / Mantid 6.12.0 (2025-04-08, IPTS-34473, DB 44033/34/35,
data 44159/60/61). The intended off-spec/specular "correct" outputs.

## session13 finding (prompt-30.1): off-spec "missing data" = 40-bin under-sampling

The user loaded `correctReduction/...OffSpecSmooth_Off_Off.dat` in the real
GUI (confirming the parser fix end to end) and saw a white horizontal band
at **Qz ≈ 0.06–0.09** in the smoothed off-spec map, vs. the continuous v2
fan. Root-caused empirically (`session13/` vs `correctReduction/`):

- **Not dropped events.** The chopper TOF fix (`_compute_tof_range_us`) is
  present; neither grid has a zero-data Qz band. Coverage analysis: v1's
  central (qx∈[-0.03,0.03]) coverage never exceeds ~73% and is irregular,
  while v2 is 100% above Qz≈0.045. v1's mid-Qz intensity is ~15–100× below
  v2 (`meanI` 2e-4 vs 5e-2), so it sinks below the log colormap floor →
  appears white.
- **Cause: TOF bins = 40, not 400.** `HeaderParser._get_dataset`
  (`qio.py:545`) reads with `NXSData.DEFAULT_OPTIONS` (**bins=40**) and only
  overrides when the recipe has an `[Event Mode Options]` section — which v2
  specular/off-spec `.dat` files do **not**. So Load Extraction reduces at
  40 TOF bins. v2 used 400. 40 bins → a sparse (qx,qz) point cloud → the
  Gaussian smoothing (R=3σ) leaves many empty grid cells (holes/streaks)
  and spreads intensity thin. This is the off-spec face of prompt-28's
  bin-density effect (40-bin intensity ~0.45× of 400-bin).
- The grid-size auto-formula `int((x2-x1)/σ*1.41)` (`gui_utils.py:787`) is
  *fine* (~1.4 cells/σ); the grid is not the problem, the input density is.
- **The GUI cannot work around it:** `eventTofBins` defaults to 40, is
  **capped at 200** (`default_interface.py:81`), and `loadExtraction` does
  not feed it to `_get_dataset` anyway.

### Fix (LANDED, commit `792e445`) + headless verification
Implemented option 1: `HeaderParser(default_bins=…)` → `_get_dataset`
forwards it (an `[Event Mode Options]` entry still overrides);
`loadExtraction` passes the GUI `eventTofBins`; its cap is raised 200→1000
so v2's 400 is selectable. In the GUI: set **Event TOF bins = 400** before
*Load Extraction…*.

Verified headless (`reduce_offspec_headless --no-smooth`, 40 vs 400 bins,
the v2 OffSpecSmooth recipe). TOF slices per run 21–37 → 381–397; central
(x∈±0.03) point cloud 14.5k → 197k (13.6×); peak I 0.865 → 25.57 (~30×).
Smoothed-cell coverage proxy (histogram + 3σ dilation; validated against the
real 40-bin session13 map at 71% vs 73% measured):

| TOF bins | central coverage | gap band Qz[0.05,0.10] |
|---|---|---|
| 40  | 71% | 79% |
| 400 | 91% | **100%** |

So 400 bins fills the gap band and brightens it (~30× I) — the white band
resolves. (A full smoothed re-reduction at 400 bins to image it is left to
the user / a slower run; the proxy + intensity are conclusive.)

### Secondary issues seen in session13 (file separately)
- `pcolormesh ... not monotonically increasing or decreasing` warning
  (`mplwidget.py:311`) — possible cosmetic mis-render of off-spec cells.
- **`Error 139` (SIGSEGV)** at GUI exit after the off-spec session — a
  stability bug, unrelated to the missing-data appearance.

## What landed (committed, tested)

### Parse (was a hard blocker)
`HeaderParser` raised `IndexError` on the v2 `[Global Options]` block
because a long key (`lock_direct_beam_y`) left only one space before its
value and the 2-space column split dropped it. Fixed in `quicknxs/qio.py`
(`_evaluate_global_options` + eval-free `_convert_scalar`). **All 7 v2
files now parse** (`DB=3, DR=3, Global Options` extracted). Test:
`tests/qio_test.py::V2GlobalOptionsParseTest`.

### Reproduce (verified on real data)
`scripts/validate_load_reduced_specular.py` loads the v2
`Specular_Off_Off.dat` *through `HeaderParser` — the same path the GUI's
Load Extraction uses* — reconstructs 3 DBs + 3 refls, stitches R(Qz) and
compares to the embedded `[Data]` table:

```
reconstructed: 3 direct beams, 3 refls
                              40 bins      160 bins
log-R Pearson correlation :   0.9609       0.9670     # shape matches v2
median ratio (mine/ref)   :   0.3109       0.3120     # ~3.2x dim, STABLE
RMS log10 residual (dex)  :   0.6266       0.6233
```

**Shape reproduction is excellent (corr 0.96–0.97).** The intensity offset
is a **constant ~3.2× factor that does NOT move with bin count** (0.311 at
40 bins vs 0.312 at 160). This is *unlike* the off-spec smoothing case in
`plan/prompt-28-findings.md` (where the ratio was bin-density dependent,
0.45→1.30 from 40→80). For **specular**, the bin-independent constant
points to a **normalization-convention** difference, not a binning artifact.

### Root cause (located): the hardcoded `0.005` beam-footprint constant
Per `setup/patterns/numerical-diagnostics.md` (clean-factor audit before
chasing physics): 1/0.311 ≈ **3.21**. The constant is **angle-independent**
(shape matches, corr 0.97), which *rules out* a θ-dependent footprint
correction — that would distort the curve, not scale it.

`quicknxs/qreduce.py` applies the footprint as a **hardcoded constant**:
```python
# Reflectivity.__init__, line ~2929  (and OffSpecular, line ~3010)
if self.ai > 0.0002:
    sin_scale = 0.005 / sin(self.ai)   # 0.005 = nominal beam width, HARDCODED
self.R = sin_scale * self.options['scale'] * self.Rraw
```
Both v1 and v2 carry the same `1/sin(ai)` term, so it **cancels in the
ratio**, leaving the constant `0.005 / W_v2`, where `W_v2` is v2's
geometry-derived footprint width (Mantid `MagnetismReflectometryReduction`).
That constant is the observed ~3.2×.

Note the recipe's `sample_length = 10.0` does **not** enter here — in v1 it
only feeds the Q-**resolution** (`s_width = sample_length*sin(ai)`,
qreduce.py:3185), not the intensity. So the fix is *not* "use
sample_length"; it is "derive the footprint width from the beam/slit +
sample geometry as v2 does, instead of the hardcoded `0.005`."

### Fixing it (separate, validated change — not done here)
Replacing the `0.005` with a geometry-derived footprint changes the
absolute intensity of **every** reduction (specular and off-spec, both
instruments), so it must be validated against several datasets and the v2
reference before landing — out of scope for the Load-Reduced session.
First confirm the constant is exactly reproducible on a **single** refl
(44159 alone vs the reference over its Qz range), then derive `W` from
slit/sample geometry and check the ratio → 1 across all three refls.

## Remaining work

### 1. Resolve the specular normalization constant
Find and document the ~3.2× factor (above). A constant scale is often
acceptable in reflectometry (curves are scaled in fitting), but the match
is only a "stunning success" once the convention is understood. Do **not**
keep raising `--bins` for specular — empirically it does not move the
ratio.

### 2. GUI smoke test of Load Extraction on a v2 file
`make gui` → File → Load Extraction… → pick
`correctReduction/REF_M_44159+44160+44161_peak1_Specular_Off_Off.dat`.
Confirm: 3 DBs populate the normalization table, 3 refls populate the
reduction table, the spinboxes show the refl region (prompt-30), and the
reflectivity plot renders. This exercises `loadExtraction` →
`HeaderParser.parse()` → `setNorm`/`addRefList` end to end (headlessly
covered by `LoadExtractionRoundTrip`, but never clicked through on a real
v2 file).

### 3. Off-specular reproduction
The off-spec path is already validated headlessly in prompt-28
(`scripts/compare_offspec_44159.py`, `scripts/reduce_offspec_headless.py`).
Re-confirm against `correctReduction/*OffSpecSmooth*` after the prompt-30
changes and at matched bins. Note `reduce_offspec_headless.py` uses its own
recipe parser (`parse_recipe`), independent of the `HeaderParser` fix.

### 4. `session12/` files ("what v2 can produce today")
The user referenced `/SNS/users/6ov/shared/REF_M/11486/session12/**` as a
second, harder target. **It does not exist on this mount** (only
`session1`–`session9`; `session12` appears only in
`compare/*-session12.png` filenames). It is likely on the other machine
(`/media/ssd2/...`) or post-dates this mount snapshot. When it appears,
repeat (1)–(3) against it; expect the same load path to work since the
header format is shared.

## Key facts for the next agent
- "Load Reduced Data" in quicknxsv1 == **File → Load Extraction…** ==
  `MainGUI.loadExtraction` → `qio.HeaderParser`.
- v2 and v1 share the `.dat` section format
  (`[Direct Beam Runs]`/`[Data Runs]`/`[Global Options]`/`[Data]`); the
  only parse incompatibility found was the Global Options spacing (fixed).
- The referenced `.nxs.h5` files exist under
  `/SNS/REF_M/IPTS-34473/nexus/REF_M_440{33,34,35,59,60,61}.nxs.h5`.

## prompt-31 Phase 1 update (2026-05-22): footprint hypothesis DISPROVEN

The earlier root-cause above ("replace the hardcoded `0.005` with a
geometry-derived footprint width `W`") is **WRONG** and must NOT be
implemented. Three independent reads of the v2/reference side show the
footprint scale is the **identical** `0.005/sin(θ)` constant that v1 uses,
applied *after* Mantid, together with the **identical** ROI-area ratio:

- quicknxsv2 `src/quicknxs/interfaces/data_handling/data_set.py:297-302`
- quicknxsv2 `test/notebooks/event_reduction.py:64-72` (`quicknxs_scale`)
- **mr_reduction** (branch `next`) `src/mr_reduction/reflectivity_output.py:99-115`
  (`quicknxs_scaling_factor`) — the canonical REF_M reference

All three compute `scale = (norm_x·norm_y)/(peak_x·low_res) · 0.005/sin(tth)`
where `tth = two_theta·π/360 = θ_incident`. v1's `_calc_normal`/`_calc_fan`
apply the same `0.005/sin(ai)` and the same area ratio (the `+1` pixel
offsets even match). So the footprint constant is **not** the discrepancy;
changing it would *break* the agreement with v2's convention, not fix it.

### What the discrepancy actually is: angle-correlated, per-run (NOT a constant)
Decomposing v1 vs the v2 `[Data]` table in each run's **exclusive** Qz range
(where that run alone feeds the stitched reference, so the per-run stitch
`scale` cancels → the ratio is effectively per-run RAW `v1/v2`):

| run   | ai (rad) | sin_scale=0.005/sin | scale | DB    | median v1/ref |
|-------|----------|---------------------|-------|-------|---------------|
| 44159 | 0.00786  | 0.6362              | 2.254 | 44033 | **0.382**     |
| 44160 | 0.01948  | 0.2567              | 2.254 | 44033 | **0.312**     |
| 44161 | 0.04831  | 0.1035              | 2.081 | 44033 | **0.192**     |

- Within a single run it IS a clean constant: the 44159 low-Qz plateau
  (Qz 0.012–0.018) holds steady at v1/ref ≈ 0.375–0.40.
- But it **shrinks as incident angle grows** (0.38 → 0.31 → 0.19): v1 is
  increasingly dim relative to v2 at higher angle. All three runs share the
  same DB (44033), the same ROI pixel area (1008), and 159/160 share the same
  `scale` — so it is NOT scale, area, footprint constant, proton charge, or
  TOF-bin count (the stitched median is bin-independent: 0.311@40, 0.312@160).
- Backing out v2's effective footprint (`sin_scale/ratio`) gives 1.665 /
  0.823 / 0.539 — which does **not** fit `0.005/sin(ai)` or any clean power
  law. So the reference carries an angle-dependent normalization v1 lacks.
- The "constant ~3.2×" framing in this file was a **median over the whole
  stitched curve** that masks this per-run variation (and the RMS residual is
  ~0.63 dex). Because each segment is offset differently, v1's stitched curve
  has small kinks at the overlaps that the same `scale` factors cannot remove.
- **Spin-state check:** the same decomposition on the `On_Off` cross-section
  gives 0.41 / 0.14 / 0.15 (vs `Off_Off` 0.38 / 0.31 / 0.19) for the same
  ai / ROI / scale / DB. So the residual is NOT a clean function of `ai`
  alone — it also varies with cross-section/intensity (caveat: the 44160
  `On_Off` point is low-statistics, n=13). This **rules out a simple `f(ai)`
  footprint patch** and reinforces that the fix needs the actual Mantid
  per-event normalization, not a one-parameter angle correction.

### Localization
The angle-dependent term lives **inside Mantid's
`MagnetismReflectometryReduction`** algorithm. v2 calls it with
`SampleLength=conf.sample_size`, `ConstantQBinning=conf.use_constant_q`,
`UseSANGLE=...` (data_set.py:242-277) and only applies `area·0.005/sin`
*afterward*. The Mantid C++ source is **not on this machine** (bounded
`find` over /home/bvacaliuc/Projects, /opt, /usr found nothing; Mantid is
not importable in v1's pixi env). A populated `mr_reduction` checkout (branch
`next`) is at `/home/bvacaliuc/Projects/Claude/2/mr_reduction` but it only
*calls* the Mantid algorithm — it does not reimplement the per-angle term.

### Reproduce
`pixi run python scripts/diag_specular_decompose.py` (loads the 6 NXS via the
real `HeaderParser` path; ~1 min over sshfs) prints the per-segment table
above. `scripts/validate_load_reduced_specular.py` gives the stitched median.

### Next session — do this BEFORE any qreduce.py change (no speculative fix)
1. Read Mantid `MagnetismReflectometryReduction.cpp` (populated checkout at ~/Projects/Claude/1/mantid,
   `Framework/Reflectometry/`) and find the angle/wavelength-dependent
   normalization between summing the peak and dividing by the direct beam —
   candidate suspects: constant-Q rebinning weighting, a solid-angle/`dQ`
   Jacobian, or a per-pixel `sin`/`cos` factor. The target law must reproduce
   v1/v2 ≈ 0.38/0.31/0.19 at ai = 0.0079/0.0195/0.0483.
2. OR run v2/mr_reduction per-run (needs a Mantid env; heavy — watch OOM on
   8 GB) to get each run's RAW R(Q) and divide by v1's RAW R(Q) to measure the
   exact f(ai) before porting it into `_calc_normal`/`_calc_fan`.
3. Only then change qreduce.py, add a unit test pinning f(ai) for a known
   dataset, and validate ratio→1 on ≥2 datasets per the plan's caution.
