# Plan: Fix SmoothDialog Cursor ValueError and Resulting Abort

## Context

Two errors occur during reduction via ReduceDialog:

1. **ValueError when clicking "Qx vs Qz" in SmoothDialog**: `leaveEvent()` in `mplwidget.py:337` sets `toolbar._last_cursor = None`, but matplotlib's `_wait_cursor_for_draw_cm()` context manager tries to restore the cursor using that value in its `finally` block, causing `ValueError: None is not a valid value for cursor`.

2. **Silent abort at ~99% smoothing**: After the ValueError leaves `SmoothDialog.drawPlot()` in a broken state (`self.drawing` stuck `True`, grid parameters not updated), the smoothing computation runs. During `processEvents()` in the progress callback, any visible MPLWidget with a corrupted `_last_cursor` triggers repeated ValueErrors. The cascading exceptions during event processing combined with CPU-intensive computation causes resource exhaustion and eventual process abort.

## Root Cause Chain

1. `MPLWidget.leaveEvent()` sets `self.toolbar._last_cursor = None` (line 337)
2. Matplotlib expects `_last_cursor` to always be a valid `tools.Cursors` enum value (initialized to `Cursors.POINTER` in `NavigationToolbar2.__init__`)
3. Any subsequent `canvas.draw()` on that widget triggers `_wait_cursor_for_draw_cm()` which fails in its `finally` block trying to restore the `None` cursor
4. In `SmoothDialog.drawPlot()`, the ValueError propagates out of `plot.draw()`, skipping grid parameter setup and leaving `self.drawing = True` permanently
5. During smoothing, `processEvents()` can trigger canvas repaints on MPLWidget instances whose `_last_cursor` was corrupted, causing repeated exceptions

## Implementation Steps

### Step 1: Fix `_last_cursor` value in `leaveEvent`
**File:** `quicknxs/mplwidget.py:337`
- Change `self.toolbar._last_cursor = None` to `self.toolbar._last_cursor = tools.Cursors.POINTER`
- Add `from matplotlib.backend_tools import Cursors as _Cursors` import at top of file

### Step 2: Add `try/finally` in `SmoothDialog.drawPlot()` to reset `self.drawing`
**File:** `quicknxs/gui_utils.py` — `drawPlot()` method (~line 639-729)
- Wrap the body after `self.drawing = True` in `try/finally` so `self.drawing = False` is always executed
- This prevents the dialog from becoming permanently unresponsive after a drawing error

### Step 3: Add final 100% progress callback in `smooth_data`
**File:** `quicknxs/qcalc.py:294`
- After the loop completes, call `callback(1.0)` if callback is not None
- This ensures the progress bar reaches 100% and a final `processEvents()` is called

### Step 4: Add tests
**File:** `tests/main_gui_test.py`
- Test that `MPLWidget.leaveEvent` sets `_last_cursor` to a valid `Cursors` value, not `None`
- Test that `canvas.draw()` works correctly after `leaveEvent` fires
- Test that `SmoothDialog.drawPlot()` resets `self.drawing` even if draw fails
- Test that `smooth_data` callback reaches 1.0 on completion

## Files to Modify
1. `quicknxs/mplwidget.py` — fix `leaveEvent` cursor value
2. `quicknxs/gui_utils.py` — add try/finally in `drawPlot()`
3. `quicknxs/qcalc.py` — add final progress callback
4. `tests/main_gui_test.py` — add verification tests

## Verification
```bash
make test  # All tests pass, no hangs
```
