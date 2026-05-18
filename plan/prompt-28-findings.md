# prompt-28: investigation and fixes — findings

## Fault 1 — TOF gaps in off-specular (root cause: chopper speed)

**Root cause.**  `quicknxs/qreduce.py` computed the event-mode TOF window
with the hardcoded half-bandwidth ±1.6 Å:

```
tmin = D_mod_det / (h/m_n) * (λ - 1.6) * 1e-4
tmax = D_mod_det / (h/m_n) * (λ + 1.6) * 1e-4
```

That formula is correct only at the reference chopper speed (60 Hz, frame
period 16.7 ms).  At 30 Hz the frame period doubles to 33.3 ms and so does
the usable bandwidth (±3.2 Å around the central wavelength).  Events whose
TOF fell outside the narrower window were silently dropped by
`MRDataset.bin_events` (`region = (tof_time >= tof_edges[0]) & (tof_time <=
tof_edges[-1])`).

**Symptom in the user's run.** IPTS-34473 / 44159-44161 were taken at 30 Hz,
λ = 5.35 Å.

```
Run 44159  λ=5.35Å  chopper=30Hz  raw events TOF span = [11733, 45067] us  (33.3 ms)
Old window @ 60 Hz: [20144, 37332] us  (17.2 ms)  →  ~50 % events kept
New window @ 30 Hz: [11413, 45386] us  (34.0 ms)  →  100 % events kept
```

The dropped events translate to a missing slab of Qz coverage on the
off-spec plot — visible as the diagonal “zigzag” gap the user reported.

**Fix.**  Introduced `qreduce._compute_tof_range_us(D, λ, chopper_speed,
half_bandwidth=1.6)` that scales the half-bandwidth by
`60 Hz / chopper_speed`.  All four event-mode loaders
(`from_event`, `from_event_h5`, `from_event_h5_filtered`, `from_xml`) call
it instead of inlining the constant.  `chopper_speed` is sourced from the
`SpeedRequest1` DAS log (already collected in `_collect_info_h5`; also
added to the legacy `_collect_info`).

**Verification** (`tests/test_event_h5.py`):
- helper math (60 Hz default, 30 Hz doubles bandwidth, 0 Hz falls back to
  60 Hz)
- IPTS-34473 / 44159 event coverage now = 100 % (was ~50 %)
- visual before/after for run 44161 (highest-tth, most affected) —
  `plan/prompt-28-fix-44161-before-after.png`
- comparison against the v4.3.0rc1 reference smoothed output —
  `plan/prompt-28-fix-vs-correct-40bin.png` (40 bins, ~9 min CPU) and
  `plan/prompt-28-fix-vs-correct-80bin.png` (80 bins, ~12 min CPU).
  The fixed quicknxsv1 output reproduces the same Qz/Qx coverage, the
  same specular streak position, and the same Bragg peak position.
  Median intensity ratio (mine / reference) shifts from 0.45 at 40
  bins to 1.30 at 80 bins; the residual depends on TOF bin count vs
  v4.3.0rc1's default of 400, which changes the smoothing density
  (Gaussian weights accumulate more samples per grid cell) rather
  than the underlying physics.

Reproduce:
```
pixi run python scripts/compare_offspec_44159.py --bins 40 \
  --out /tmp/qnxs_compare/quicknxsv1_OffSpecSmooth_Off_Off.dat
pixi run python scripts/plot_offspec_compare.py \
  --out /tmp/qnxs_compare/offspec_compare.png
```

## Fault 2 — DASLog tab TypeError on `.nxs.h5`

**Root cause.** `_collect_info_h5` stored single-value DAS logs as
`self.logs[motor] = val[0]`.  Modern files keep several string logs
(`BL4A:CS:ITEMS:CanName`, `SampleName`, `DensityUnits`, …) as
`shape (1, 1)` byte arrays.  `val[0]` then produced a 1-element 1-D array,
and `'%g' % data.logs[key]` in `main_gui.update_daslog` raised
`TypeError: only 0-dimensional arrays can be converted to Python scalars`
on the first click of the DASLogs tab.

**Fix.**
- `qreduce._log_scalar(val)` returns `val.flat[0]` so the scalar is
  extracted regardless of ndim.  Used by all four `_collect_info` /
  `_collect_info_h5` sites (REF_M legacy histo, REF_M event, REF_L histo,
  REF_L event).
- Non-numeric time-series (`!issubdtype(val.dtype, number)`) are stored as
  the first scalar rather than via `.mean()`.
- `main_gui._format_log_value(value)` formats with `%g` if numeric, else
  decodes bytes / falls back to `str()`.  `update_daslog` now uses it for
  both the cell text and the tool-tip.

## Fault 3 — `run_state.dat` lost the user's last direct beam / data run

**Two contributing causes.**

1. `HeaderCreator` only wrote a direct beam into the `[Direct Beam Runs]`
   section if at least one entry in `reduction_list` referenced it as
   `normalization`.  44035 never made it because the user had not yet
   attached a refl to it before the GUI crashed.
2. `updateStateFile` was only connected to `initiateReflectivityPlot`, so
   adding a direct beam alone never triggered a save.  44161 didn't make
   it because the user opened the DASLogs tab (→ Fault 2 crash) instead
   of clicking "Add to Reduction" first.

**Fix.**
- `HeaderCreator(refls, extra_norms=...)` — extra direct beams are
  appended to `self.norms` and serialised in `[Direct Beam Runs]` even
  with no refls referencing them.
- `_collect_global_options` handles an empty `self.refls` (falls back to
  the first norm's options or the Reflectivity defaults).
- `HeaderParser._evaluate_section` no longer crashes when a section is
  present but has no column header (empty `[Data Runs]` is now valid).
- `MainGUI.updateStateFile()` passes `list(self.ref_norm.values())` as
  `extra_norms`.
- `setNorm` and `clearNormList` now call `updateStateFile()` so DB-only
  changes are persisted immediately.

Round-tripped via `HeaderCreator → str → HeaderParser` in the unit tests.

## Tests added

`tests/test_event_h5.py` (10 new tests, all pass):

- `TestTofBandwidthChopperScaling` (4) — helper math + IPTS-34473 coverage
- `TestLogScalarExtraction` (4) — scalars from 1-D/2-D/bytes; string log
  end-to-end via `_format_log_value`
- `TestHeaderCreatorExtraNorms` (2) — `extra_norms` serialisation,
  DB-only state file round-trip

Existing suites unaffected: `qio_test` (22/22), `qcalc_test` (13/13),
46 of `test_event_h5` (10 network-skipped on this machine).

## Tooling

- `scripts/compare_offspec_44159.py` — headless reduction of 44033/4/5 +
  44159/60/61 → `OffSpecSmooth_Off_Off.dat` for diffing against the
  v4.3.0rc1 reference at
  `/SNS/users/6ov/shared/REF_M/11486/correctReduction/`.
- `scripts/plot_offspec_compare.py` — side-by-side log-pcolormesh of two
  `OffSpecSmooth` `.dat` files with a ratio panel.
