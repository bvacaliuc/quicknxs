# Plan: Fix OOM Crash (Exit 137) During Off-Specular Smoothing Reduction

## Context

After the previous fix (cursor ValueError + drawPlot try/finally), the application still crashes with exit code 137 during or shortly after completing the smoothing operation. The `strace` output confirms: the pixi wrapper process is killed by SIGKILL (128 + 9 = 137), which on Linux means the **OOM killer** terminated the process for exceeding available memory.

The previous commit (`ed20cf3`) fixed the ValueError cascade that corrupted `_last_cursor` and left `SmoothDialog.drawing` stuck. This plan addresses the **separate, underlying memory exhaustion** that causes the OOM kill.

## Root Cause: Cumulative Memory Pressure

The reduction pipeline (`Reducer.execute()`) keeps ALL data alive simultaneously:

| Data resident in memory | Est. size | When freed |
|---|---|---|
| `Exporter.raw_data` — full 3D detector arrays (304×256×150) per dataset per channel | **1–2 GB** | Never (until Exporter is GC'd) |
| `output_data['OffSpec']` — extracted off-specular arrays | 50–100 MB | Only if `not exportOffSpecular` |
| `output_data['OffSpecSmooth']` — smoothed output | 10–50 MB | Never |
| `hstack` + `flatten` temporaries inside `smooth_offspec()` | 50–100 MB | End of loop iteration |
| Matplotlib rendered figures (MainGUI MPLWidgets) | 50–200 MB | Never |

**Peak total: 1.5–3+ GB**, enough to trigger the OOM killer on a 4–8 GB system.

The critical insight: `raw_data` is only needed during extraction steps. By the time `smooth_offspec()` runs (the most memory-intensive stage), raw_data has already been fully consumed but is never released.

## Pipeline Flow Analysis

```
Reducer.execute() — gui_utils.py:78
  ├─ Exporter.__init__() calls read_data()          ← loads raw_data (~1-2 GB)
  ├─ read_data() called AGAIN (redundant)            ← line 89, double-read
  ├─ extract_reflectivity()                          ← uses raw_data
  ├─ extract_offspecular()                           ← uses raw_data
  ├─ extract_offspecular_corr()                      ← uses raw_data
  ├─ smooth_offspec()                                ← does NOT use raw_data!
  │   ├─ SmoothDialog (user picks params)
  │   ├─ ProgressDialog.show()
  │   └─ Exporter.smooth_offspec(settings, pb)       ← qio.py:723
  │       ├─ np.hstack(odata[channel])               ← COPY #1
  │       ├─ .flatten() ×3                           ← COPIES #2-4
  │       ├─ smooth_data(x, y, I, callback=pb)       ← qcalc.py:244
  │       │   └─ callback → processEvents()          ← GC interference
  │       └─ np.array([x,y,I]).transpose()           ← COPY #5
  ├─ extract_gisans()                                ← uses raw_data
  └─ export_data()                                   ← does NOT use raw_data
```

## Implementation Steps

Steps are ordered by memory impact. Each is independently testable.

---

### Step 1: Release raw_data before smoothing (highest impact, ~1–2 GB saved)

**Files:** `quicknxs/gui_utils.py` (Reducer.execute), `quicknxs/qio.py` (Exporter)

**Problem:** `Exporter.raw_data` holds ~1–2 GB of 3D detector arrays throughout the entire pipeline, including during the memory-intensive smoothing phase where it is not needed.

**Changes:**

1. **Add `Exporter.release_raw_data()` method** in `qio.py` after line 607:
   ```python
   def release_raw_data(self):
       '''Release raw data to free memory after all extractions are complete.'''
       self.raw_data.clear()
       import gc; gc.collect()
   ```

2. **Reorder `extract_gisans()` before `smooth_offspec()` in `Reducer.execute()`** (gui_utils.py:78–132). GISANS extraction uses `raw_data`; smoothing does not. Moving GISANS before smoothing allows releasing raw_data before the memory-intensive phase. Both operations involve user dialogs (modal `exec_()`), so they are independent. The new order:
   ```python
   # All extraction steps that need raw_data:
   if opts['exportSpecular']:
       self.exporter.extract_reflectivity()
   if opts['exportOffSpecular'] or opts['exportOffSpecularSmoothed']:
       self.exporter.extract_offspecular()
   if opts['exportOffSpecularCorr']:
       self.exporter.extract_offspecular_corr()
   if opts['exportGISANS']:
       self.extract_gisans()                           # MOVED UP: needs raw_data

   # Raw data no longer needed — release it
   self.exporter.release_raw_data()

   # Memory-intensive smoothing runs with ~1-2 GB freed:
   if opts['exportOffSpecularSmoothed']:
       self.smooth_offspec()
       if not opts['exportOffSpecular']:
           del(self.exporter.output_data['OffSpec'])
   ```

3. **Remove the redundant `read_data()` call** on line 89 of `execute()`. `Exporter.__init__()` already calls `self.read_data()` (qio.py:582), so the explicit call in `execute()` is a double-read.

**Verification:** `make test` — `ExportTest.test_create_data` in tests/qio_test.py exercises the full extract→smooth pipeline via `Exporter` directly. Add a new test that calls `release_raw_data()` between extraction and smoothing.

---

### Step 2: Delete intermediate arrays in smooth_offspec() (~100–200 MB saved)

**File:** `quicknxs/qio.py` — `Exporter.smooth_offspec()` at line 723

**Problem:** `np.hstack()` creates a full copy of the channel data, and 3× `.flatten()` calls create additional copies. The `hstack` copy persists alongside the flattened arrays through the entire `smooth_data()` call.

**Changes:** Add `del` statements to release intermediate arrays as soon as they are consumed:

```python
for i, channel in enumerate(self.channels):
    # ... pb setup ...
    data=np.hstack(odata[channel])
    I=data[:, :, 5].flatten()
    Qzmax=data[:, :, 2].max()*2.
    if settings['xy_column']==0:
        x=data[:, :, 4].flatten()
        y=data[:, :, 1].flatten()
        # ...
    elif settings['xy_column']==1:
        x=data[:, :, 0].flatten()
        y=data[:, :, 1].flatten()
        # ...
    else:
        x=data[:, :, 2].flatten()
        y=data[:, :, 3].flatten()
        # ...
    del data                          # ← ADD: release hstack copy before smoothing
    x, y, I=smooth_data(...)
    output_data[channel]=[np.array([x, y, I]).transpose((1, 2, 0))]
    del x, y, I                       # ← ADD: release before next channel iteration
```

**Verification:** `make test` — `ExportTest.test_create_data` tests all 3 `xy_column` values.

---

### Step 3: Add try/finally guards for resource cleanup

**File:** `quicknxs/gui_utils.py`

**Problem A:** `Reducer.smooth_offspec()` (line 214) creates a `ProgressDialog` that is never destroyed if an exception occurs during `Exporter.smooth_offspec()`.

**Fix:** Wrap in try/finally:
```python
@log_call
def smooth_offspec(self):
    data=self.exporter.output_data['OffSpec'][self.channels[0]]
    dia=SmoothDialog(self._parent_window, data)
    if not dia.exec_():
        dia.destroy()
        return
    settings=dia.getOptions()
    dia.destroy()
    pbinfo="Smoothing Channel "
    pb=ProgressDialog(self._parent_window, title="Smoothing",
                      info_start=pbinfo+self.channels[0],
                      maximum=100*len(self.channels))
    pb.show()
    try:
        self.exporter.smooth_offspec(settings, pb)
    finally:
        pb.destroy()
```

**Problem B:** `Reducer.execute()` (line 78) has no cleanup if an exception occurs mid-pipeline. The Exporter and its large data structures leak.

**Fix:** Wrap the pipeline body in try/finally to ensure cleanup:
```python
def execute(self):
    opts=self.export_optios
    # ...
    self.exporter=Exporter(...)
    try:
        # ... entire extraction/smoothing/export pipeline ...
    finally:
        if hasattr(self, 'exporter') and hasattr(self.exporter, 'raw_data'):
            self.exporter.release_raw_data()
```

**Verification:** `make test`. Add a test that patches `smooth_offspec` to raise, verifying `pb.destroy()` is still called.

---

### Step 4: Throttle processEvents() during smoothing

**File:** `quicknxs/gui_utils.py` — `ProgressDialog` class at line 1036

**Problem:** `processEvents()` is called every 5 outer loop iterations (40 times for a 200-row grid). Each call processes the full Qt event queue, which can trigger matplotlib canvas repaints on visible MainGUI widgets, interfere with GC, and add latency.

**Fix:** Throttle to at most once per 200ms using `time.monotonic()`:
```python
import time

class ProgressDialog(QDialog):
    def __init__(self, parent, title='', info_start='', maximum=100, add=0):
        QDialog.__init__(self, parent)
        self.add=add
        self._last_process_time=0
        # ... rest unchanged ...

    def progress(self, value):
        param=value*100+self.add
        self.progressBar.setValue(int(param))
        now=time.monotonic()
        if now - self._last_process_time > 0.2:
            app=QApplication.instance()
            app.processEvents()
            self._last_process_time=now
```

**Verification:** `make test` — `MainGUIProgressDialogFix` tests exercise `ProgressDialog.progress()`. Manual test: confirm progress bar still updates visually.

---

### Step 5: Add tests

**File:** `tests/qio_test.py` — `ExportTest` class

**New tests:**

1. **`test_release_raw_data`**: Call `Exporter.release_raw_data()` after extractions, verify `raw_data` is empty, then call `smooth_offspec()` — must succeed since smoothing only uses `output_data`.

2. **`test_smooth_after_release`**: Full pipeline: extract → release_raw_data → smooth → verify output arrays have expected shape.

**File:** `tests/main_gui_test.py`

3. **`test_smooth_offspec_progress_cleanup`**: Patch `Exporter.smooth_offspec` to raise, verify ProgressDialog is destroyed (via `Reducer.smooth_offspec()` try/finally).

4. **`test_progress_dialog_throttle`**: Call `progress()` rapidly, verify `processEvents()` is called fewer times than `progress()`.

---

## Files to Modify

| File | Changes |
|---|---|
| `quicknxs/qio.py` | Add `release_raw_data()` method; add `del data` and `del x, y, I` in `smooth_offspec()` |
| `quicknxs/gui_utils.py` | Reorder GISANS before smoothing in `execute()`; remove redundant `read_data()` call; add try/finally in `smooth_offspec()` and `execute()`; throttle `processEvents()` in `ProgressDialog` |
| `tests/qio_test.py` | Add `test_release_raw_data` and `test_smooth_after_release` |
| `tests/main_gui_test.py` | Add `test_smooth_offspec_progress_cleanup` and `test_progress_dialog_throttle` |

## Verification

```bash
make test  # All tests pass, no hangs
```

For real-world validation: run the full reduction with off-specular smoothing on actual MR reflectometer data and confirm:
1. No OOM kill (process completes)
2. Output files are identical to pre-change output
3. Progress bar updates visibly during smoothing
