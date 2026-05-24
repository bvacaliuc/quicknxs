# prompt-31 plan — remaining quicknxsv1 reduction-fidelity & role work

A clean-session, **multi-agent** plan for the work left after the
Load-Reduced-Data / prompt-30 / exit-SIGSEGV sessions. Start a fresh session
on this file. Sources consolidated here: `plan/prompt-30-remaining.md`
(role decoupling Layer 2) and `plan/prompt-31-load-reduced-data.md`
(v2 reproduction fidelity).

## Already DONE (do not redo — see git log on feature/read-event-nexus)
- Parse v2 `.dat` (`[Global Options]` fix) — Load Extraction works on all 7
  `correctReduction/*.dat`.
- prompt-30 **Layer 1**: `ExtractionRegion`, `region_db`/`region_refl`/
  `active_role`, role-switch `_applyRoleRegion`, capture in setNorm/addRefList,
  loadExtraction seeds both regions. (`RoleDecoupling` tests pass.)
- Off-spec "missing data" → **honor `eventTofBins` on Load Extraction**
  (cap raised to 1000); set bins=400 to match v2. Verified: gap band coverage
  79%→100%, intensity ~30×.
- **Exit SIGSEGV** → dialogs disposed via `deleteLater()`, not `destroy()`
  (6 sites). `WidgetDisposalSafety` test guards it. Verified clean.
- Specular load+reproduce shape correlation 0.96–0.97 vs v2.

## Reference data & tooling (all on this machine)
- v2 "correct" outputs: `/SNS/users/6ov/shared/REF_M/11486/correctReduction/`
  (also rsync'd local: `/home/bvacaliuc/shared/REF_M/11486/...` — faster, the
  sshfs `/SNS/` is a 50 Mbps link). DB 44033/34/35, data 44159/60/61, IPTS-34473.
- `session12/` = quicknxsv2-today output (now present locally); `session13/` =
  our quicknxsv1 output from the last GUI test.
- Scripts: `scripts/validate_load_reduced_specular.py` (--bins; HeaderParser
  load-path R(Qz) vs reference), `scripts/reduce_offspec_headless.py`
  (--bins/--no-smooth/--grid-nx,-ny; off-spec, own recipe parser),
  `scripts/compare_offspec_44159.py`, `scripts/plot_offspec_compare.py`.
- `make gdb` for native backtraces; `make strace*` for memory traces.

## Orchestration rules (READ FIRST — context / OOM / token budget)

This machine is ~8 GB RAM with ~3–4 GB free during a GUI/test session; OOM
(exit 137) kills sessions. Apply `CLAUDE.md` OOM + Knowledge-Routing rules.

1. **One heavy job at a time.** Off-spec smoothing and multi-file reductions
   load ~600 MB + large arrays. **Never run two concurrently.** Launch each via
   background Bash (`run_in_background: true`) and **wait for the completion
   notification — do not poll/sleep.** Do other *light* work meanwhile.
2. **Delegate read-heavy investigation to `Explore` subagents** (e.g. "how does
   v2 compute the beam footprint"). Subagents return a concise report, keeping
   the orchestrator's context lean. Use a `general-purpose` subagent for a
   self-contained implementation phase if the orchestrator is >60% context.
   Brief each subagent fully (it starts cold): goal, files, what to return.
3. **Checkpoint after every phase:** run the relevant tests, commit + push,
   and tick the phase box in this file. Commits are the cross-session/-machine
   handoff (git is the only durable channel — `MEMORY.md` is machine-local).
4. **Token limits → hand off, don't cram.** Each phase below is sized for ~one
   session. If context passes ~75%, finish the current step, commit, update
   this plan, and **start a new session at the next unchecked phase.** This
   file is the handoff; no state needs to live in chat.
5. **Tests:** prefer `pytest -k <name> --timeout=...` for the targeted subset;
   run the full `make test-gui` (~3 min) only as the phase's final gate. The
   GUI suite needs `QT_QPA_PLATFORM=offscreen` (conftest sets it).
6. **Interactive GUI checks need a display** — the agent cannot do them
   headless. Where a phase needs one, prepare it and **hand the click-through
   to the user** with an explicit checklist.

## Phases (rough priority order; 1 & 3 are independent and may interleave)

### Phase 1 — Specular intensity discrepancy  ★ highest value
> **STATUS 2026-05-22 (Session A): hypothesis DISPROVEN — do NOT change the
> `0.005` footprint.** Full evidence in `plan/prompt-31-load-reduced-data.md`
> ("Phase 1 update"). Summary:
> - quicknxsv2 (`data_set.py:297-302`), the v2 notebook (`event_reduction.py:64`)
>   and the canonical **mr_reduction** (`reflectivity_output.py:99-115`) ALL use
>   the *same* `area_ratio · 0.005/sin(θ)` scaling v1 uses, applied *after*
>   Mantid. The footprint constant is identical on both sides → not the bug.
> - The real discrepancy is **angle-correlated and per-run, not a global
>   constant**: median v1/ref ≈ 0.38 / 0.31 / 0.19 at ai = 0.0079 / 0.0195 /
>   0.0483 (same DB, same ROI area, same scale for 159/160). Within a run it is
>   a clean constant (44159 plateau steady at ~0.38). Reproduce:
>   `pixi run python scripts/diag_specular_decompose.py`.
> - The angle-dependent term lives inside Mantid `MagnetismReflectometryReduction`
>   (C++, **not on this machine**; Mantid not importable in v1's env).

**Original (incorrect) problem statement, kept for history.** quicknxsv1
specular R was thought to be a *constant* ~3.2× dimmer than v2 due to the
hardcoded `sin_scale = 0.005 / sin(self.ai)` at `qreduce.py` ~2929
(`_calc_normal`) and ~3010 (`_calc_fan` — NOT `OffSpecular`; `_calc_offspec`
applies no footprint at all). That ~3.2× was a stitched-curve *median*; the
underlying offset is actually angle-dependent (see above).

**Steps**
- [x] *(Explore subagent)* Determine how v2 / Mantid normalizes the footprint.
  **Result:** identical `0.005/sin(θ)` + ROI-area ratio on both sides (triple
  confirmed). The footprint is not the differentiator.
- [x] Decompose per-run to localize the true offset. **Result:** angle-correlated
  per-run residual (0.38/0.31/0.19), localized to Mantid's C++ algorithm.
  Added `scripts/diag_specular_decompose.py`; findings written up.
- [ ] **(Next session, needs Mantid)** Characterize the exact angle law f(ai)
  the reference carries — by reading `MagnetismReflectometryReduction.cpp`
  (populated checkout at ~/Projects/Claude/1/mantid `Framework/Reflectometry/`) OR running v2/mr_reduction
  per-run to divide v2 RAW R(Q) by v1 RAW R(Q). Target: reproduce 0.38/0.31/0.19.
- [ ] Only after f(ai) is understood: port it into `_calc_normal`/`_calc_fan`,
  add a unit test pinning f(ai) for a known dataset, validate ratio→1 on ≥2
  datasets. **Caution:** changes absolute intensity of every reduction; single
  well-documented commit; `make test-core`/`test-gui`.
**Done when:** specular ratio ≈1 on 44159–61 and ≥1 other dataset, all tests
pass — **deferred**; this session delivered the diagnosis + handoff only.

### Phase 2 — `get_xregion` per-DB x-width (prompt-30 AC1)
**Problem.** Fresh direct beams inherit the previous (refl) `x_width`;
`calcReflParams` auto-fits only `x_pos` (CWT) and `y` (`get_yregion`), never
`x_width`. The three DBs have distinct widths (44033=12, 44034=16, 44035=24).
**Steps**
- [ ] Add `quicknxs/qcalc.py::get_xregion(data, role)` (mirror `get_yregion`)
  returning a role-appropriate `x_width` from the x-projection (DB = full beam
  FWHM/tails; refl = narrower). Unit-test its output against the v2 header
  values 12/16/24 for 44033/34/35 (load via local rsync path; **single heavy
  load, or use cached fixtures** to avoid OOM).
- [ ] Wire into `calcReflParams` for **fresh** files only (mirror the Fix-A
  `get_yregion` branch); known files keep stored region. Keep
  `CalcReflParamsFreshFileReseed` + `RoleDecoupling` green.
- [ ] *(User, display)* Smoke test: fresh-load 44035 → spinbox `x_width≈24`,
  `y_width≈100` regardless of previously-active refl.
**Done when:** AC1 met (fresh 44035 → x_width≈24/y_width≈100); tests pass.

### Phase 3 — prompt-30 Layer 2 hygiene (independent of Phase 1)
From `plan/prompt-30-remaining.md`; each is small but needs care + a smoke test.
- [ ] **Fresh-file→DB capture:** `setNorm` invoked while `active_role=='refl'`
  should switch to db role and capture DB-role widths, not on-screen refl
  widths (depends on Phase 2's `get_xregion`).
- [ ] **Position vs policy split** in `ExtractionRegion` (per-file position
  `x_pos`/`y_pos`/`y_width` vs per-role policy `x_width`/`bg_*`/`scale`) — decide
  with Phase 2.
- [ ] **`changeRegionValues` capture** (snapshot spinboxes → active role's
  region) so a same-role reload preserves edits. Hot path — guard, snapshot
  only, no control-flow change.
- [ ] **Mouse handlers** `plotPickX/Y/XY` route through the active region.
- [ ] **`actionAutoYLimits` per-role** (or implicit "DB re-fits Y, refl freezes
  after first add").
- [ ] *(User, display)* Full smoke test from `prompt-30-decouple-db-refl-ui.md`
  step 4 (load 3 DBs + 3 refls, reload 44035→wide, 44161→narrow, save/restore).
**Done when:** the prompt-30 acceptance criteria all hold + smoke test clean.

### Phase 4 — Off-spec reproduction fidelity vs v2 (after Phase 1)
- [ ] After the footprint fix, re-reduce off-spec at 400 bins (background, one
  at a time) and compare to `correctReduction/*OffSpecSmooth*` **and**
  `session12/` — coverage, log-intensity correlation, median ratio. Use the
  existing compare scripts; write the numbers into `prompt-31-load-reduced-data.md`.
- [ ] Decide whether any residual off-spec discrepancy remains (bin density vs
  normalization) and document.
**Done when:** off-spec statistically matches v2 (corr high, ratio ~1) and is
written up.

### Phase 5 — cosmetic: pcolormesh non-monotonic warning (low priority)
- [ ] `mplwidget.py:311` pcolormesh on off-spec emits "coordinates not
  monotonically increasing/decreasing". Sanitize coords / choose shading so the
  warning is gone without changing the science. Not a crash (the SIGSEGV is
  fixed); purely tidiness.

## Suggested session/agent layout
- **Session A:** Phase 1 (orchestrator + 1 Explore subagent for the v2 formula;
  heavy validations in background). Commit. → likely fills one session.
- **Session B:** Phase 2 + Phase 3 (role/`get_xregion` work; mostly unit-test +
  GUI, lighter compute). Hand the smoke tests to the user.
- **Session C:** Phase 4 (heavy reductions, background, one-at-a-time) + Phase 5.
- Within any session, if you spawn parallel subagents keep it to ≤2 and never
  let two run heavy reductions at once (OOM).

## Acceptance for "prompt-31 complete"
- Specular & off-spec intensity match v2 within statistical tolerance
  (ratio ~1, corr ≥0.96) on ≥2 datasets.
- prompt-30 acceptance criteria (incl. AC1 `x_width=24`) all met.
- Full `make test-core` + `make test-gui` green; no new lint.
- Findings written back into `prompt-31-load-reduced-data.md` /
  `prompt-30-remaining.md`; this file's boxes ticked.
