# prompt-31 — remaining work (handoff for the next session)

Snapshot after **Session A (2026-05-22 → 05-24)**, which executed Phase 1 of
`plan/prompt-31-plan.md`. Start a fresh session on this file. Detailed evidence
lives in `plan/prompt-31-load-reduced-data.md` ("Phase 1 update") and the
updated `plan/prompt-31-plan.md` Phase 1 STATUS banner.

## Orchestration (unchanged — re-read before heavy work)
~8 GB RAM machine; OOM (exit 137) kills sessions. **One heavy job at a time**,
launch via background Bash and wait for the completion notification (don't
poll). Prefer `pytest -k <name> --timeout=...`; full `make test-gui` only as a
final gate. GUI click-throughs need a display → hand to the user with a
checklist. **Push policy:** do not push to `code.ornl.gov` (read-only; human-only),
but quicknxsv1's remote is **GitHub**, which is *not* held — its pushes are allowed
(no reflexive idle/handoff pushes). See parent `CLAUDE.md` "Pushing is a human action".

## 1 — Phase 1 specular intensity FIX  (DEFERRED — needs Mantid) ★
Session A **diagnosed** this and deliberately made **no code change** (the
plan's original "replace the hardcoded `0.005`" hypothesis is DISPROVEN).
- quicknxsv2 (`data_set.py:301`), the v2 notebook (`event_reduction.py:70`) and
  the canonical **mr_reduction** (`reflectivity_output.py:99-115`) all apply the
  *identical* `area_ratio · 0.005/sin(θ)` scaling v1 uses → the footprint
  constant is the same on both sides and is **not** the bug. **Do not change it.**
- The real residual is **per-run and angle-correlated, not a constant**:
  median v1/ref ≈ 0.38 / 0.31 / 0.19 (Off_Off) and 0.41 / 0.14 / 0.15 (On_Off)
  at ai = 0.0079 / 0.0195 / 0.0483. So it is not even a clean `f(ai)`.
- It is produced **inside Mantid `MagnetismReflectometryReduction`** (C++, not on
  this machine; Mantid not importable in v1's env).
- **Reproduce:** `pixi run python scripts/diag_specular_decompose.py`.
- **Next steps (before any qreduce.py edit):** read
  `MagnetismReflectometryReduction.cpp` (populated checkout at ~/Projects/Claude/1/mantid,
  `Framework/Reflectometry/`) to find the angle/wavelength term between summing
  the peak and dividing by the direct beam (suspects: constant-Q rebinning
  weight, solid-angle/dQ Jacobian, per-pixel sin/cos); OR run v2/mr_reduction
  per-run (populated checkout at `~/Projects/Claude/1/mr_reduction`, branch
  `next`; needs a Mantid env — heavy, watch OOM) and divide v2 RAW R(Q) by v1
  RAW R(Q) to measure the exact term. Then port into `_calc_normal`/`_calc_fan`,
  add a unit test pinning the term for a known dataset, validate ratio→1 on ≥2
  datasets (`scripts/validate_load_reduced_specular.py`), single commit.

## 2 — Phase 2: `get_xregion` per-DB x-width  (independent of #1)
Add `quicknxs/qcalc.py::get_xregion(data, role)` mirroring `get_yregion`; wire
into `calcReflParams` for **fresh files only**. Unit-test against the v2 header
x_width values 12/16/24 for DB 44033/34/35 (single heavy load or cached
fixtures — OOM). Keep `CalcReflParamsFreshFileReseed` + `RoleDecoupling` green.
**User/display smoke test:** fresh-load 44035 → spinbox `x_width≈24`,
`y_width≈100` regardless of previously-active refl. (prompt-30 AC1)

**STATUS (Session B, 2026-05-24): DONE + numerically validated** (commit
`81363ae`). `get_xregion(data, role)` in `qcalc.py`: `role='db'` = tails
(max/10, like `get_yregion`); `role='refl'` = FWHM (max/2). `calcReflParams`
reseeds `refXWidth` from `get_xregion(data,'db')` on fresh files (hardcoded
`'db'` — `active_role` defaults to `'refl'` and would mis-narrow a fresh DB;
position still from `get_xpos`). Green: `qcalc_test` (18),
`CalcReflParamsFreshFileReseed`+`RoleDecoupling` (7), 34 file/region GUI tests;
`ruff` clean on `quicknxs/`. Headless validation vs v2 headers
(`/tmp/validate_xregion.py`, real DB loads):

| run | v1 x_center | v1 xw(db) | v2 x_pos | v2 x_width |
|---|---|---|---|---|
| 44033 | 227.0 | 8 | 227.0 | 12 |
| 44034 | 229.5 | 13 | 228.5 | 16 |
| 44035 | 231.0 | 22 | 230.5 | 24 |

x_center matches x_pos to ~1px; `xw(db)` is correctly ordered and within ±4px
but **systematically narrow by 2–4px** (FWHM/refl threshold 4/8/17 is far too
narrow — confirms tails is right). The undershoot likely reflects v2's
round-up-pixel / boundary convention; exact parity would need reading v2's
x_width code, not curve-fitting 3 points. Adequate as an auto-seed (AC1 "≈24"
met: fresh 44035 → 22, vs the stale 17 it replaces). **Remaining:** GUI display
smoke test (fresh-load 44035 → spinbox ~22–24) — needs a display; hand to user.

## 3 — Phase 3: prompt-30 Layer 2 hygiene  (small, careful; see prompt-30-remaining.md)
Fresh-file→DB capture in `setNorm`; position-vs-policy split in
`ExtractionRegion`; `changeRegionValues` snapshot-capture; `plotPickX/Y/XY` via
active region; `actionAutoYLimits` per-role. Each needs a user/display smoke test.

**STATUS (Session B, 2026-05-25): clean wins DONE; remainder deferred to the
v1 frontend/backend modularization (user decision).**
- **DONE** `changeRegionValues` snapshot-capture (commit `fb60888`): edits to a
  classified file are recorded into `region_db`/`region_refl`, keyed on the
  file's *actual* role (fresh files skipped, so they can't pollute a role
  region). TDD: 2 `RoleDecoupling` tests.
- **COVERED** `plotPickX/Y/XY`: they set the final spinbox *unguarded*, so a
  drag fires `changeRegionValues` → the snapshot above tracks the region. The
  visual "drag still moves the lines" check wants a display (user).
- **DEFERRED → quicknxsv1-modularization:** (2) fresh→DB capture robustness in
  `setNorm`/`addRefList` (touches the stored `Reflectivity`); (3) position-vs-
  policy split of `ExtractionRegion` (architectural — a known DB should re-fit
  position while keeping role-policy widths); (6) per-role `actionAutoYLimits`
  (largely moot given Fix A's fresh-file Y reseed). Rationale: structural
  concerns the frontend/backend separation will address more cleanly; doing
  them now risks regressions on code that refactor may restructure.

## 4 — Phase 4: off-spec reproduction fidelity vs v2  (after #1)
Re-reduce off-spec at 400 bins (background, one at a time) and compare to
`correctReduction/*OffSpecSmooth*` and `session12/` (coverage, log-I corr,
median ratio); write numbers into `prompt-31-load-reduced-data.md`.
**Note:** `OffSpecular._calc_offspec` applies **no** footprint scale at all
(it normalizes only by the direct-beam `norm.Rraw`), so it is *independent* of
the #1 specular issue; its known discrepancy is bin-density (see prompt-28).

## 5 — Phase 5: pcolormesh non-monotonic warning  (cosmetic, low priority)
`mplwidget.py:311` emits "coordinates not monotonically increasing/decreasing"
on off-spec. Sanitize coords / shading without changing the science.

**STATUS (Session B, 2026-05-25): OBSOLETE on the current stack — reverted.**
Empirically, **matplotlib 3.10.8 does not emit this warning at all**: the
string is absent from its `pcolormesh` source, and both a 2D-gouraud
non-monotonic mesh and a 1D non-monotonic mesh warn zero times. The warning was
removed upstream; the note above was true only on the *older* matplotlib used
before this env moved to 3.10.8. The off-spec Q-grids *are* non-monotonic
(curved — hence gouraud), but that is moot since matplotlib no longer checks.

A `catch_warnings` suppression + file-only breadcrumb was briefly added (commit
`8215df5`) then **reverted** once the above was confirmed: inert on 3.10.8, and
its `simplefilter('always')` risked re-surfacing normally-filtered warnings.
**Kept:** the reusable `gui_logging.QtHandler` `extra={'no_statusbar': True}`
file-only-logging opt-out (+ `QtHandlerStatusbarOptOut` test) for future
sanitization diagnostics that should stay off the shared status bar. **Lesson:**
verify a warning still fires on the *pinned* matplotlib before building
suppression for it.

## Ops / handoff follow-ups
- **quicknxsv1 → GitHub** (allowed): commits `0d72436` and `a1d32e6` (+ this wording
  fix) on `feature/read-event-nexus` are unpushed (`f77204b`, `dfe52eb` already on
  GitHub). GitHub is not held, so these may be pushed — confirm with the user first
  per the no-reflexive-push norm.
- **Parent repo → code.ornl.gov** (HELD, human-only, currently READ-ONLY — see
  `MEMORY.md` → gitlab-readonly): dragonfly commits `aeca94d` (numerical-diagnostics
  caveat) and `b2518ed` + `4242e3f` (push-policy) need to round-trip onto `main` and
  be pushed once code.ornl.gov is writable. Reconcile the duplicate local-only
  commit `ffdcc21` in `~/Projects/Claude/main`.

## Acceptance for "prompt-31 complete"
Specular intensity matches v2 within tolerance on ≥2 datasets (needs #1);
prompt-30 AC1 (`x_width=24`) met (#2/#3); off-spec written up (#4); full
`make test-core` + `make test-gui` green; findings recorded.
