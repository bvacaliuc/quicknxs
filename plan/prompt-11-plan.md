# Plan: Fix Four UI Errors + Systematic QFileDialog Tuple Return Bug

## Overview

There are four reported errors in TODO.md, but investigation reveals they represent **two distinct bug classes** plus one missing-feature issue:

1. **Bug Class A — `QFileDialog` tuple return values not unpacked** (causes 3 of 4 reported errors, plus 4 more latent bugs across the codebase)
2. **Bug Class B — Orphaned `_init_toolbar()` method** (causes the `labelAction` AttributeError)
3. **Missing feature — IPython/qtconsole not in dependencies** (graceful degradation already works; needs dependency or better UX)

---

## Bug Class A: QFileDialog Return Value Handling

### Root Cause

In PyQt5, **all** `QFileDialog` static methods return tuples, not bare strings:

| Method | Returns |
|--------|---------|
| `getOpenFileName()` | `tuple[str, str]` — `(filepath, selected_filter)` |
| `getSaveFileName()` | `tuple[str, str]` — `(filepath, selected_filter)` |
| `getOpenFileNames()` | `tuple[list[str], str]` — `([filepaths], selected_filter)` |
| `getExistingDirectory()` | `str` — only one that returns a bare string |

Code written for PyQt4 (where these returned bare strings) broke silently when migrated to PyQt5. The result: tuples are passed to `open()`, compared against `''`, or iterated as if they were strings/lists.

### Complete Inventory of All Call Sites

Every `QFileDialog` call in the codebase, with status:

| # | File | Line | Method | Current Code | Bug? | Consequence |
|---|------|------|--------|-------------|------|-------------|
| 1 | `main_gui.py` | 1185 | `getOpenFileNames` | `...[0]` | No | Already unpacked |
| 2 | `main_gui.py` | 1206 | `getOpenFileNames` | raw tuple | **YES** | `fileOpenSumDialog` iterates tuple not filenames |
| 3 | `main_gui.py` | 1267 | `getOpenFileName` | raw tuple | **YES** | `loadExtraction` hangs — **REPORTED IN TODO** |
| 4 | `main_gui.py` | 1987 | `getSaveFileName` | raw tuple | **YES** | `exportRawData` writes to wrong path or crashes |
| 5 | `main_gui.py` | 2437 | `getOpenFileNames` | raw tuple | **YES** | `open_filter_dialog` crashes — **REPORTED IN TODO** |
| 6 | `compare_plots.py` | 28 | `getOpenFileNames` | raw tuple | **YES** | `open_file` passes list to `os.path.dirname` |
| 7 | `mplwidget.py` | 237 | `getSaveFileName` | raw tuple | **YES** | `savefig` passes tuple to `print_figure` |
| 8 | `polarization_gui.py` | 293 | `getSaveFileName` | raw tuple | **YES** | `exportPolarizationParameters` writes wrong path |
| 9 | `polarization_gui.py` | 319 | `getSaveFileName` | raw tuple | **YES** | `exportFR` writes wrong path |
| 10 | `polarization_gui.py` | 363 | `getSaveFileName` | raw tuple | **YES** | `exportFRDetector` writes wrong path |
| 11 | `quicklog_gui.py` | 163 | `getOpenFileName` | raw tuple | **YES** | `openFile` passes tuple to `Logfile()` |
| 12 | `gui_utils.py` | 485 | `getExistingDirectory` | bare string | No | Returns string, no tuple |

**9 of 12 call sites are broken.** Only #1 (already has `[0]`) and #12 (`getExistingDirectory` returns a string) are correct.

### Fixes

All fixes follow the same pattern: extract `[0]` from the tuple.

#### Fix A1: `main_gui.py:1206` — `fileOpenSumDialog()`

```python
# BEFORE:
filenames=QtWidgets.QFileDialog.getOpenFileNames(self, u'Open NXS file...',
                                           directory=self.active_folder,
                                           filter=filter_)
# AFTER:
filenames=QtWidgets.QFileDialog.getOpenFileNames(self, u'Open NXS file...',
                                           directory=self.active_folder,
                                           filter=filter_)[0]
```

#### Fix A2: `main_gui.py:1267` — `loadExtraction()` — **REPORTED BUG: program hangs**

```python
# BEFORE:
filename=QtWidgets.QFileDialog.getOpenFileName(self, u'Create extraction from file header...',
                                           directory=paths.results,
                                           filter=u'Extracted Dataset (*.dat)')
if filename==u'':
  return
# AFTER:
filename=QtWidgets.QFileDialog.getOpenFileName(self, u'Create extraction from file header...',
                                           directory=paths.results,
                                           filter=u'Extracted Dataset (*.dat)')[0]
if filename==u'':
  return
```

Why this hangs: `filename` is a tuple `('', 'filter')` on cancel. `('', 'filter') == ''` is False, so the early return is skipped. Then `open(('', 'filter'), 'rb')` raises a TypeError. Since the exception handler only wraps `HeaderParser` (not the `open` call), the unhandled TypeError propagates up and the Qt event loop may get corrupted, hanging the GUI.

#### Fix A3: `main_gui.py:1987` — `exportRawData()`

```python
# BEFORE:
name=QtWidgets.QFileDialog.getSaveFileName(parent=self, caption=u'Select export file name',
                                 filter='ASCII files (*.dat);;All files (*.*)')
if name!='':
# AFTER:
name=QtWidgets.QFileDialog.getSaveFileName(parent=self, caption=u'Select export file name',
                                 filter='ASCII files (*.dat);;All files (*.*)')
name=name[0]
if name!='':
```

Note: We extract `[0]` on a separate line here because `name` is used for both the comparison and the file write. Alternatively, append `[0]` to the call and adjust only once.

#### Fix A4: `main_gui.py:2437` — `open_filter_dialog()` — **REPORTED BUG: TypeError**

```python
# BEFORE:
names=QtWidgets.QFileDialog.getOpenFileNames(self, u'Select reflectivity file(s)...',
                                         directory=paths.results,
                                         filter=filter_)
# AFTER:
names=QtWidgets.QFileDialog.getOpenFileNames(self, u'Select reflectivity file(s)...',
                                         directory=paths.results,
                                         filter=filter_)[0]
```

#### Fix A5: `compare_plots.py:28` — `open_file()`

```python
# BEFORE:
names=QFileDialog.getOpenFileNames(self, u'Open reflectivity file...',
                                           directory=self.active_folder,
                                           filter=filter_)
# AFTER:
names=QFileDialog.getOpenFileNames(self, u'Open reflectivity file...',
                                           directory=self.active_folder,
                                           filter=filter_)[0]
```

#### Fix A6: `mplwidget.py:237` — `savefig()`

```python
# BEFORE:
fname=QtWidgets.QFileDialog.getSaveFileName(self, u"Choose a filename to save to", start, filters)
# AFTER:
fname=QtWidgets.QFileDialog.getSaveFileName(self, u"Choose a filename to save to", start, filters)[0]
```

#### Fix A7–A9: `polarization_gui.py` — three `getSaveFileName` calls

Lines 293, 319, 363: Append `[0]` to each `getSaveFileName()` call.

```python
# Line 293 BEFORE:
name=QFileDialog.getSaveFileName(parent=self, caption=u'Select export file prefix',
                                 filter='ASCII files (*.dat);;All files (*.*)')
# Line 293 AFTER:
name=QFileDialog.getSaveFileName(parent=self, caption=u'Select export file prefix',
                                 filter='ASCII files (*.dat);;All files (*.*)')
name=name[0]

# Line 319 BEFORE:
name=QFileDialog.getSaveFileName(parent=self, caption=u'Select export file name',
                                 filter='ASCII files (*.dat);;All files (*.*)')
# Line 319 AFTER:
name=QFileDialog.getSaveFileName(parent=self, caption=u'Select export file name',
                                 filter='ASCII files (*.dat);;All files (*.*)')
name=name[0]

# Line 363 BEFORE:
name=QFileDialog.getSaveFileName(parent=self, caption=u'Select export file name',
                                 filter='ASCII files (*.dat);;All files (*.*)')
# Line 363 AFTER:
name=QFileDialog.getSaveFileName(parent=self, caption=u'Select export file name',
                                 filter='ASCII files (*.dat);;All files (*.*)')
name=name[0]
```

#### Fix A10: `quicklog_gui.py:163` — `openFile()`

```python
# BEFORE:
filename=QFileDialog.getOpenFileName(self, caption=u'Select logfile')
# AFTER:
filename=QFileDialog.getOpenFileName(self, caption=u'Select logfile')[0]
```

### Tests for Bug Class A

Add tests in `tests/main_gui_test.py`:

1. **`test_loadExtraction_cancel_no_hang`**: Patch `getOpenFileName` to return `('', '')`, call `loadExtraction()`, verify it returns cleanly without hanging or raising.

2. **`test_open_filter_dialog_cancel_no_crash`**: Patch `getOpenFileNames` to return `([], '')`, call `open_filter_dialog()`, verify no TypeError.

3. **`test_fileOpenSumDialog_cancel_no_crash`**: Patch `getOpenFileNames` to return `([], '')`, call `fileOpenSumDialog()`, verify no crash.

4. **`test_exportRawData_cancel_no_crash`**: Patch `getSaveFileName` to return `('', '')`, call `exportRawData()`, verify no crash.

---

## Bug Class B: NavigationToolbar `labelAction` AttributeError

### Root Cause

The custom `NavigationToolbar` class in `mplwidget.py` overrides `_init_toolbar()` (line 43), which creates `self.labelAction` at line 107. However, in matplotlib 3.6+, `NavigationToolbar2QT.__init__()` **no longer calls `_init_toolbar()`**. It builds the toolbar directly in `__init__` instead.

So:
1. `NavigationToolbar.__init__()` calls `NavigationToolbar2QT.__init__()` which builds the **default** toolbar (with standard matplotlib icons)
2. `_init_toolbar()` is never called — custom icons, `self.labelAction`, `self.buttons`, and `self.adj_window` are never created
3. `gui_utils.py:555` accesses `self.plot.toolbar.labelAction.setVisible(True)` → **AttributeError**

The parent class DOES create a `labelAction` local variable when `coordinates=True`, but stores it as a **local** not `self.labelAction`. The parent also creates `self.locLabel` when `coordinates=True`.

### What `_init_toolbar()` Provided

The orphaned `_init_toolbar()` method provided:
1. **Custom icons** from Qt resource file (`:/MPL Toolbar/...`) instead of matplotlib's default PNG icons
2. **Print button** — `self.print_figure()` for direct printing
3. **Log toggle button** — `self.toggle_log()` for switching y-scale
4. **`self.labelAction`** — coordinates label visibility toggle
5. **`self.locLabel`** — coordinates display (parent also creates this when `coordinates=True`)

### Fix

Move the toolbar customization from the dead `_init_toolbar()` into `__init__()`, running **after** the parent `__init__` completes. The parent `__init__` builds the standard toolbar; we then:
1. Clear the standard toolbar actions
2. Rebuild with custom icons, adding Print and Log toggle buttons
3. Store `self.labelAction` as an instance attribute

```python
def __init__(self, canvas, parent, coordinates=False):
    NavigationToolbar2QT.__init__(self, canvas, parent, coordinates)
    self.setIconSize(QtCore.QSize(20, 20))
    self._customize_toolbar()

def _customize_toolbar(self):
    # Remove default actions built by parent __init__
    for action in self.actions():
        self.removeAction(action)

    # Rebuild with custom icons (same code as old _init_toolbar)
    icon=QtGui.QIcon()
    icon.addPixmap(QtGui.QPixmap(":/MPL Toolbar/go-home.png"), ...)
    a=self.addAction(icon, 'Home', self.home)
    a.setToolTip('Reset original view')
    # ... [same icon setup as _init_toolbar lines 48-94] ...

    # Coordinates label
    self.locLabel=QtWidgets.QLabel("", self)
    self.locLabel.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTop)
    self.locLabel.setSizePolicy(
        QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding,
                          QtWidgets.QSizePolicy.Ignored))
    self.labelAction=self.addWidget(self.locLabel)
    if self.coordinates:
        self.labelAction.setVisible(True)
    else:
        self.labelAction.setVisible(False)
    self.adj_window=None
```

**Critical detail**: The parent `__init__` internally calls `NavigationToolbar2.__init__(self, canvas)` which sets up mouse event handlers. Our `_customize_toolbar()` only replaces visual elements (actions/icons), not the functional backend. This is safe.

**Also remove the old `_init_toolbar()`** method entirely — it's dead code.

### Where `labelAction` Is Referenced

| File | Line | Code |
|------|------|------|
| `mplwidget.py` | 107 | `self.labelAction=self.addWidget(self.locLabel)` (dead code in `_init_toolbar`) |
| `mplwidget.py` | 109 | `self.labelAction.setVisible(True)` (dead code) |
| `mplwidget.py` | 111 | `self.labelAction.setVisible(False)` (dead code) |
| `gui_utils.py` | 555 | `self.plot.toolbar.labelAction.setVisible(True)` — **crash site** |

After the fix, `self.labelAction` will be set in `_customize_toolbar()` (called from `__init__`), so all references will work.

### Tests for Bug Class B

Add to `tests/main_gui_test.py`:

1. **`test_toolbar_has_labelAction`**: Create an `MPLWidget`, verify `toolbar.labelAction` exists and is a `QWidgetAction`.

2. **`test_toolbar_labelAction_visibility`**: Create `MPLWidget(coordinates=False)`, verify `labelAction.isVisible()` is False. Create with `coordinates=True` (set after), verify it can be toggled.

3. **`test_plot_dialog_no_crash`**: Create a `PlotDialog()`, verify no `AttributeError` — this is the exact crash from the bug report.

---

## Issue C: IPython Console Not Available

### Current State

The `run_ipython()` method (main_gui.py:224-238) tries to import `quicknxs.ipython_widget`, which in turn imports `IPython`. IPython and qtconsole are **not listed** in `pyproject.toml` or `pixi.toml` dependencies. The current behavior is graceful: it logs "IPython is not installed" and returns.

### Options (choose one)

**Option 1 — Add IPython as a dependency** (if the feature is wanted):
```toml
# In pyproject.toml [tool.pixi.dependencies]:
ipython = "*"
qtconsole = "*"
```
Note: the `ipython_widget.py` module uses `IPython.qt.console` import paths from IPython 1.x-3.x era. Modern IPython (8.x+) moved these to the separate `qtconsole` package. The imports in `ipython_widget.py` would need updating:
```python
# Old (IPython 1.x-3.x):
from IPython.qt.console.rich_ipython_widget import RichIPythonWidget
from IPython.qt.inprocess import QtInProcessKernelManager
# New (qtconsole 5.x):
from qtconsole.rich_jupyter_widget import RichJupyterWidget
from qtconsole.inprocess import QtInProcessKernelManager
```

**Option 2 — Improve the user-facing message** (minimal fix):
Change the `info()` log to a visible `QMessageBox.information()` dialog so users actually see the message instead of it being buried in the log file.

**Recommendation**: Option 2 (minimal fix) — the IPython console is a developer/power-user feature. Adding qtconsole as a dependency would bring in significant additional packages. A visible message is better than a silent log entry.

---

## Implementation Order

Implement in this order for safest, most testable progression:

### Phase 1: QFileDialog tuple fixes (Bug Class A)
**Files:** `main_gui.py`, `compare_plots.py`, `mplwidget.py`, `polarization_gui.py`, `quicklog_gui.py`

This is the highest-priority fix. It's mechanical (add `[0]`), affects 9 call sites across 5 files, and fixes 2 of the 4 reported bugs. Do all 9 sites at once — they're the same bug repeated.

### Phase 2: NavigationToolbar fix (Bug Class B)
**Files:** `mplwidget.py`, `gui_utils.py` (no change needed — it already references `labelAction` correctly)

Move `_init_toolbar()` body into `_customize_toolbar()` called from `__init__`. Delete the dead `_init_toolbar()` method. This fixes the 3rd reported bug.

### Phase 3: IPython message improvement (Issue C)
**Files:** `main_gui.py`

Change `info()` to `QMessageBox.information()` for the missing-IPython case. This addresses the 4th reported issue.

### Phase 4: Tests
**Files:** `tests/main_gui_test.py`, `tests/qio_test.py`

Add tests for:
- QFileDialog cancel handling (loadExtraction, open_filter_dialog, fileOpenSumDialog, exportRawData)
- NavigationToolbar.labelAction existence
- PlotDialog instantiation
- IPython not-installed message (already tested in `MainGUIIPythonFault`)

---

## Files Modified

| File | Phase | Changes |
|------|-------|---------|
| `quicknxs/main_gui.py` | 1, 3 | Fix 4 QFileDialog calls (lines 1206, 1267, 1987, 2437); improve IPython message |
| `quicknxs/compare_plots.py` | 1 | Fix 1 QFileDialog call (line 28) |
| `quicknxs/mplwidget.py` | 1, 2 | Fix 1 QFileDialog call (line 237); rebuild toolbar in `__init__` |
| `quicknxs/polarization_gui.py` | 1 | Fix 3 QFileDialog calls (lines 293, 319, 363) |
| `quicknxs/quicklog_gui.py` | 1 | Fix 1 QFileDialog call (line 163) |
| `tests/main_gui_test.py` | 4 | Add tests for all fixes |

## Verification

```bash
make test  # All existing + new tests pass
```

Manual verification:
1. File → Load Extraction → Cancel → no hang
2. Tools → Filter Points → Cancel → no crash
3. Reduce with "Plot" checked → no `labelAction` error, plots appear with custom toolbar
4. Advanced → IPython Console → user sees informative message dialog
5. File → Open Sum → Cancel → no crash
6. Save figure from any plot toolbar → file saved correctly
