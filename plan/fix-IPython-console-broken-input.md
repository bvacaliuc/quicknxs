# Plan: Fix IPython Console Broken Import

## Context

The Advanced->IPython Console menu action crashes with `ModuleNotFoundError: No module named 'mplwidget'`. The `_install_exc()` method at `main_gui.py:269` uses a bare import (`from mplwidget import _set_default_rc`) instead of a relative import. Python 3 eliminated implicit relative imports, so this fails. This is the only broken import in the codebase — all other files correctly use `from .mplwidget import ...`.

## Fix

**File:** `quicknxs/main_gui.py` line 269

Change:
```python
from mplwidget import _set_default_rc
```
To:
```python
from .mplwidget import _set_default_rc
```

## Test

**File:** `tests/main_gui_test.py` — Add to `MainGUIIPythonFault` class

Add `test_run_ipython_starts_console` that calls `self.gui.run_ipython()`. The test fixture already replaces `trigger` with synchronous `processDelayedTrigger` calls (line 273), so `_install_exc` will execute immediately and exercise the fixed import. Verify:
- `self.gui.ipython` exists (widget was created)
- No exception raised (the import fix works)

## Cleanup

**File:** `TODO.md` — Remove resolved issue content.

## Verification

```bash
make test   # All tests pass including new test
```

## Files to Modify

| File | Change |
|---|---|
| `quicknxs/main_gui.py` | Fix relative import on line 269 |
| `tests/main_gui_test.py` | Add `test_run_ipython_starts_console` |
| `TODO.md` | Remove resolved issue |
