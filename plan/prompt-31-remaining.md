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

**STATUS (Session B, 2026-05-26): DONE — v1 reproduces v2's off-spec STRUCTURE;
the intensity carries the #1 scaling gap.** Re-reduced 44159+44160+44161
headless (`reduce_offspec_headless.py`, **corrected paired DBs**
44159↔44033 / 44160↔44034 / 44161↔44035, bins=400) on the reference's 563×1000
grid and compared via `plot_offspec_compare.py` to the v2 reference
(`session13/..._peak1_OffSpecSmooth_Off_Off-correct-db-id.dat`, QuickNXS
4.3.0rc1 / Mantid 6.12.0).

- **Shape: strong agreement** — log-Pearson 0.87 overall, **0.96 on the specular
  stripe**, 0.85 off-spec; Qz=0.05/0.15/0.30 line cuts match in shape. The
  non-Mantid off-spec geometry is sound.
- **Magnitude: v1 systematically lower** — median ratio (v1/v2) **0.26**
  off-spec, **0.43** specular stripe, **0.61** integrated. v1 ≈ ¼–½ of v2,
  region-dependent.
- **Matches the #1 specular gap** (Off_Off v1/ref ≈ 0.38/0.31/0.19, angle-
  correlated): specular-stripe 0.43 ≈ the low-angle 0.38, and the ratio falls
  with Qz/angle just as #1 does. **This revises the "independent of #1" note
  above** — the off-spec deficit is the *same* angle-dependent v1-vs-Mantid
  scaling, not a separate bin-density effect, so it is **Mantid-blocked like #1**
  (root cause inside `MagnetismReflectometryReduction`, not diagnosable without
  Mantid here). Smoothing σ (0.0005, unrecorded in the ref) cannot cause a scale
  gap (Gaussian smoothing conserves total), so σ is not the cause; peak
  Δ=(−0.074, +0.105) is argmax noise from the relatively-suppressed specular,
  not a geometry error.

Artifacts in `session13/`: `v1-vs-v2-offspec-compare.png`,
`v1-vs-v2-offspec-metrics.json`,
`REF_M_44159+44160+44161_OffSpecSmooth_Off_Off-v1-paired-tof400.dat`.

**CORRECTION + On_Off extension (2026-05-26, later).** The Off_Off result above
compared v1 **paired** DBs against a reference whose data is actually
**single-DB**: the session13 `-correct-db-id` file is byte-identical to the buggy
`correctReduction` Off_Off — only the header DB_ID was relabeled 1→1/2/3, the data
was **not** re-reduced (both v2 reference headers carry DB_ID=1/1/1). So that
comparison mixed the DB-association difference into the ratio. Re-ran **matched**
(v1 single, all→44033) for both channels; v1-paired served as a control and
**confirmed the references are single-DB** (paired total matched worse: On_Off
integrated 0.53 vs single 0.91; Off_Off 0.61 vs 1.35).

Clean v1-vs-v2 (both single-DB, bins=400):

| metric (v1/v2) | Off_Off | On_Off |
|---|---|---|
| log-Pearson overall | 0.870 | 0.860 |
| log-Pearson specular | 0.947 | 0.944 |
| log-Pearson off-spec | 0.850 | 0.840 |
| median ratio (overall) | 0.154 | 0.175 |
| specular median ratio | 0.246 | 0.276 |
| off-spec median ratio | 0.148 | 0.168 |
| integrated ratio | 1.35 | 0.91 |

**Conclusions (both channels):** (1) **structure is faithful** — log-Pearson
0.86–0.95; On_Off behaves like Off_Off, so the non-Mantid off-spec geometry is
sound for the spin-flip channel too. (2) **per-pixel intensity ≈ 0.15–0.28× v2**
across the map — the same angle-dependent v1-vs-Mantid scaling as #1, now
confirmed in **both** polarization channels (Mantid-blocked). (3) A **localized
bright feature in v1's low-angle 44159** (raw I≈25 vs ≈3–9 for 44160/61,
db-independent) inflates the integral (integrated 0.9–1.35 despite low median) and
drives the peak-location metric — distinct from the broad scaling; worth a
separate look (possible low-angle normalization artifact). σ=0.0005 cannot cause a
scale gap.

Artifacts in `session13/`: `v1-vs-v2-offspec-{Off_Off-single,On_Off-single,
On_Off-paired}-compare.{png,json}` and
`REF_M_..._OffSpecSmooth_{Off_Off,On_Off}-v1-{single,paired}-tof400.dat`.

**44159 bright feature — DIAGNOSED (2026-05-26): a 1/Rraw normalization artifact,
not physical.** v1's 44159 off-spec max (I≈25.6) is a **single pixel** (x_pix=117,
tof_bin=16, λ=2.41 Å; only 1 pixel >10 and 2 >5 of 121,600), at a wavelength in
the **direct-beam spectrum's low-flux tail where `norm.Rraw`≈1.5e-15** (44033
Rraw peak 6.8e-11; 21 bins <1e-13). `OffSpecular._calc_offspec`
(`qreduce.py:3316-3321`) guards with `idxs = norm.Rraw > 0.` then
`self.S[:, idxs] /= norm.Rraw[idxs]` — `>0.` admits tiny-positive Rraw, so a small
off-spec count ÷ 1.5e-15 blows up (exact-zero bins are already masked to 0 at
3322). Same `Rraw>0` guard in `_calc_reflectivity` (2938) and `_calc_fan` (3015).
**Separate from the broad ~0.2× #1 scaling**; this is what inflates the off-spec
integrated ratio (0.9–1.35) and drives the peak-Δ metric. **Proposed fix:** raise
the guard to a relative floor, `idxs = norm.Rraw > frac*norm.Rraw.max()`
(frac≈1e-3 masks the artifact at ~2e-5 of peak while keeping real data); excluded
bins already fall through to the existing `S=0` mask. Pending decision (science-
output change; optional Mantid cross-check of the masked band).

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
