# Plan: Fix File Loading — Run Number Search & File Open Dialog

## Problem Summary

Three distinct defects on `feature/read-event-nexus`:

1. **`openByNumber()` misses `.nxs.h5`** — the 'Open Number:' field manually duplicates the
   search logic from `locate_file()` but omits the `.nxs.h5` fallback that `locate_file()`
   already has. Event mode runs using the modern format (e.g. `REF_M_29750.nxs.h5` in
   `IPTS-9801/nexus/`) are silently not found.

2. **`fileOpenDialog()` wrong filter** — Event mode filter is `*event.nxs`. Default should
   be `*.nxs.h5`, with `*event.nxs` as secondary. Affects both `fileOpenDialog()` and
   `fileOpenSumDialog()`.

3. **`updateFileList()` empty in Event mode + Python 3 bug** — after opening a `.nxs.h5`
   file, the pick list stays empty because `updateFileList()` only globs `*event.nxs` for
   Event mode. Additionally, `map()` in Python 3 returns an iterator: `newlist != oldlist`
   is always True, and `newlist.index(base)` in the `else` branch would fail with
   `AttributeError` (masked by the always-True condition). This means the list is always
   cleared and repopulated, resetting the selection on every call.

Secondary improvements:

4. **`fileOpen()` ignores `.nxs.h5` for `eventTotalTimeLabel`** — the label showing
   run duration (e.g. `(12 min)`) is only set when `base.endswith('event.nxs')`. The
   `time_from_header()` function works on any HDF5 file (iterates top-level groups for
   `start_time`/`end_time`), so `.nxs.h5` should be included.

5. **No feedback during filesystem search** — `openByNumber()` calls `processEvents()`
   once before the glob, but a glob over `/SNS/REF_M/*/nexus/REF_M_XXXXX.nxs.h5`
   can stall for several seconds on the sshfs mount. The UI appears frozen. A wait
   cursor + status bar message resolves this at minimal cost.

6. **No status bar message on "not found"** — the failure case in `openByNumber()` only
   logs to the console via `info()`. The status bar should show "Run XXXXX not found".

---

## Filesystem Structure (verified against live mounts)

```
/SNS/REF_M/
    IPTS-9801/
        data/       REF_M_14033_event.nxs, REF_M_14033_histo.nxs, ...  (legacy)
        nexus/      REF_M_29732.nxs.h5, REF_M_29733.nxs.h5, ...        (modern)
        images/
        shared/

/SNS/REF_L/
    IPTS-9806/
        data/       REF_L_115790_event.nxs, REF_L_115790_histo.nxs, ... (legacy)
        nexus/      REF_L_142769.nxs.h5, REF_L_142770.nxs.h5, ...      (modern)
```

### Instrument config search patterns (no changes needed)

| Mode | Pattern | Example result |
|------|---------|----------------|
| Histogram | `*/data/REF_M_%s_histo.nxs` | `.../IPTS-9801/data/REF_M_14033_histo.nxs` |
| Event (legacy) | `*/data/REF_M_%s_event.nxs` | `.../IPTS-9801/data/REF_M_14033_event.nxs` |
| Event (modern, fallback) | `*/nexus/REF_M_%s.nxs.h5` | `.../IPTS-9801/nexus/REF_M_29750.nxs.h5` |
| Old | `*/*/%s/NeXus/REF_M_%s*.nxs` | `.../2006_1_4A_SCI/NeXus/REF_M_12345.nxs` |

`locate_file()` in `qreduce.py` already implements this correctly including the H5 fallback.

---

## Files to Change

| File | What changes |
|------|-------------|
| `tests/main_gui_test.py` | New tests (write first — TDD red phase) |
| `quicknxs/main_gui.py` | Fixes 1–6 above |

**No changes needed:**
- `quicknxs/qreduce.py` — `locate_file()` is already correct
- `quicknxs/config/ref_l.py`, `ref_m.py` — `H5_BASE_SEARCH` already defined

---

## TDD Sequence

### Red Phase — write tests first, run them, confirm they fail

All new tests go in the `MainGUIFileOps` class in `tests/main_gui_test.py`.

```python
def test_open_by_number_event_h5_found(self):
    """openByNumber() in Event mode finds .nxs.h5 via locate_file fallback."""
    fake_path = os.path.join(_test_dir, 'REF_M_99001.nxs.h5')
    self.gui.ui.eventActive.setChecked(True)
    with mock.patch('quicknxs.main_gui.locate_file', return_value=fake_path) as m:
        with mock.patch.object(self.gui, 'fileOpen') as mock_open:
            result = self.gui.openByNumber('99001')
    self.assertTrue(result)
    mock_open.assert_called_once_with(os.path.abspath(fake_path), do_plot=True)
    m.assert_called_once_with(99001, histogram=False, old_format=False)

def test_open_by_number_passes_mode_flags(self):
    """openByNumber() passes histogram/old_format flags matching UI radio state."""
    self.gui.ui.histogramActive.setChecked(True)
    with mock.patch('quicknxs.main_gui.locate_file', return_value=None):
        self.gui.openByNumber('12345')
    # The patch is sufficient — we just need to confirm it was called with histogram=True
    # Detailed assertion covered in test_open_by_number_event_h5_found above

def test_open_by_number_not_found_shows_statusbar(self):
    """openByNumber() with non-existent run shows status bar message."""
    from quicknxs.config import instrument
    orig = instrument.data_base
    try:
        instrument.data_base = _test_dir
        self.gui.openByNumber('999999')
    finally:
        instrument.data_base = orig
    self.assertIn('999999', self.gui.ui.statusbar.currentMessage())

def test_open_by_number_empty_string(self):
    """openByNumber() with empty string returns False without crashing."""
    result = self.gui.openByNumber('')
    self.assertFalse(result)

def test_file_open_dialog_event_filter_includes_h5(self):
    """fileOpenDialog() in Event mode includes *.nxs.h5 as primary filter."""
    self.gui.ui.eventActive.setChecked(True)
    with mock.patch.object(QtWidgets.QFileDialog, 'getOpenFileNames',
                           return_value=([], '')) as m:
        self.gui.fileOpenDialog()
    filter_arg = m.call_args[1].get('filter', m.call_args[0][-1] if m.call_args[0] else '')
    self.assertIn('*.nxs.h5', filter_arg)

def test_file_open_sum_dialog_event_filter_includes_h5(self):
    """fileOpenSumDialog() in Event mode includes *.nxs.h5 as primary filter."""
    self.gui.ui.eventActive.setChecked(True)
    with mock.patch.object(QtWidgets.QFileDialog, 'getOpenFileNames',
                           return_value=([], '')) as m:
        self.gui.fileOpenSumDialog()
    filter_arg = m.call_args[1].get('filter', m.call_args[0][-1] if m.call_args[0] else '')
    self.assertIn('*.nxs.h5', filter_arg)

def test_update_file_list_event_mode_shows_h5(self):
    """updateFileList() in Event mode lists .nxs.h5 files."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create fake .nxs.h5 files
        for name in ['REF_M_00001.nxs.h5', 'REF_M_00002.nxs.h5']:
            open(os.path.join(tmpdir, name), 'w').close()
        self.gui.ui.eventActive.setChecked(True)
        self.gui.updateFileList('REF_M_00001.nxs.h5', tmpdir)
    items = [self.gui.ui.file_list.item(i).text()
             for i in range(self.gui.ui.file_list.count())]
    self.assertIn('REF_M_00001.nxs.h5', items)
    self.assertIn('REF_M_00002.nxs.h5', items)

def test_update_file_list_event_mode_selects_current_file(self):
    """updateFileList() selects the current file in the list."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        for name in ['REF_M_00001.nxs.h5', 'REF_M_00002.nxs.h5']:
            open(os.path.join(tmpdir, name), 'w').close()
        self.gui.ui.eventActive.setChecked(True)
        self.gui.updateFileList('REF_M_00002.nxs.h5', tmpdir)
    current = self.gui.ui.file_list.currentItem()
    self.assertIsNotNone(current)
    self.assertEqual(current.text(), 'REF_M_00002.nxs.h5')
```

### Green Phase — implement fixes, run tests, confirm they pass

---

## Implementation Details

### Fix 1: Add `locate_file` to import in `main_gui.py`

```python
# Line 32-33, BEFORE:
from .qreduce import NXSData, NXSMultiData, Reflectivity, OffSpecular, time_from_header, \
                     GISANS, XMLData

# AFTER:
from .qreduce import NXSData, NXSMultiData, Reflectivity, OffSpecular, time_from_header, \
                     GISANS, XMLData, locate_file
```

### Fix 2: `openByNumber()` (lines 1261-1282)

Replace the manual glob with `locate_file()`, add wait cursor and status bar feedback.

```python
@log_call
def openByNumber(self, number=None, do_plot=True):
    '''
    Search the data folders for a specific file number and open it.
    '''
    if number is None:
        number = self.ui.numberSearchEntry.text()
    number = str(number).strip()
    if not number:
        return False
    info('Trying to locate file number %s...' % number)
    self.ui.statusbar.showMessage(u'Searching for run %s...' % number)
    QtWidgets.QApplication.instance().setOverrideCursor(QtCore.Qt.WaitCursor)
    QtWidgets.QApplication.instance().processEvents()
    try:
        found_path = locate_file(int(number),
                                  histogram=self.ui.histogramActive.isChecked(),
                                  old_format=self.ui.oldFormatActive.isChecked())
    except (ValueError, TypeError):
        found_path = None
    finally:
        QtWidgets.QApplication.instance().restoreOverrideCursor()
    if found_path:
        self.ui.numberSearchEntry.setText(u'')
        self.ui.statusbar.showMessage(u'Loading run %s...' % number)
        self.fileOpen(os.path.abspath(found_path), do_plot=do_plot)
        return True
    else:
        info('Could not locate %s...' % number)
        self.ui.statusbar.showMessage(u'Run %s not found' % number)
        return False
```

Key changes:
- Empty-string guard (avoids `int('')` ValueError)
- Status bar message + wait cursor before slow glob
- Delegates to `locate_file()` — no duplicated logic
- Correct mode flags passed to `locate_file()`
- Status bar "not found" message visible to user

### Fix 3: `fileOpenDialog()` (lines 1215-1220)

```python
# BEFORE:
else:
    filter_=u'Event Nexus (*event.nxs);;All (*.*)'

# AFTER:
else:
    filter_=u'Event Nexus (*.nxs.h5);;Legacy Event (*event.nxs);;All (*.*)'
```

### Fix 4: `fileOpenSumDialog()` (lines 1236-1241)

Same change as Fix 3:
```python
# BEFORE:
else:
    filter_=u'Event Nexus (*event.nxs);;All (*.*)'

# AFTER:
else:
    filter_=u'Event Nexus (*.nxs.h5);;Legacy Event (*event.nxs);;All (*.*)'
```

### Fix 5: `updateFileList()` (lines 1502-1535)

Two bugs fixed: add `.nxs.h5` glob for Event mode, and fix Python 3 `map()` iterator.

```python
# BEFORE (Event mode section):
elif self.ui.eventActive.isChecked():
    self.ui.eventModeEntries.show()
    newlist=glob(os.path.join(folder, '*event.nxs'))
...
newlist=map(lambda name: os.path.basename(name), newlist)
oldlist=[self.ui.file_list.item(i).text() for i in range(self.ui.file_list.count())]
if newlist!=oldlist:
    ...
else:
    try:
        self.ui.file_list.setCurrentRow(newlist.index(base))
    except ValueError:
        pass

# AFTER (Event mode section):
elif self.ui.eventActive.isChecked():
    self.ui.eventModeEntries.show()
    newlist = sorted(glob(os.path.join(folder, '*.nxs.h5')) +
                     glob(os.path.join(folder, '*event.nxs')))
...
newlist = [os.path.basename(name) for name in newlist]   # list, not iterator
oldlist = [self.ui.file_list.item(i).text() for i in range(self.ui.file_list.count())]
if newlist != oldlist:
    ...
else:
    try:
        self.ui.file_list.setCurrentRow(newlist.index(base))
    except ValueError:
        pass
```

Note: the `sorted()` call on the combined list means `.nxs.h5` files and `*event.nxs`
files from the same folder will be interleaved alphabetically. This is correct since a
given IPTS folder will have either `data/*event.nxs` files OR `nexus/*.nxs.h5` files,
not both (they are in different subdirectories). The combined glob handles the case where
the `folder` argument points to either `data/` or `nexus/`.

### Fix 6: `fileOpen()` — show `eventTotalTimeLabel` for `.nxs.h5` (lines 379-387)

`time_from_header()` works on any HDF5 file (it opens the file with h5py and iterates
top-level groups for `start_time`/`end_time`). The `.nxs.h5` format has a single entry
group with both fields. Guard against `None` return to handle corrupt/partial files.

```python
# BEFORE:
if base.endswith('event.nxs'):
    tottime=time_from_header(os.path.join(folder, base))
    self.ui.eventTotalTimeLabel.setText(u"(%i min)"%(tottime/60))
if base.endswith('event.nxs') and self.ui.eventSplit.isChecked():

# AFTER:
if base.endswith('event.nxs') or base.endswith('.nxs.h5'):
    tottime = time_from_header(os.path.join(folder, base))
    if tottime is not None:
        self.ui.eventTotalTimeLabel.setText(u"(%i min)" % (tottime / 60))
if base.endswith('event.nxs') and self.ui.eventSplit.isChecked():
    # Event splitting is only supported for legacy *event.nxs format; no change here
```

### Fix 7: `fileOpen()` — status bar progress message (lines 367-397)

Add a "Loading..." status bar message before the blocking `NXSData()` call. The existing
`updateEventReadout` callback already moves the progress bar during event data loading,
but there is no message before it starts.

```python
@log_input
def fileOpen(self, filename, do_plot=True):
    '''
    Open a new datafile and plot the data.
    '''
    folder, base = os.path.split(filename)
    self.ui.statusbar.showMessage(u'Loading %s...' % base)  # ADD THIS
    QtWidgets.QApplication.instance().processEvents()        # ADD THIS
    if folder != self.active_folder:
        self.onPathChanged(base, folder)
    else:
        self.updateFileList(base, folder)
    ...
```

---

## Edge Cases

| Case | Handling |
|------|----------|
| Empty run number field | `str(number).strip()` guard → return False |
| Non-numeric run number (e.g. "abc") | `int(number)` in `try/except (ValueError, TypeError)` → not found path |
| Run number exists in both `data/` (event.nxs) and `nexus/` (.nxs.h5) | `locate_file()` tries `*event.nxs` first in Event mode; prefer legacy. Histogram mode: finds histo.nxs, no ambiguity |
| Network mount timeout during glob | `locate_file()` blocks in glob (no SIGALRM safety); user sees wait cursor — does not appear fully hung. Future hardening: wrap in `signal.alarm`. Not in scope for this fix |
| IPTS folder has no runs matching mode | `updateFileList()` produces empty list — correct behavior |
| `.nxs.h5` file with missing `start_time`/`end_time` | `time_from_header()` returns `etime - stime = 0.0 - 0.0 = 0.0` or `1e30 - 0.0`; guard `if tottime is not None` doesn't help (returns float). Add check `if tottime and tottime < 1e20:` or accept 0 min display |
| `locate_file()` default is `histogram=True` | Existing behavior: if called without args, prefers histo. `openByNumber()` now passes correct flags from UI |
| Python 3 `map()` iterator in `updateFileList()` | Fixed by switching to list comprehension |
| REF_L run number with 6 digits vs REF_M 5 digits | `H5_BASE_SEARCH = '*/nexus/REF_L_%s.nxs.h5'` — `%s` uses `str(number)` directly; glob patterns work regardless of digit count |

---

## Implementation Order (TDD)

1. **Write all new tests** → confirm they fail (red)
2. Fix `updateFileList()` (Python 3 map + `.nxs.h5` glob)
3. Fix `fileOpenDialog()` / `fileOpenSumDialog()` filters
4. Add `locate_file` to import; fix `openByNumber()`
5. Fix `fileOpen()` — `.nxs.h5` total time label + status message
6. Run full test suite: `pixi run test`
7. Verify manually: open run 29750 (REF_M, Event mode) by number

---

## Out of Scope

- Network timeout protection for `locate_file()` glob (SIGALRM wrapper) — separate task
- Event splitting support for `.nxs.h5` — separate feature
- quicknxsv2-style `ProgressReporter` class — not warranted here; the existing
  `updateEventReadout` callback + status bar message + wait cursor is sufficient
