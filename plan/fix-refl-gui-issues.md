# Plan: Fix REF_L GUI Issues (Post-Integration)

## Issues Observed

### Issue 1: Silent failure when loading non-existent run 70476
The file `/SNS/REF_L/IPTS-7053/data/REF_L_70476_histo.nxs` is a broken symlink. When opened:
- `_read_file()` catches the `IOError` and logs at **DEBUG** level only (line 268)
- `NXSData.__new__()` returns `None` (line 234)
- `_fileOpenDone()` detects `None` and sets the UI label to `!!!NO DATA IN FILE!!!` but **never logs** (line 395-397)
- The user sees no response and no log entry at ERROR or WARNING level

### Issue 2: CRITICAL crash when loading valid run 83586
```
File "quicknxs/qcalc.py", line 109, in get_xpos
    raise ValueError("'data' needs to be a MRDataset object")
```
- `get_xpos()` uses `type(data) is not MRDataset` — strict identity check
- `LRDataset` inherits from `MRDataset` and has all the same attributes
- Same issue exists in `get_yregion()` (line 170-171)
- `calcReflParams()` in `main_gui.py:2274` calls `get_xpos` after file load, triggering the crash

### Issue 3: REF_M-specific UI labels displayed for REF_L
The screenshot shows labels like SANGLE, DANGLE, DANGLE0 which are REF_M motor names.
- REF_L uses "TwoTheta" (≈DANGLE) and "Theta" (≈SANGLE) internally
- REF_L has no DANGLE0 concept (always 0.0)
- Labels are hardcoded in both `.ui` files and generated `.py` interface files
- The underlying data attributes (`.sangle`, `.dangle`, `.dangle0`, `.dpix`) are identical
  in both `MRDataset` and `LRDataset` — only the display names differ

---

## Proposed Changes

### Change 1: Add ERROR logging when file load fails

**Files:** `quicknxs/qreduce.py`, `quicknxs/main_gui.py`

**1a.** In `_read_file()` (qreduce.py:267-269), upgrade IOError logging from `debug` to `warning`:
```python
except IOError:
    warning('Could not read nxs file %s'%filename, exc_info=True)
    return False
```

**1b.** In `_fileOpenDone()` (main_gui.py:395-397), add an ERROR log entry when data is None:
```python
if data is None:
    from logging import error
    error('Failed to load file: %s'%base)
    self.ui.currentChannel.setText(u'<b>!!!NO DATA IN FILE %s!!!</b>'%base)
    return
```

This ensures every failed load produces a visible log entry in `~/.quicknxs/debug.log`.

### Change 2: Fix type checks in qcalc.py to accept LRDataset

**File:** `quicknxs/qcalc.py`

**2a.** In `get_xpos()` (line 108-109), change strict type check to isinstance:
```python
if not isinstance(data, MRDataset):
    raise ValueError("'data' needs to be a MRDataset or LRDataset object")
```

**2b.** In `get_yregion()` (line 170-171), same fix:
```python
if not isinstance(data, MRDataset):
    raise ValueError("'data' needs to be a MRDataset or LRDataset object")
```

Since `LRDataset` inherits from `MRDataset`, `isinstance(lr_data, MRDataset)` returns `True`.
Both functions use attributes (`xdata`, `xydata`, `dangle`, `sangle`, `dpix`, etc.) that
`LRDataset` inherits unchanged, so no logic changes are needed.

### Change 3: Make UI labels instrument-aware at runtime

**File:** `quicknxs/main_gui.py`

Rather than modifying the `.ui` files (which would require regenerating the Python interface
files), set the label text dynamically after the UI loads, based on the active instrument.

**3a.** Add a method to `MainGUI` that updates instrument-specific labels:
```python
def _updateInstrumentLabels(self):
    '''Update UI labels based on the active instrument.'''
    from .config import instrument
    if instrument.NAME == 'REF_L':
        self.ui.trustDANGLE.setText('TwoTheta')
        self.ui.trustSANGLE.setText('Theta')
        # Update display labels
        for widget_name, text in [
            ('label_DANGLE', 'TwoTheta'),     # detector angle label
            ('label_SANGLE', 'Theta'),          # sample angle label
            ('label_15', 'TwoTheta₀'),          # DANGLE0 label
            ('label_SANGLE_calc', 'Theta-calc'), # calculated sample angle
        ]:
            widget = getattr(self.ui, widget_name, None)
            if widget is not None:
                widget.setText(text)
```

NOTE: The exact widget names for the column-header labels need to be confirmed by
inspecting the generated interface code. The `.ui` files use generic names like
`label_19`, `label_15` — I'll identify each by its current text content.

**3b.** Call `_updateInstrumentLabels()` from `__init__` after the UI is set up.

**3c.** Update tooltips for REF_L context where they reference DANGLE0 or SANGLE.

### Change 4: Add tests

**File:** `tests/qreduce_test.py`

- Test that `get_xpos()` accepts `LRDataset` without raising `ValueError`
- Test that `get_yregion()` accepts `LRDataset` without raising `ValueError`

---

## Execution Order (Red/Green TDD)

```
Step 1: RED  — Write test: get_xpos with LRDataset raises ValueError
               Run: pixi run pytest tests/qreduce_test.py -k "get_xpos" → FAIL

Step 2: GREEN — Apply Change 2 (isinstance fix in qcalc.py)
                Run: pixi run pytest tests/qreduce_test.py -k "get_xpos" → PASS

Step 3: Apply Change 1 (error logging)
        Verify: Load broken symlink → ERROR appears in debug.log

Step 4: Apply Change 3 (instrument-aware labels)
        Verify: make gui INSTRUMENT=ref_l → labels show TwoTheta/Theta

Step 5: Full test suite: pixi run pytest tests/qreduce_test.py → all pass

Step 6: Integration test:
        make gui INSTRUMENT=ref_l → load run 83586 → no crash, data displays
        make gui INSTRUMENT=ref_m → regression check
```

---

## Files Modified

| File | Change |
|------|--------|
| `quicknxs/qreduce.py` | Upgrade IOError log from debug→warning |
| `quicknxs/main_gui.py` | Add ERROR log in _fileOpenDone; add _updateInstrumentLabels |
| `quicknxs/qcalc.py` | isinstance checks in get_xpos and get_yregion |
| `tests/qreduce_test.py` | Tests for get_xpos/get_yregion with LRDataset |

## Files NOT Modified

| File | Reason |
|------|--------|
| `designer/*.ui` | Labels changed at runtime via Python, not in XML |
| `quicknxs/*_interface.py` | Generated from .ui files — no manual edits |
| `quicknxs/config/ref_l.py` | No new config entries needed |

## Risks and Considerations

1. **get_xpos peak-finding**: The algorithm was designed for REF_M geometry. It should work
   for REF_L since `LRDataset` inherits the same `xdata`, `xydata`, and angle attributes,
   but the peak shapes may differ. If peak-finding produces poor results on REF_L data,
   that's a follow-up tuning issue, not a crash.

2. **Label widget names**: The `.ui` files use auto-generated names like `label_19`. I need
   to map from displayed text ("DANGLE", "SANGLE") to widget object names. I'll do this
   by reading the generated Python interface code.

3. **DANGLE0 for REF_L**: REF_L always has `dangle0=0.0`. The DANGLE0 override input and
   display could be hidden for REF_L, but for this iteration I'll just relabel it to
   "TwoTheta₀" and leave it functional (it's harmless at 0.0).
