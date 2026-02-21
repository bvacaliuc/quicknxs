# Plan: Overhaul Test System with Timeouts and Fix Hanging Test

## Context

The 49th test (`MainGUIDisplayControls::test_plot_tab_switching`) hangs indefinitely when running `make test`, preventing the test suite from ever completing. There is no timeout mechanism in the test infrastructure, so a single hanging test blocks the entire CI/test run forever.

## Goals
1. **Primary:** Ensure the test suite always completes by adding per-test timeouts
2. **Secondary:** Set statistically appropriate timeout thresholds
3. **Tertiary:** Fix the root cause of the hang in `test_plot_tab_switching`

## Root Cause of the Hang

`test_plot_tab_switching` iterates over all `plotTab` indices, calling `setCurrentIndex(i)` then `plotActiveTab()`. But `setCurrentIndex()` emits the `currentChanged` signal which is connected to `plotActiveTab()` (in `docked_interface.py:1362`), so **plotActiveTab runs twice per iteration**.

When tab 4 (GISANS) is reached:
1. First call (via signal) starts a `gisansCalcThread`
2. Second call (explicit) terminates the barely-started thread and starts a new one
3. When the next tab is selected, `plotActiveTab()` tries to terminate/wait on this thread again
4. The combination of `thread.terminate()` + `thread.wait(100)` on a thread that may not have fully initialized causes an indefinite hang

## Timeout Threshold Rationale

Observed test durations across 138 tests:
- **Mean:** ~3s, **Max:** 13.22s (`test_create_data`)
- **95th percentile:** ~9s, **99th percentile:** ~13s
- Using **mean + 5σ** or roughly **2× the observed max** → **30 seconds**
- This is generous enough to avoid flaky failures on slow machines while catching true hangs (which would run forever)

## Implementation Steps

### Step 1: Add pytest-timeout dependency
**File:** `pyproject.toml`
- Add `pytest-timeout` to `[tool.pixi.feature.test.dependencies]`

### Step 2: Configure global timeout in pytest config
**File:** `pyproject.toml` `[tool.pytest.ini_options]`
- Add `timeout = 30` (30-second default for all tests)
- Add `timeout_method = "thread"` (thread-based method works with Qt event loops better than signal-based)

### Step 3: Fix `test_plot_tab_switching` root cause
**File:** `tests/main_gui_test.py`
- Remove the explicit `self.gui.plotActiveTab()` call — `setCurrentIndex()` already triggers it via signal
- Add `self.app.processEvents()` after each `setCurrentIndex()` to ensure the signal-triggered slot completes
- This eliminates the double-execution race condition

### Step 4: Add a conftest.py with Qt event loop safety
**File:** `tests/conftest.py` (new)
- Add a session-scoped fixture or autouse fixture that calls `processEvents()` cleanup
- Set `QT_QPA_PLATFORM=offscreen` environment variable as a pytest environment setup

### Step 5: Verify by running full test suite
- `make test` should complete all tests within ~3 minutes
- No test should hang; any test exceeding 30s will fail with a timeout error

## Files to Modify
1. `pyproject.toml` — add pytest-timeout dep + config
2. `tests/main_gui_test.py` — fix `test_plot_tab_switching`
3. `tests/conftest.py` — new file for shared test configuration

## Verification
```bash
make test  # Full suite should complete, no hangs
pixi run python -m pytest tests/main_gui_test.py -v  # All GUI tests pass including the formerly-hanging one
pixi run python -m pytest tests/main_gui_test.py::MainGUIDisplayControls::test_plot_tab_switching -v  # Specific test passes
```
