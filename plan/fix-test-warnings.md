# Fix: Test Warning Investigation and Mitigation

## Summary

Running `make test` produced 2 visible warnings. Investigation revealed these were
the tip of an iceberg: 26+ instances of unclosed file handles (`ResourceWarning`)
were silently suppressed by default Python settings. With strict warning mode
(`-W error`), 65 tests would fail.

## Root Cause Analysis

### Visible Warnings (cosmetic, upstream libraries)

| Warning | Location | Cause | Fix |
|---------|----------|-------|-----|
| `PytestCollectionWarning` | `numpy/_pytesttester.py:79` | numpy exposes `numpy.test` (a `PytestTester` object); pytest tries to collect it as a test item | Suppress in pytest `filterwarnings` |
| `PendingDeprecationWarning` | `ipykernel/kernelbase.py:957` | ipykernel 7.x warns its own `InProcessKernel.do_history` is not async | Suppress in pytest `filterwarnings` (ipykernel upstream bug) |

### Hidden Resource Warnings (real bugs — unclosed file handles)

All of these used one of two anti-patterns:
- `open(path).read()` — file object discarded immediately, closed by GC
- `f = open(path)` ... `f.close()` — explicit close without exception safety

Files fixed (all converted to `with open(...) as f:` context managers):

| File | Lines | Pattern |
|------|-------|---------|
| `quicknxs/main_gui.py` | 317, 1280, 2003, 2225, 2304, 2306, 2449 | 7 instances |
| `quicknxs/qio.py` | 374, 839, 867, 978, 1048 | 5 instances |
| `quicknxs/buzhug/buzhug_info.py` | 66 | 1 instance |
| `quicknxs/gui_utils.py` | 415–422 | 4 instances (email attachments) |
| `quicknxs/gui_logging.py` | 92, 235 | 2 instances |
| `quicknxs/auto_reflectivity.py` | 130, 269, 434 | 3 instances |
| `quicknxs/database_dialog.py` | 48 | 1 instance (double open) |
| `quicknxs/point_picker.py` | 172, 194 | 2 instances |
| `quicknxs/genx_data.py` | 210, 256 | 2 instances |
| `tests/qio_test.py` | 249 | 1 instance (py2/py3 branch removed) |

## Changes Made

### pyproject.toml

Added `filterwarnings` to `[tool.pytest.ini_options]`:

```toml
filterwarnings = [
  "error",                                    # all warnings → errors (enforces clean code)
  "ignore::pytest.PytestCollectionWarning",   # numpy.test false positive
  "ignore::PendingDeprecationWarning:ipykernel",  # ipykernel upstream bug
]
```

The `"error"` entry ensures that any NEW warnings introduced by future code will
cause test failures immediately, forcing developers to either fix the warning or
explicitly document why it is suppressed.

### tests/conftest.py

Added a docstring explaining the warning policy and how to handle new warnings
in the future.

## Warning Policy for Future Development

1. **New warning from our code**: Fix the root cause. Do not add a suppression.
2. **New warning from upstream**: Add a specific `filterwarnings` ignore entry
   in `pyproject.toml` with a comment explaining why it cannot be fixed in our
   code. Use the most specific pattern possible.

The `gc.collect()` call in `conftest.py`'s `_qt_cleanup` fixture helps surface
`ResourceWarning` from unclosed file handles during tests, since GC may otherwise
defer cleanup until after the test completes.
