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
checklist. **Pushes are now human-only** (commit, then tell the user what's
ready — see parent `CLAUDE.md` "Pushing is a human action").

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
  `MagnetismReflectometryReduction.cpp` (mantidproject/mantid,
  `Framework/Reflectometry/`) to find the angle/wavelength term between summing
  the peak and dividing by the direct beam (suspects: constant-Q rebinning
  weight, solid-angle/dQ Jacobian, per-pixel sin/cos); OR run v2/mr_reduction
  per-run (populated checkout at `~/Projects/Claude/2/mr_reduction`, branch
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

## 3 — Phase 3: prompt-30 Layer 2 hygiene  (small, careful; see prompt-30-remaining.md)
Fresh-file→DB capture in `setNorm`; position-vs-policy split in
`ExtractionRegion`; `changeRegionValues` snapshot-capture; `plotPickX/Y/XY` via
active region; `actionAutoYLimits` per-role. Each needs a user/display smoke test.

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

## Ops / handoff follow-ups (HUMAN — not quicknxs code)
- **Push pending commits.** Per the new human-push policy, Session A left commits
  unpushed: this session's `plan/prompt-31-remaining.md` (+ any new quicknxsv1
  commits) on `feature/read-event-nexus`. Earlier Phase 1 commits (`f77204b`,
  `dfe52eb`) were already on GitHub.
- **Round-trip to `main` + push** (only when `code.ornl.gov` is writable again —
  it is currently READ-ONLY, see `MEMORY.md` → gitlab-readonly): dragonfly
  commits `aeca94d` (numerical-diagnostics caveat) and `b2518ed` (push-policy)
  need to land on `main`. Reconcile the duplicate local-only commit `ffdcc21`
  in `~/Projects/Claude/main`.

## Acceptance for "prompt-31 complete"
Specular intensity matches v2 within tolerance on ≥2 datasets (needs #1);
prompt-30 AC1 (`x_width=24`) met (#2/#3); off-spec written up (#4); full
`make test-core` + `make test-gui` green; findings recorded.
