# prompt-35 — UI usability + freeze diagnosis + v4.x comparison (revised 2026-06-02)

This revision folds the original 2026-05-30 live-test feedback into the
investigation findings from 2026-06-02. Sections marked **CARRY-FORWARD** are
unchanged from the previous version (with status updates). Sections marked
**NEW** were added after the 2026-06-02 session's three new findings:

  1. **TOF-bin coverage artifact**: at `bins=40` the off-spec preview shows
     visible (Qz) gaps that disappear at `bins=400`. The PER-CELL intensity
     is bin-invariant (median ratio 0.93 between the two, IQR 0.78–1.09 on
     a common Cartesian (Qx, Qz) grid) — the difference is COVERAGE, not
     calibration. See `plan/scripts/prompt-35/compare_tof_binning.py` and
     `/tmp/compare-tof-binning-OffSpec-Off_Off.png`.
  2. **Clear+reload stale-state bug**: `clearRefList` (trashcan) does NOT
     clear `self.ref_norm`. `loadExtraction → setNorm(do_remove=False)`
     does nothing if the entry already exists, so the OLD direct-beam
     `Reflectivity` (at the OLD bin count) survives a reload. Downstream,
     `getNorm()` checks `len(norm.Rraw) == len(data.tof)` — at mismatched
     bin counts this fails silently and the **xtof_overview** is rendered
     un-normalized, which is the visible difference between
     `quicknxsv1-overview-tof-400-clear-and-reload.png` and
     `quicknxsv1-overview-tof-400-clean-load-extraction.png`.
  3. **Off-spec smoothing defaults**: 5% inset of the I>0 data extent;
     σ = 0.005 × X-span (coupled in kizmkfz / kiz modes); grid = √2 × span/σ.
     Documented at `plan/offspec-smoothing-defaults.md`. The user typically
     tunes σ to ~0.0005 and clamps Y1 ≥ 0; the latter is an obvious default
     improvement.

The previous session's RESOLVED items (N1 BG-X consolidation, N2 flux-floor
placement, N5 smoothing colormap, N6 reduction-engine deficit) are kept in
this file as a record but are not actionable any more.

----

## NEW T1 — clear+reload reuses stale `ref_norm` (HIGH PRIORITY, simple fix)

**Bug**: in `main_gui.py`:
- `clearRefList` only resets `reduction_list` and the reduction table; it does
  NOT reset `self.ref_norm` or the normalize table.
- `loadExtraction` calls `setNorm(do_plot=False, do_remove=False)` for each
  parsed norm. `setNorm` is structured as `if number not in ref_norm: ADD`
  / `elif do_remove: REMOVE`; with `do_remove=False` and the number already
  in `ref_norm`, the branch falls through silently — the new Reflectivity
  object never replaces the stale one.
- Therefore, after `trashcan → change tof bins → re-load extraction`, the
  user's `self.ref_norm` still holds Reflectivity objects bound to the OLD
  bin count.
- `getNorm()` then sees `len(norm.Rraw) != len(data.tof)` and returns None
  → `plot_overview` skips the normalize-by-direct-beam step → xtof_overview
  is rendered un-normalized in the clear+reload session but normalized in
  the fresh-session baseline (where `ref_norm` was just populated at the
  current bin count).

**Fix** (recommended approach): clear `ref_norm` at the top of `loadExtraction`
**before** parser-populated norms are added.

```python
def loadExtraction(self, filename=None):
    ...
    with self.busy(u'Loading extraction...'):
      self.clearRefList(do_plot=False)
      self.clearNormList()                # NEW — load is full replacement
      ...
```

`clearNormList()` already exists (`main_gui.py:2070`) and properly resets
`ref_norm`, the normalize table widget, and the normalize label. It also
calls `updateStateFile()`, so the saved `run_state.dat` reflects the cleared
state.

**Rationale for fix-at-loadExtraction (not fix-at-clearRefList)**:
- The trashcan icon's *current* semantic is "clear refls, keep DBs" — a
  user adding new refls without reloading DBs depends on it.
- Load Extraction's semantic is "completely replace state from a file" —
  it's reasonable (and currently the user's expectation) that this wipes
  any prior in-memory state.

**Test**: after the fix, repeat the user's failing scenario:
  1. Open quicknxsv1, set TOF bins = 40, Load Extraction
  2. Trashcan to clear refl list
  3. Set TOF bins = 400, Load Extraction (same file)
  Expected: overview xtof is normalized identically to a fresh-session load
  at TOF=400.

**Acceptance**: a regression test that:
- Mocks the loadExtraction header parsing,
- Simulates the trashcan-then-reload-different-bins flow,
- Asserts `len(ref_norm[number].Rraw) == len(active_data.tof)` after
  the reload (the previously-failing invariant).

----

## NEW T2 — TOF-bin coverage gap is a real sampling artifact (DOCUMENT + fix preview)

**Finding**: the user's expectation that "TOF bin count is purely statistical
and must not alter data" is **partially correct**:

- The per-cell intensity is bin-invariant (median ratio 0.93 on the common
  Cartesian (Qx, Qz) grid; the spread is the discretization noise, not a
  reduction error).
- But the OUTPUT .dat file is a list of bin samples, NOT a 2D histogram.
  At bins=40 we have 24,016 rows over the (Qx, Qz) plane; at bins=400 we
  have 351,424 rows. Total intensity scales with bin count because each
  row is intensity *per bin*, not *per unit area*.
- Therefore at coarse bins the per-run band is sampled with fewer points
  in the Qz direction. On a fine pcolormesh, neighboring runs' bands have
  a visible gap between their sampled points.

This is a **sampling/visualization** effect, not a reduction bug.

**Mitigations** (recommend doing 1 and 2 this session; 3 is deferred):

1. **Document** — add the bin-invariance finding and the coverage caveat
   to `plan/v1-vs-mantid-deficit-rootcause.md` (or create a new
   `plan/tof-binning-and-offspec-coverage.md`) so future sessions don't
   re-investigate. Reference the comparison script and the PNG artifact.

2. **Off-spec preview shading change**: `plot_offspec` currently uses
   `shading='gouraud'`. With sparse vertices, `gouraud` interpolates between
   them and masked cells (S = 0) appear as visible holes. **Test**
   `shading='nearest'` (fill cells edge-to-edge with the bottom-left
   vertex's value) on a small dataset and visually compare the bins=40
   gap appearance. If it's better, switch the default. If it's worse,
   keep gouraud and just document.

   Note: the smoothing dialog (`SmoothDialog.drawPlot`, `gui_utils.py:736`)
   also uses `gouraud`; harmonize the choice with the preview.

3. **Deferred**: persist the preview view onto a regular (Qx, Qz) Cartesian
   grid (interpolation + masking), so the rendered image is bin-invariant.
   This is what the smoothing dialog already does for the *output*, so the
   infrastructure exists in `qcalc.smooth_data`. Cost: one more grid build
   per preview = more latency; ties to N4 speed-up below.

----

## NEW T3 — Smoothing defaults documentation (DONE in this revision)

`plan/offspec-smoothing-defaults.md` now captures the deterministic rule
(`SmoothDialog.drawPlot`, `gui_utils.py:683`): 5% inset of the I>0 data
extent for the region box, σ = 0.005 × X-span floored at 1e-4 Å⁻¹, grid =
√2 × (span / σ). Includes a worked example from the user's 44159+44160+44161
reduction at TOF=400.

----

## NEW T4 — Smoothing dialog Y1 default should be ≥ 0 (small fix)

The off-spec preview at low-angle runs emits sample points slightly into
negative Qz at the band edges (artifact: noise). The smoothing dialog seeds
`gridYmin` from `y_min - 5% × (y_max - y_min)` = the data extent minus a
small inset — typically negative for the lowest-angle run. The user has to
manually clamp Y1 to 0 every reduce.

**Fix**: in `SmoothDialog.drawPlot` (`gui_utils.py:683`), after computing
`y1` and before `self.ui.gridYmin.setValue(y1)`, clamp:

```python
y1 = max(0.0, y1)
```

(only when the y axis represents Qz — i.e. NOT in the `ki_z vs kf_z` mode).

**Acceptance**: open Smooth dialog on the user's 44159+44160+44161
extraction; Y1 should now seed at 0.0 instead of -0.0297.

----

## CARRY-FORWARD N4 — UI freeze diagnostics (PARTIAL FIX 2026-05-30; remaining work)

- Off-spec preview wrapper `_replotOffspec` now uses `self.busy(...)`. The
  spinbox feedback is instant.
- **Remaining:**
  - **Coalesce `valueChanged`** on `_offspecFluxFloor` so spinning the
    spinbox does not queue multiple 30 s off-spec recomputes. Replace the
    direct `_offspecFluxFloor.valueChanged.connect(self._replotOffspec)`
    with a debounced wrapper (QTimer 300 ms single-shot reset on each
    value change, fire when the timer expires).
  - **Speed up `plot_offspec`** by caching per-run `OffSpecular` results
    keyed on `(file, channel, item.options)` until inputs change. The
    current code re-loads + re-extracts on every preview. (Deferred — needs
    more design.)
  - **Reduction-dialog → statusbar progress**: the export/reduce path
    blocks the statusbar at "Opening reduction dialog…" for the entire
    109 s of the reduce loop. Wire one statusbar message per file/channel
    out of `Reducer.execute`.
  - **Overview-tab switch 30 s freeze**: gather a reproducible timestamp,
    trace which slot ran. Almost certainly a `plotActiveTab` path missing
    a `busy()` wrapper. (Defer until reproducible.)

## CARRY-FORWARD N5 — Off-spec preview start-up rendering (still open)

- Colormap unification: **FIXED 2026-05-30**.
- **Intensity scale / axes**: the off-spec preview still starts clipped
  to whatever `offspecImin`/`offspecImax` the user left in the spinboxes.
  The smoothing dialog auto-fits. The user wants the **preview to also
  auto-fit on first plot** (and on reduction-list change), then honor
  user-set bounds only after explicit "Clip" / spinbox adjustment.
- **σ default coupling and anisotropy** — captured in
  `plan/offspec-smoothing-defaults.md` "What might be worth changing"
  section. Deferred.

## CARRY-FORWARD N6 — v4.17.0rc5 vs v4.3.0rc1 comparison

- `correctReduction` is the v4.3.0rc1 baseline; v1 now matches at median 1.067
  per `plan/v1-vs-mantid-deficit-rootcause.md`. With the user's 2026-06-02
  paired+flux-floor+BG-off run at TOF=400, the comparison is at median ratio
  1.07 (specular 1.06, off-spec 1.07), log-Pearson 0.90; effectively matched.
- **v4.17.0rc5 reference NOT YET AVAILABLE** — without an OffSpecSmooth output
  produced by that version, we can only match v4.3.0rc1. If/when the user
  provides a v4.17.0rc5 reference, re-run `scripts/plot_offspec_compare.py`
  and identify which knob (σ, band, scale, smoothing) drives the residual.
- **No action this session** — pending user input.

----

## Implementation order (this session, recommended)

Each item below has a clear scope and acceptance criterion. I will execute
1–6 in order, log each choice in `plan/prompt-35-retrospective.md`, and
commit after each logical change (per CLAUDE.md "commit freely").

1. **T1** — clear+reload stale `ref_norm` fix. Single-line addition in
   `loadExtraction`. Smallest, highest-impact.
2. **T4** — Smoothing dialog Y1 ≥ 0 clamp. Single-line addition. Low risk.
3. **T2 part 1** — document TOF-binning bin-invariance finding in a new
   `plan/tof-binning-and-offspec-coverage.md`. Reference the comparison
   script and PNG. No code change.
4. **T2 part 2** — off-spec preview `shading='nearest'` experiment. If the
   gap appearance improves on bins=40, switch the default; if not, document
   the decision and keep `gouraud`.
5. **N5 (intensity scale auto-fit)** — auto-fit `offspecImin`/`offspecImax`
   to the data on first plot and after reduction-list change; mark
   "fitted" state so user-set bounds win once they edit the spinboxes.
6. **N4 (flux-floor debounce)** — debounce `_offspecFluxFloor.valueChanged`
   via QTimer 300 ms single-shot. Acceptance: turning the spinbox repeatedly
   coalesces into a single replot ≈ 300 ms after the last change.

Deferred to a future session (out of this prompt's scope):
- N4 plot_offspec speed-up (caching design).
- N4 reduction-dialog statusbar updates (needs API design).
- N4 Overview-tab switch 30 s freeze (needs reproducible trace).
- N5 σ default coupling change.
- N6 v4.17.0rc5 comparison (no reference data yet).
- T2 part 3 (preview as regular grid) — design discussion needed.

## Retrospective document

`plan/prompt-35-retrospective.md` (created during execution) records every
choice this session made under autonomous operation, with the rationale
the user can review later.
