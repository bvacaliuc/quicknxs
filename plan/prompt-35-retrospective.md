# prompt-35 — retrospective (autonomous session 2026-06-02)

The user instructed me to execute the revised `plan/prompt-35-todo.md` to
completion while they are away from the workstation. Where the plan asked
for a choice, I am to use my recommended option AND record the choice plus
my reasoning here so the user can review it later.

This file is written incrementally; each section below is added as the
corresponding task completes.

## Session inputs

- Repository branch: `feature/read-event-nexus` (quicknxsv1)
- Starting HEAD: `8ba70f0 bump quicknxsv1 rev to prompt 35`
- Prior session findings: `plan/prompt-35-todo.md` (revised 2026-06-02)
- User-provided artifacts: `~/shared/REF_M/QuickNXSv1/prompt34/**`
  (screenshots, `.tar.gz` of `~/.quicknxs`, reduced .dat files)

## Choices made

### T1 — clear+reload stale `ref_norm` fix

**Decision:** add `self.clearNormList()` immediately after the existing
`self.clearRefList(do_plot=False)` at the top of `MainGUI.loadExtraction`
(`quicknxs/main_gui.py:1591`).  No change to `clearRefList` itself.

**Why this approach over the alternatives I considered:**

| option | what it does | accept? |
|---|---|---|
| A. clear in `loadExtraction` only (CHOSEN) | reload is a full state reset | ✅ minimal, matches user mental model "Load = replace" |
| B. clear in `clearRefList` (the trashcan) | trashcan wipes both refls and DBs | ❌ breaks the incremental "clear refls, add new refls, reuse DBs" workflow |
| C. add a `force=True` to `setNorm` so it overwrites | reload re-populates correctly without explicit clear | ⚠️ scattered semantic change; harder to reason about |

A is the smallest change that fixes the bug, leaves the trashcan's existing
semantic alone, and is exactly the behavior a user expects from
"Load Extraction" — replace state from the file.

**Regression test** (added in
`tests/main_gui_test.py::LoadExtractionRoundTrip::test_load_extraction_clears_stale_norms_on_reload`):
generates a reduced .dat, loads it, captures the IDs of `ref_norm` values,
trashcan-clears, reloads the same file, asserts that no object identity
from the first load survives in `ref_norm` after the reload. This is the
strongest invariant — even if `bins` were the same, the user's expectation
is that Load Extraction replaces, not preserves, the prior load's
normalization objects.

**Tests run:**
- `tests/main_gui_test.py::LoadExtractionRoundTrip` — 5 passed (incl. the new test)
- `tests/main_gui_test.py::MainGUIReductionActions` — 7 passed (no regressions)

### T4 — Smoothing dialog Y1 ≥ 0 clamp

**Decision:** in `SmoothDialog.drawPlot` (`quicknxs/gui_utils.py:683`),
clamp the seeded `y1 = max(0.0, y1)` **only** in the (ki_z-kf_z)-vs-Qz
and Qx-vs-Qz modes (where the y axis is Qz, non-physical for Qz < 0).
The (ki_z, kf_z) mode is left alone — kf_z can legitimately straddle
zero (specular ridge near kf_z=0).

**Why this is conservative**: the only data the clamp affects is
non-physical negative-Qz noise at the lowest-angle run's band edge.
The user has been manually clamping Y1→0 every reduce (visible in
`quicknxs-offspecular-smoothing-options-000525-take2.png`); this just
makes the default what they do anyway.

**Regression test** (added in
`tests/main_gui_test.py::SmoothDialogYClamp`):
- builds a small synthetic OffSpec data array with Qz crossing zero
  (-0.05 → 0.40) and kf_z crossing zero (-0.15 → 0.38),
- opens SmoothDialog in each of the three modes (kizmkfz, qxqz, kizkfz),
- asserts Y1 ≥ 0 in the Qz-y modes and Y1 < 0 (allowed) in the kf_z-y mode.

The test's ki_z is **varied along the Ny axis** (not constant) so the
(ki_z, kf_z) mode does not trigger the `x_max <= x_min` degenerate-extent
fallback (which would seed y_min=0 regardless and obscure the clamp).

**Tests run:**
- `tests/main_gui_test.py::SmoothDialogYClamp` — 3 passed

### T2 part 1 — TOF-binning coverage documentation

**Decision:** create `plan/tof-binning-and-offspec-coverage.md` capturing
the bin-invariance / coverage / integrated-intensity nuance. Reference
the comparison script (`plan/scripts/prompt-35/compare_tof_binning.py`)
and the produced metrics (median ratio 0.93 on a common (Qx, Qz) grid;
no cells are lost only at TOF=400, 623 cells lost only at TOF=40).
This addresses the user's request to **document for future sessions**
so we never re-investigate this.

No code change.

### T2 part 2 — shading change experiment

**Decision: KEEP `shading='gouraud'`.** The experiment shows that
`shading='nearest'` produces **the same** visible gaps at TOF=40 as
`gouraud` does. The gaps are not a shading artifact — they are the
physical Qz region between two runs' bands that neither run measured.

**Evidence:** `plan/scripts/prompt-35/render_offspec_shading.py` renders
the user's TOF=40 .dat (and TOF=400 .dat) with three shading modes
side-by-side; the artifacts are:

- `/tmp/render-shading-tof40.png` — gouraud and nearest both show the
  same horizontal gap between the lowest-angle and middle-angle runs
- `/tmp/render-shading-tof400.png` — gouraud and nearest both show
  continuous coverage, no gaps in either shading

So changing the default would not improve the user's experience, and
the visually-smoother `gouraud` is still the right choice for dense
plots.

**The actual mitigation** for the user's complaint is:
1. Document the "use bins=400 for clean off-spec preview" guidance
   (now captured in `plan/tof-binning-and-offspec-coverage.md`).
2. Optionally pre-smooth the preview onto a regular (Qx, Qz) grid
   in `plot_offspec` — deferred, design discussion needed.

No code change for T2 part 2 — only the experiment record above.

