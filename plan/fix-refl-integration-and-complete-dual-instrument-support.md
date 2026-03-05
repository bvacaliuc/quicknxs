# Plan: Fix REF_L Integration and Complete Dual-Instrument Support

## Context

Launching `pixi run python scripts/quicknxs --instrument ref_l` crashes with a KeyError
at module import time. The root cause is that our previous implementation used
`_get_instrument_constant('ANALYZER_IN', default)` at module scope in `qreduce.py`, which
calls `getattr(instrument, 'ANALYZER_IN', default)`. The ConfigHolder's `__getattribute__`
routes to `__getitem__` → `get_config_item`, which raises `KeyError` (not `AttributeError`)
when the key is missing. Python's `getattr()` only catches `AttributeError`, so the
`KeyError` propagates and crashes.

This reveals that the previous "minimal edits" approach was naive: it tried to share
REF_M-specific constants (analyzer/polarizer positions) across both instruments via a
fallback mechanism, but the config proxy's error handling makes that impossible without
modifying the config infrastructure itself.

The correct approach is to recognize that `ANALYZER_IN`, `NEW_ANALYZER_IN`, `POLARIZER_IN`,
and `SUPERMIRROR_IN` are **exclusively REF_M hardware constants** that have no meaning for
REF_L. They should be accessed only within REF_M code paths, not at module scope.

## Assessment: Was the Minimal-Edit Approach Naive?

**Yes.** The key mistakes were:

1. **Module-scope constant initialization** — Constants frozen at import time cannot adapt
   to runtime instrument switching. The config system was designed for lazy access, not
   eager initialization.

2. **Assuming `getattr()` would catch config errors** — The ConfigHolder raises `KeyError`,
   not `AttributeError`, making `getattr(obj, name, default)` useless as a fallback.

3. **Treating REF_M hardware constants as shared** — `ANALYZER_IN` et al. describe physical
   hardware (analyzer lift, polarizer) that REF_L does not have. These should never be
   accessed from a REF_L code path.

4. **Not auditing all instrument-dependent code** — The `auto_reflectivity.py` file has a
   hardcoded `'REF_M_autorefl.com'` string that was missed.

---

## Approach: Access Constants at Point-of-Use, Not Module Scope

Remove the 5 module-level constant assignments from `qreduce.py`. Instead, access them
from the `instrument` config object at the point where they're used. Since these constants
are only used inside REF_M code paths (`_read_file_MR`, `XMLData._read_file`,
`is_analyzer_in`), the config will always be `ref_m` when they're accessed.

Keep a safe helper `_get_instrument_constant(name, default)` for `_correct_sensitivity()`
which is called for both instruments and needs POLY_CORR_PARAMS with a fallback.

---

## Change 1: Remove module-level constants from qreduce.py

**File:** `quicknxs/qreduce.py`

### 1a. Replace lines 42–55

Remove the `_get_instrument_constant` function and all 5 module-level constant assignments.
Replace with a safe helper that catches KeyError:

```python
def _get_instrument_config(name, default=None):
    '''Safely read an instrument config constant, returning default if missing.

    ConfigHolder raises KeyError (not AttributeError) for missing keys,
    so getattr()'s default parameter does not work. This helper catches both.
    '''
    try:
        return instrument[name]
    except KeyError:
        return default
```

### 1b. Update `_read_file_MR()` — lines 351, 358–359

These are inside the REF_M code path (only called for beamline 4A). Replace bare constant
references with `instrument.CONSTANT_NAME`:

```python
# line 351: was is_analyzer_in(ana, ana_trans, start_time_str)
# is_analyzer_in() itself will be updated (see 1d below)

# lines 358-359: replace POLARIZER_IN and SUPERMIRROR_IN
elif abs(pol-instrument.POLARIZER_IN[0])<instrument.POLARIZER_IN[1] or \
     abs(smpt-instrument.SUPERMIRROR_IN[0])<instrument.SUPERMIRROR_IN[1]:
```

### 1c. Update `XMLData._read_file()` — lines 728, 735–736

Same pattern as 1b:

```python
# line 728
if abs(ana-instrument.ANALYZER_IN[0])<instrument.ANALYZER_IN[1]:

# lines 735-736
elif abs(pol-instrument.POLARIZER_IN[0])<instrument.POLARIZER_IN[1] or \
     abs(smpt-instrument.SUPERMIRROR_IN[0])<instrument.SUPERMIRROR_IN[1]:
```

### 1d. Update `is_analyzer_in()` — lines 1527–1546

Read from `instrument` config instead of module-level constants:

```python
def is_analyzer_in(position, trans_position, start_time_str):
    analyzer_in = instrument.ANALYZER_IN
    new_analyzer_in = instrument.NEW_ANALYZER_IN
    result = abs(position - analyzer_in[0]) < analyzer_in[1]
    try:
        date_str = start_time_str.split('T')[0]
        parts_str = date_str.split('-')
        year_month_int = int("%s%s" % (parts_str[0], parts_str[1]))
        if year_month_int >= 201708:
            result = abs(trans_position - new_analyzer_in[0]) < new_analyzer_in[1]
    except Exception:
        warn("Problem parsing start time: use more recent definition for analyzer position")
        result = abs(trans_position - new_analyzer_in[0]) < new_analyzer_in[1]
    return result
```

### 1e. Update `_correct_sensitivity()` — line 1756

Change from `_get_instrument_constant('POLY_CORR_PARAMS', POLY_CORR_PARAMS)` to:

```python
poly_params = _get_instrument_config('POLY_CORR_PARAMS')
```

This returns `None` for REF_L (which defines `POLY_CORR_PARAMS=None`) and the existing
`if poly_params is None: warn(); return data` handles it.

---

## Change 2: Fix hardcoded REF_M in auto_reflectivity.py

**File:** `quicknxs/auto_reflectivity.py`, line 50

The class attribute `bind_path` is evaluated at class definition time (import time), when
the instrument may not be configured yet. Move to `__init__`:

```python
class FileCom(Thread):
    # Remove class-level bind_path
    parent = None
    MAX_READ_TIME = 1
    daemon = True
    last_com = 0.

    def __init__(self, parent):
        Thread.__init__(self, name='FileCom')
        self.parent = parent
        self.bind_path = instrument.autorefl_folder + instrument.NAME + '_autorefl.com'
        self.quit = Event()
        self.quit.clear()
```

---

## Change 3: Extend Makefile

**File:** `Makefile`

### 3a. Add INSTRUMENT parameter to `gui` target

```makefile
INSTRUMENT ?= ref_m

gui: install
	pixi run python scripts/quicknxs --instrument $(INSTRUMENT)
```

### 3b. Add `load-test` target (single file)

```makefile
load-test: install
	@test -n "$(FILE)" || (echo "Usage: make load-test FILE=/path/to/file.nxs"; exit 1)
	pixi run python scripts/load_test.py --file "$(FILE)"
```

### 3c. Add `batch-load-test` target (directory scan)

```makefile
batch-load-test: install
	@test -n "$(DIR)" || (echo "Usage: make batch-load-test DIR=/path/to/data/"; exit 1)
	pixi run python scripts/load_test.py --dir "$(DIR)" $(if $(PATTERN),--pattern "$(PATTERN)",)
```

Example usage:
```bash
make gui INSTRUMENT=ref_l
make load-test FILE=/SNS/REF_L/IPTS-7053/data/REF_L_70476_histo.nxs
make batch-load-test DIR=/SNS/REF_L/IPTS-7053/data/ PATTERN="*_histo.nxs"
make batch-load-test DIR=/SNS/REF_M/IPTS-16196/data/ PATTERN="*_event.nxs"
```

---

## Change 4: Create load_test.py script

**File:** `scripts/load_test.py` (new)

A standalone CLI tool that loads NXS files and reports:
- Instrument detection (beamline 4A/4B → REF_M/REF_L)
- Dataset class (MRDataset/LRDataset)
- Channel count and measurement type
- Array shapes (data, xydata, xtofdata)
- Key metadata (run#, lambda_center, angles, distances, proton_charge, counts)
- PASS/FAIL per file

Modes:
- `--file PATH` — single file test
- `--dir PATH [--pattern GLOB]` — batch directory scan
- `--refl` — also extract Reflectivity and report Q range

Exit code 0 if all files pass, 1 if any fail.

---

## Change 5: Add tests

**File:** `tests/qreduce_test.py`

### 5a. InstrumentConfigTests class

Tests that verify the config system works for both instruments without crashing:

- `test_ref_l_config_no_crash` — Switch instrument to ref_l, call
  `_get_instrument_config('ANALYZER_IN')`, verify it returns None (not crash)
- `test_ref_l_config_poly_corr_none` — Verify ref_l's POLY_CORR_PARAMS is None
- `test_ref_m_constants_accessible` — Verify ref_m's ANALYZER_IN, POLARIZER_IN, etc.
  are accessible and have expected values

### 5b. Data load verification tests

- `test_lr_load_multiple_runs` — Load 3–5 different REF_L files from
  `/SNS/REF_L/IPTS-7053/data/`, verify each returns a valid NXSData with LRDataset
- `test_mr_load_multiple_runs` — Load 3–5 different REF_M files from
  `/SNS/REF_M/IPTS-16196/data/` (if accessible), verify each returns MRDataset
- `test_lr_event_mode_load` — Load an event-mode REF_L file from
  `/SNS/REF_L/IPTS-7053/data/`, verify the LRDataset is created correctly
- These tests should be marked with `@unittest.skipUnless(os.path.exists(...))` so
  they skip gracefully on CI where SNS data is not available

---

## Execution Order (Red/Green TDD)

```
Step 1: RED  — Write InstrumentConfigTests.test_ref_l_config_no_crash
               Run: pixi run pytest tests/qreduce_test.py -k "config" → FAIL (KeyError)

Step 2: GREEN — Apply Changes 1a–1e to qreduce.py
                Run: pixi run pytest tests/qreduce_test.py -k "config" → PASS

Step 3: VERIFY — Run full test suite: pixi run pytest tests/qreduce_test.py → all pass

Step 4: Apply Change 2 (auto_reflectivity.py fix)

Step 5: Apply Change 3 (Makefile extensions)

Step 6: Apply Change 4 (create load_test.py)

Step 7: Write remaining tests (5b: data load verification)

Step 8: Integration test:
        make gui INSTRUMENT=ref_l            → launches without crash
        make load-test FILE=tests/test_refl_histo.nxs  → PASS
        make load-test FILE=tests/test1_histo.nxs      → PASS
        make batch-load-test DIR=/SNS/REF_L/IPTS-7053/data/ PATTERN="*80836*"
```

---

## Files Modified

| File | Change |
|------|--------|
| `quicknxs/qreduce.py` | Remove module-level constants; access from config at point-of-use |
| `quicknxs/auto_reflectivity.py` | Fix hardcoded REF_M name; move `bind_path` to `__init__` |
| `Makefile` | Add INSTRUMENT param, load-test, batch-load-test targets |
| `scripts/load_test.py` | New: data load verification CLI script |
| `tests/qreduce_test.py` | Add InstrumentConfigTests and data load verification tests |

## Files NOT Modified (verified correct)

| File | Status |
|------|--------|
| `quicknxs/config/ref_m.py` | Already has all REF_M constants |
| `quicknxs/config/ref_l.py` | Already complete with REF_L config |
| `scripts/quicknxs` | Entry point already correct |
| `quicknxs/config/baseconfig.py` | Config infrastructure unchanged |

## Verification Checklist

1. `pixi run pytest tests/qreduce_test.py` — all tests pass (REF_M + REF_L + config)
2. `make gui INSTRUMENT=ref_l` — launches without crash
3. `make gui INSTRUMENT=ref_m` — launches without crash (regression)
4. `make load-test FILE=tests/test_refl_histo.nxs` — PASS
5. `make load-test FILE=tests/test1_histo.nxs` — PASS
6. `make batch-load-test DIR=/SNS/REF_L/IPTS-7053/data/ PATTERN="*80836*"` — PASS
7. `make lint` — no new lint errors

## Available Test Data

| Source | Count | Types |
|--------|-------|-------|
| `tests/test1_histo.nxs` | 1 | REF_M histogram (10 MB, 4 entries) |
| `tests/test1_event.nxs` | 1 | REF_M event (13 MB) |
| `tests/test_refl_histo.nxs` | 1 | REF_L histogram (2.5 MB, 1 entry) |
| `/SNS/REF_L/IPTS-7053/data/` | 5018 | 2509 histo + 2509 event |
| `/SNS/REF_M/IPTS-16196/data/` | ~946 | histo + event |
