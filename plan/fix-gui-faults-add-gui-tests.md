# Plan: Fix GUI Faults and Add Comprehensive GUI Tests for quicknxsv1

## Context

The QuickNXS v1 application has been migrated from Python 2/PyQt4 to Python 3/PyQt5 (via qtpy). Four faults were discovered during production testing (documented in TODO.md), plus one additional float-to-int issue. This plan fixes all 5 bugs and adds comprehensive tests covering all major GUI interaction categories.

## Files to Modify

| File | Changes |
|------|---------|
| `quicknxs/gui_utils.py` | Fix DelayedTrigger dict mutation (Bug 1), ProgressDialog float→int (Bug 5) |
| `quicknxs/qio.py` | Fix HeaderParser KeyError on missing sections (Bug 2) |
| `quicknxs/main_gui.py` | Fix run_ipython ImportError (Bug 3), helpDialog QtWebKit (Bug 4a), aboutDialog QT_VERSION_STR (Bug 4b), guard loadExtraction for empty parse results |
| `tests/main_gui_test.py` | Add 11 new test classes (~50 test methods) |

## Part 1: Bug Fixes

### Bug 1 — DelayedTrigger dictionary mutation (CRITICAL)
**File:** `quicknxs/gui_utils.py:1074-1084`
**Root cause:** `del(self.actions[name])` inside `for name, items in self.actions.items()` mutates the dict during iteration. Also, `__call__` can add items from the main thread concurrently.
**Fix:** Iterate over `list(self.actions.items())` (snapshot), collect items to activate, then pop them after the loop:
```python
def run(self):
    while self.stay_alive:
        to_activate = []
        for name, items in list(self.actions.items()):
            ti, args = items
            if time() - ti > self.delay:
                to_activate.append((name, args))
        for name, args in to_activate:
            self.actions.pop(name, None)
            self.activate.emit(name, args)
        sleep(self.refresh)
```

### Bug 2 — HeaderParser KeyError on 'Direct Beam Runs'
**File:** `quicknxs/qio.py:454-461`
**Root cause:** `_evaluate()` unconditionally accesses `self.sections['Direct Beam Runs']`, but backup state files may not have this section.
**Fix:** Guard both `'Direct Beam Runs'` and `'Data Runs'` with existence checks, defaulting to `[]` (matching the pattern already used for optional sections like 'Event Mode Options').

Also guard `loadExtraction()` in `main_gui.py:1304` against `UnboundLocalError` when `parser.refls` is empty (no datasets to restore):
```python
if not parser.refls:
    info('No datasets found in header to restore.')
    return
```

### Bug 3 — IPython Console ModuleNotFoundError
**File:** `quicknxs/main_gui.py:224-234`
**Root cause:** `from .ipython_widget import IPythonConsoleQtWidget` triggers `import IPython`, which is not installed.
**Fix:** Wrap the import in `try/except ImportError`, log a warning message, and return.

### Bug 4a — helpDialog QtWebKit not available
**File:** `quicknxs/main_gui.py:2475-2496`
**Root cause:** `QtWebKit` is `None` (import failed at line 13-15); `QtWebKit.QWebView(dia)` crashes.
**Fix:** Check `if QtWebKit is not None:`, else fall back to `QTextBrowser` which can render basic HTML.

### Bug 4b — aboutDialog QT_VERSION_STR attribute error
**File:** `quicknxs/main_gui.py:2522`
**Root cause:** `QtCore.QT_VERSION_STR` doesn't exist in qtpy (confirmed: `hasattr(QtCore, 'QT_VERSION_STR')` is False).
**Fix:** Use `qtpy.QT_VERSION` (confirmed working, returns `'5.15.15'`). Add `import qtpy` at top of `aboutDialog()`.

### Bug 5 — ProgressDialog.progress() float→int
**File:** `quicknxs/gui_utils.py:1048`
**Root cause:** `self.progressBar.setValue(param)` where `param = value*100+self.add` is a float. Same issue as the already-fixed `updateEventReadout`.
**Fix:** `self.progressBar.setValue(int(param))`

## Part 2: Test Plan

All tests go in `tests/main_gui_test.py`, following existing patterns: unittest.TestCase, QMessageBox.warning patched, trigger disabled, state file cleaned. TEST_EVENT constant added for event mode tests.

### Bug Verification Tests (5 classes)

**MainGUIDelayedTrigger** — Verify Bug 1 fix
- `test_iterate_over_copy` — Add multiple expired actions, simulate run loop iteration, verify no RuntimeError and all actions processed
- `test_trigger_thread_lifecycle` — Start/stop DelayedTrigger thread cleanly

**MainGUIHeaderParserFault** — Verify Bug 2 fix
- `test_missing_direct_beam_section` — Parse header with no `[Direct Beam Runs]`, verify no KeyError, empty list returned
- `test_missing_data_runs_section` — Parse header with no `[Data Runs]`, same check
- `test_empty_state_header` — Parse minimal "Running PID ..." backup content

**MainGUIIPythonFault** — Verify Bug 3 fix (with full GUI setUp)
- `test_run_ipython_no_crash` — Call `run_ipython()`, verify no unhandled exception

**MainGUIHelpAboutFault** — Verify Bug 4 fixes (with full GUI setUp)
- `test_help_dialog_no_crash` — Call `helpDialog()`, verify no AttributeError
- `test_about_dialog_no_crash` — Call `aboutDialog()` (patching QMessageBox.about), verify no AttributeError
- `test_about_dialog_contains_version` — Verify the about text includes version info

**MainGUIProgressDialogFix** — Verify Bug 5 fix
- `test_progress_accepts_float` — Create ProgressDialog, call `progress()` with float values 0.0→1.0
- `test_progress_with_add_offset` — Verify `add` offset works correctly with float values

### Comprehensive GUI Tests (6 classes)

**MainGUIFileOperations** — File open/reload/event/sum operations (setUp loads TEST_DATASET)
- `test_reload_file` — `reloadFile()` re-reads same file
- `test_file_open_event_dataset` — Open `TEST_EVENT` without plot
- `test_file_open_event_with_plot` — Open `TEST_EVENT` with plot
- `test_open_by_number_not_found` — `openByNumber('999999')` returns False
- `test_file_open_sum` — `fileOpenSum([TEST_DATASET, TEST_DATASET])`
- `test_folder_modified_no_crash` — `folderModified()` doesn't crash
- `test_empty_cache` — `empty_cache()` resets cache

**MainGUIExtractionRegion** — Extraction region controls (setUp loads TEST_DATASET with plot)
- `test_overwrite_direct_beam` — `overwriteDirectBeam()` sets dpix and dangle
- `test_clear_overwrite` — `clearOverwrite()` resets to -1 / "None"
- `test_change_region_fan_reflectivity` — Toggle fanReflectivity checkbox
- `test_trust_dangle_toggle` — Toggle trustDANGLE checkbox
- `test_range_start_end_setValue` — Set rangeStart/rangeEnd values
- `test_bg_active_toggle` — Toggle background active radio button

**MainGUIReductionActions** — Reduction list operations (setUp loads TEST_DATASET with plot)
- `test_add_ref_without_norm` — `addRefList()` without normalization warns, doesn't add
- `test_set_norm_and_add_ref` — Set normalization, add to list, verify table row
- `test_remove_ref_list` — Remove item from reduction list
- `test_clear_ref_list` — Clear entire reduction list
- `test_clear_norm_list` — Clear normalization table
- `test_reduce_datasets_empty` — `reduceDatasets()` with empty list logs warning
- `test_quick_reduce_empty` — `quickReduce()` with empty list logs warning

**MainGUIDisplayControls** — Display toggles and tab switching (setUp loads TEST_DATASET with plot)
- `test_toggle_hide` — Toggle `hide_plots` checkbox on/off
- `test_toggle_colorbars` — Call `toggleColorbars()`
- `test_plot_tab_switching` — Set each plotTab index, call `plotActiveTab()`
- `test_replot_projections` — Call `replotProjections()` with logarithmic_y toggled
- `test_change_active_channel` — Select channel0, call `changeActiveChannel()`
- `test_logarithmic_colorscale_toggle` — Toggle logarithmic_colorscale checkbox
- `test_normalize_xtof_toggle` — Toggle normalizeXTof checkbox
- `test_color_selector_change` — Change color_selector combo box index

**MainGUIMenuActions** — Menu action handlers
- `test_set_debug` — `set_debug()` enables debug logging
- `test_raise_error` — `raiseError()` raises RuntimeError
- `test_export_raw_data_no_refl` — `exportRawData()` with refl=None returns silently
- `test_open_nxs_dialog_no_data` — `open_nxs_dialog()` with active_data=None returns silently

**MainGUISettingsState** — Settings persistence and state management
- `test_update_state_file` — `updateStateFile()` writes PID
- `test_update_state_file_with_reduction` — State file includes header when reduction_list populated
- `test_close_event_no_crash` — `close()` doesn't crash

## Implementation Order

1. Bug 5 (one-line ProgressDialog fix)
2. Bug 1 (DelayedTrigger dict mutation)
3. Bug 2 (HeaderParser KeyError + loadExtraction guard)
4. Bug 3 (IPython try/except)
5. Bug 4a + 4b (helpDialog + aboutDialog)
6. Write all bug verification test classes
7. Write all comprehensive GUI test classes
8. Run `pixi run test-gui` after each step; `pixi run test` at the end

## Verification

```bash
pixi run test-gui   # all GUI tests pass
pixi run test       # full suite (91+ existing + ~50 new) all pass
pixi run ruff check quicknxs/  # no lint errors in modified files
```
