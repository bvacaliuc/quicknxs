# prompt-30 plan: decouple Direct-Beam mode from Reflectivity mode in the GUI

## Why

Fix (A) (committed as `cdbf821`) plugged the specific cross-talk path
that produced 44035 = 17/55 in `plan/prompt-28.2-run_state.dat`. Fix (A)
is targeted and safe: it re-seeds y values only for files the GUI
hasn't classified yet.

But the **underlying architectural issue is broader** — the GUI keeps a
single set of extraction-region spinboxes (`refXPos`, `refXWidth`,
`refYPos`, `refYWidth`, `bgCenter`, `bgWidth`, `refScale`,
`rangeStart`/`rangeEnd`) that is shared by:

1. *Direct-beam* capture (clicking **Set Direct Beam** → `setNorm`),
   which wants the whole-detector beam profile (wide y, wide x).
2. *Reflectivity* extraction (clicking **Add to Reduction** →
   `addRefList`), which wants the narrower sample-reflected stripe.

There is no clean separation between the two roles. Cross-talk shows
up as:

- DBs inheriting refl widths (Fault A, fixed).
- Refls inheriting DB widths the very first time a session opens a
  direct beam, then a reflectivity, before any refl has been added.
- `actionAutoYLimits` being a *sticky* toggle: `addRefList` flips it
  off and it stays off forever — even when the user navigates back to
  a previously-set DB or loads a new DB.
- `loadExtraction` (state restore) seeding the spinboxes from the
  **last refl** at lines 1427–1430 regardless of what file the user
  is about to open next.

Fix (A) hides the symptom for one path (`calcReflParams`). Fix (C)
makes the symptom impossible by making *role* a first-class concept in
the GUI.

## What "decoupled" should look like

### Two extraction regions kept in memory, one selected at a time

```python
# Per-role extraction state, replacing the implicit single set of
# UI spinboxes that everything currently shares.
class ExtractionRegion:
    x_pos: float
    x_width: float
    y_pos: float
    y_width: float
    bg_pos: float
    bg_width: float
    scale: float          # data-runs only; ignored for DB
    extract_fan: bool     # data-runs only
    range_start: int      # data-runs only
    range_end: int        # data-runs only

self.region_db = ExtractionRegion(...)
self.region_refl = ExtractionRegion(...)
self.active_role: Literal['db', 'refl'] = 'refl'  # which the spinboxes mirror right now
```

### Role inference per file load

When a file is loaded (`fileOpen`, `openByNumber`, or `loadExtraction`
ends with `fileOpen` of the last refl) the GUI decides the role for
that file by looking it up:

1. If the file's run number is in `self.ref_norm` → role = `db`.
2. If the file's run number is in any `self.reduction_list` entry →
   role = `refl`.
3. Otherwise → role = previous role (or `refl` at first startup).

The active spinboxes are then **switched to mirror the appropriate
`ExtractionRegion`**. Auto-detection runs **for the role**:
- DB role → wide-y `get_yregion` defaults
- Refl role → keep the refl's tighter region (or auto-fit relative to
  the matched DB's beam profile)

### Buttons unchanged but the captured region is unambiguous

- **Set Direct Beam** captures `self.region_db` for `self.active_data`
  (no UI scraping required — the region is held by the role).
- **Add to Reduction** captures `self.region_refl` for
  `self.active_data` (likewise).

It becomes structurally impossible for one to scrape the other's
spinbox state.

### `loadExtraction` becomes role-aware

Instead of writing the *last refl's* options to the UI at lines
1427–1430, `loadExtraction` should:

1. Build `self.region_db` from `parser.norms[-1].options` (most recent
   DB).
2. Build `self.region_refl` from `parser.refls[-1].options`.
3. Then `fileOpen(...)` the last refl — the role-inference step
   above sets the active region to `refl` and mirrors `region_refl`
   into the spinboxes.

State restore then leaves *both* DB and refl regions ready, so the
first thing the user does after restore (open a DB or open another
refl) doesn't drag stale values into the wrong role.

### `actionAutoYLimits` becomes per-role, not sticky

Today it lives on the menu and is a single bool. After (C) it should
either:

- (i) Be split into `autoY_db` / `autoY_refl`, each with its own
  toggle, OR
- (ii) Be replaced with two implicit policies — DB always re-fits Y
  unless the user has explicitly typed something into the spinbox,
  refls auto-fit on the *first* file added then freeze.

(ii) is closer to current behaviour and keeps menu UI simple; (i) is
more transparent. Pick during implementation; either is consistent
with (C)'s architecture.

## Concrete touchpoints

| File | Change |
|---|---|
| `quicknxs/main_gui.py` | Introduce `ExtractionRegion` dataclass and `self.region_db`/`self.region_refl`/`self.active_role`. Add `_apply_region(role)` that writes a region's fields to the spinboxes under `auto_change_active`. |
| `quicknxs/main_gui.py:fileOpen` / `_fileOpenDone` | After load, infer role from `_active_file_is_known()` (already exists from Fix A), call `_apply_region(role)`. |
| `quicknxs/main_gui.py:setNorm` | Build the captured `Reflectivity` from `region_db` directly, not from spinboxes. |
| `quicknxs/main_gui.py:addRefList` | Build the captured `Reflectivity` from `region_refl` directly. Drop the `actionAutoYLimits.setChecked(False)` toggle — replace with a `region_refl.frozen=True` flag. |
| `quicknxs/main_gui.py:calcReflParams` | Update the *role's* `ExtractionRegion`, not the spinboxes directly; trigger `_apply_region` if the role's region changed. Fix (A)'s `_active_file_is_known` guard remains as fallback for any role that's still "auto". |
| `quicknxs/main_gui.py:loadExtraction` | Replace lines 1414–1434 with explicit DB/refl region initialisation as described above. |
| `quicknxs/main_gui.py` mouse handlers | When the user clicks on the projection plots, write to the active role's region (not the spinboxes directly). UI mirror falls out of the model. |
| `tests/main_gui_test.py` | New test class `RoleDecoupling` with: (a) load DB then load refl — refl must not get DB widths; (b) load state, open a new DB — DB must not get refl widths (subsumes Fix A's regression); (c) `setNorm`/`addRefList` capture must match the role's region byte-for-byte regardless of spinbox content. |

## Risks / things to be careful about

- **GUI behaviour change.** Users have muscle memory around "type in
  the spinbox, hit Set Direct Beam, see it captured". After (C) the
  capture goes via the role's region. As long as the spinboxes
  *mirror* `region_db` while DB role is active, behaviour is
  externally identical. Verify with an interactive smoke test.

- **Backwards compatibility of state files.** `HeaderCreator` /
  `HeaderParser` already write a per-row `options` dict, so the on-disk
  format doesn't change. Only the in-memory shuffle does.

- **`recalculateReflectivity`** is called by signal handlers when the
  user edits a refl row in the reduction table. Make sure it goes
  through the role machinery so a typed-in width doesn't accidentally
  poison the DB region.

- **Per-role x-width** still has no auto-detect helper. Fix (A) covers
  Y; (C) should add `get_xregion(data, role)` returning a sensible
  default x_width for the role (DB = wider, refl = narrower based on
  detector tail). Falls back to the run-number's last-seen value when
  available.

- **`ref_list_channels`** assumption (all refls share polarization
  channel set) is independent — keep as-is.

## Verification plan

1. Headless replay of `plan/prompt-28.2-run_state.dat` after (C) must
   produce identical state-file output (no cross-talk possible).
2. Run `make test-gui` — all existing tests must pass.
3. Add `RoleDecoupling` test class as listed above.
4. Interactive smoke test in `make gui`:
   - Start fresh, load 44033 / 44034 / 44035 as DBs (each with wide
     y_width, e.g. 100).
   - Load 44159 / 44160 / 44161, add as refls (y_width=55).
   - Reload 44035 — assert spinboxes show 100, not 55.
   - Reload 44161 — assert spinboxes show 55, not 100.
   - Save state, close, reopen, repeat checks.

## Out of scope for this plan

- Mantid integration (quicknxsv2 territory).
- Replacing `actionAutomaticXPeak` — it's already per-file because
  `get_xpos` is called every `calcReflParams`.
- GUI redesign / new panels.
- Polarization-aware auto-regions.

## Acceptance criteria

- After (C), running the prompt-28.2 reload + new-file sequence
  saves 44035 with `x_width=24 / y_width=100` (its own
  auto-detected DB region), regardless of what `actionAutoYLimits`
  is set to and regardless of which refl was last active.
- After (C), with `actionAutoYLimits` set to False (current default
  after `addRefList`), reloading an existing refl preserves its
  user-tuned region exactly.
- Test `RoleDecoupling.test_db_after_refl_uses_db_region` passes.
- Test `RoleDecoupling.test_refl_after_db_uses_refl_region` passes.
- Fix (A) regression tests in
  `CalcReflParamsFreshFileReseed` continue to pass.

## Estimated effort

Single focused session. The mechanical part (dataclass, two
attributes, role-mirror in `fileOpen`) is small; the surrounding
audit (mouse handlers, recalculate paths, the y-projection clicker
at lines 2200–2244 that mutates spinboxes directly) is what eats
time. Probably 2–3 hours of careful work plus tests.
