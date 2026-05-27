# Prompt 32 — GUI responsiveness ("not crisp")

Branch: `feature/read-event-nexus`. Reported: GUI takes several seconds to react
to button presses, on both analysis.sns.gov and dragonfly (systematic, not just
sshfs). "The quick part of quicknxs is that actions have immediate effect."

## Diagnosis (measured, not guessed)

Profiled headless via `scripts/profile_responsiveness.py`
(`QT_QPA_PLATFORM=offscreen`, local `tests/test1_histo.nxs`, so numbers are the
**systematic** cost independent of sshfs). Stuck-process stacks captured with
`py-spy dump`.

### Wall-clock per handler (main/event-loop thread, local file)

| Operation | Time | Notes |
|---|---:|---|
| `fileOpen` cold (load + overview plot) | **4.0 s** | the "several seconds" |
| `fileOpen` warm (NXSData cache hit) | 0.6 s | still not crisp |
| tab → X vs Y (`plot_xy`, 8 imshow) | 0.78 s | |
| tab → X vs ToF (`plot_xtof`) | 0.54 s | |
| `plot_refl` | 0.25 s | ~all matplotlib draw |
| `changeRegionValues` (spinbox path) | 0.19 s | + 0.25 s `DelayedTrigger` debounce |
| **`plot_offspec`** (OffSpec Preview) | **1.1–1.4 s** | re-reads + recomputes every view |
| `calc_refl` (the reduction math) | **0.002 s** | negligible |
| `setNorm`, `addRefList` | <0.001 s | negligible |

### Root cause

1. **Everything runs synchronously on the GUI thread.** Qt cannot repaint or
   even show a button's pressed state while a slot runs, so the window is frozen
   for the full 0.2–4 s of each action with **no acknowledgment that the click
   registered**. This is the entire "not crisp" feeling.
2. **The cost is matplotlib rendering + file I/O, NOT the reduction math.**
   cProfile of 10× `plot_refl`: dominated by `axis._update_ticks`,
   `get_major_ticks`, `backend_agg.draw_text`. `calc_refl` is 2 ms.
   `plot_offspec` ≈ 0.7 s `OffSpecular.__init__` (incl. 0.20 s `zlib.decompress`
   of the detector array) + ~0.5 s draw, recomputed from scratch on every view.
3. **`plot_offspec` re-reads each reduction-list file** (`NXSData(fname)`) and
   re-runs `OffSpecular` per channel on every tab view (main_gui.py:1083-1112).
   NXSData has a class cache so disk is only hit once, but decompress+recompute
   +draw repeat. Over sshfs the first read also pays disk latency → much worse.

### Two modal-dialog footguns found while profiling (both fully block the GUI)

- **Startup "Previous Crash" `QMessageBox`** (main_gui.py:2593): pops whenever a
  stale `~/.quicknxs/run_state.dat` exists — i.e. after any crash/OOM kill (this
  app has a history of OOM). Headless it blocks forever; for a user it's a modal
  gate on every launch after a non-clean exit.
- **Logged `warning()` → modal `QMessageBox`** (gui_logging.py:193 `show_warning`).
  Any code path that logs a warning freezes the GUI until the user clicks OK.
  `info()` already routes to `statusbar.showMessage(msg, 5000)` (non-blocking).

## Fix strategy (matches the user's explicit asks)

Since the latency is rendering (hard to make dramatically faster without a large
matplotlib refactor), the high-leverage, low-risk win is **immediate
acknowledgment + a uniform idle signal**:

1. **Immediate status before the blocking work** + `processEvents(ExcludeUser
   InputEvents)` so Qt actually paints the message and the wait cursor *before*
   the slot blocks. The app then feels instant even when the op takes a second.
2. **Wait cursor** while busy.
3. **Uniform fading "Complete"** when the outermost busy scope exits (return to
   idle). Real opacity fade so it doesn't clutter.

Implemented as a centralized `ActivityIndicator` (status-bar label + opacity
fade) + a busy-depth counter + `with self.activity("…"):` context manager on
MainGUI, applied to the heavy top-level handlers. Depth counting makes nesting
(fileOpen → plotActiveTab → plot_refl) fire "Complete" exactly once.

Secondary (optional, noted not yet done): cache `OffSpecular` results so the
preview tab doesn't recompute; make the startup crash dialog non-blocking.

## Repro / tooling

- `QT_QPA_PLATFORM=offscreen pixi run python scripts/profile_responsiveness.py [--cprofile]`
- `py-spy dump --pid <pid>` to get a Python stack of a hung/slow GUI (installed
  via `uv tool install py-spy`).
