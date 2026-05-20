# prompt-30 remaining work (Layer 2)

Status of `plan/prompt-30-decouple-db-refl-ui.md` after the session that
landed commits `1b2439f` (parser) and `ddb7944` (role decoupling).

## What landed (Layer 1 — committed, tested)

The architectural core of Fix (C) is in:

- `ExtractionRegion` dataclass (7 fields: `x_pos`, `x_width`, `y_pos`,
  `y_width`, `bg_pos`, `bg_width`, `scale`; units match
  `Reflectivity.options`, `scale` linear).
- `self.region_db` / `self.region_refl` / `self.active_role`.
- Helpers `_read_region_from_ui`, `_apply_region_to_ui`,
  `_active_file_number`, `_active_file_role`, `_applyRoleRegion`.
  `_active_file_is_known` now delegates to `_active_file_role`.
- `fileLoaded → _applyRoleRegion` (after `calcReflParams`): mirrors a
  role's region into the spinboxes **only on a role switch** (db↔refl),
  so same-role reloads and Fix A's fresh-file Y reseed are untouched.
- `setNorm` captures `region_db`; `addRefList` captures `region_refl`,
  both from the stored object's `options` (correct under `loadExtraction`).
- `loadExtraction` seeds **both** regions and applies `region_refl` for
  the reopened last refl (byte-identical to the old last-refl seeding).
- `tests/main_gui_test.py::RoleDecoupling` (5 tests). Full GUI suite
  109/109; `CalcReflParamsFreshFileReseed` (Fix A) and
  `LoadExtractionRoundTrip` still pass.

### Deliberate scope choice

Layer 1 uses a **role-switch-only** application and keeps `calcReflParams`
(Fix A) unchanged. This fixes the *classified-file* and *state-restore*
cross-talk (open a known DB after refls / a known refl after DBs / restore
then open the other role) with **no GUI smoke test required** and no
regression risk to refl-stitching. It does **not** yet fix the headline
*fresh-file-becomes-DB* case (AC1's 44035 → `x_width=24`), which needs the
items below and interactive verification.

## What remains (Layer 2 — needs interactive smoke test)

### 1. `get_xregion(data, role)` — per-file x-width auto-detect  ← AC1 blocker

The three direct beams in the REF_M 11486 reference have **different**
x-widths (`44033`=12, `44034`=16, `44035`=24); refls are ~17. A single
shared `region_db.x_width` cannot reproduce per-DB widths, and
`calcReflParams` today auto-fits only `x_pos` (CWT) and `y` (`get_yregion`),
never `x_width`. So a freshly-loaded DB keeps whatever `x_width` was on
screen (a refl's 17), and `setNorm` captures it.

Add `quicknxs/qcalc.py::get_xregion(data, role)` returning a sensible
`x_width` (DB = full beam stripe from the x-projection FWHM / tails;
refl = narrower). Wire into `calcReflParams` for **fresh** files (mirror
Fix A's Y branch): fresh DB → wide `x_width`; fresh refl → narrow.
Acceptance: fresh 44035 auto-detects `x_width≈24`, `y_width≈100`
regardless of the previously active refl. Validate the detector's output
against the v2 header values for 44033/34/35 before trusting it.

### 2. Fresh-file → DB capture path

Even with (1), make `setNorm` robust: when invoked while
`active_role=='refl'` (user clicked **Set Direct Beam** on a file the GUI
still thinks is refl-role), switch to `db` role and ensure the captured
region uses DB-role widths (`get_xregion` / `region_db`), not the on-screen
refl widths. Mirror for `addRefList` from a db-role file.

### 3. Position vs. policy separation

`_applyRoleRegion` currently applies the whole stored region (including
`x_pos`/`y_pos`) on a switch. That is right for *restoring a known file*
but conflates per-file **position** (should re-fit from data) with per-role
**policy** widths. Consider splitting `ExtractionRegion` into policy
(`x_width`, `bg_*`, `scale`) vs. position (`x_pos`, `y_pos`, `y_width`),
so a DB always re-fits position while keeping role policy. Decide together
with (1).

### 4. `changeRegionValues` capture (hot path)

Snapshot the spinboxes into `region[active_role]` at the end of
`changeRegionValues`, so a user edit after `addRefList` survives a
same-role reload (today `_applyRoleRegion` is a no-op on same-role, so the
edit is kept on screen — but a later switch-away/switch-back would restore
the stale captured region). Low-risk: snapshot only, no control-flow change.

### 5. Mouse handlers (`plotPickX`/`plotPickY`/`plotPickXY`)

They write spinboxes directly (`main_gui.py` ~2240–2330). With (4) the
region tracks automatically; otherwise route them through
`region[active_role]`. Verify the projection-plot click-drag still updates
lines.

### 6. `actionAutoYLimits` per-role (plan option i/ii)

Today `addRefList` flips the single global toggle off and it stays off
(sticky). Either split into `autoY_db`/`autoY_refl` or replace with the
implicit policy "DB always re-fits Y; refls freeze after the first add".
Option (ii) is closest to current behaviour.

## Interactive smoke test (from the original plan, still required)

`make gui`:
1. Fresh start; load 44033 / 44034 / 44035 as DBs (wide y, e.g. 100).
2. Load 44159 / 44160 / 44161, add as refls (y≈55, x≈17).
3. Reload 44035 → spinboxes must show the DB region (wide), not 55/17.
4. Reload 44161 → spinboxes must show 55/17.
5. Save state, close, reopen, repeat 3–4.
6. Headless replay of `plan/prompt-28.2-run_state.dat` must still produce
   identical state-file output.

## Acceptance criteria not yet met

- AC1 (fresh 44035 → `x_width=24 / y_width=100`): **blocked on item 1**
  (`get_xregion`). `y_width=100` already comes from Fix A; `x_width=24`
  does not.
- AC2/AC3/AC4 for **classified** files and state-restore: met by Layer 1.
- AC5 (Fix A regressions): met.
