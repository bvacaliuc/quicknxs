# Prompt 32 — Holistic responsiveness/feedback design

Phase 1 (committed `9b8038d`) wrapped 11 handlers in `with self.busy(...)`. Live
testing showed it is **incomplete**: many discrete actions that trigger a replot
are unwrapped (BG-X toggle, channel radios, normalize, clear/remove, table
edits, format toggles), and **stacked clicks during a blocking op get no
acknowledgement until the op finishes**. This doc audits every main-window
action and proposes a complete scheme. Architecture stays **single-threaded**
(threading is a later phase).

## Why stacked clicks can't be acknowledged today (the core constraint)

While a slot runs, the Qt event loop is blocked; new clicks sit in the OS/Qt
event queue and are **not dispatched** until the slot returns. Our code cannot
run during the block, and Qt does **not** expose its pending-event count. So the
only way to *count* "3 operations queued" is to put them in **our own** queue —
i.e. intercept user actions, enqueue them, and drain them ourselves. That is the
heart of the design below.

## Audit — every main-window action by cost

Triggers are the `*.connect(...)` lines in `default_interface.py` (88 of them).
Cost measured/estimated on a local file; sshfs inflates anything doing I/O.

### A. Heavy, discrete (one user gesture → one replot/reduce/IO)  ← need feedback

| Handler | Triggered by | Cost | Phase-1? |
|---|---|---|---|
| `fileOpen` / `fileOpenSum` | file_list select, reload, next/prev, open dialogs | 0.6–4 s | ✅ |
| `openByNumber` | run-number entry | I/O (sshfs) | ✅ |
| `loadExtraction` | Load Extraction | 20–30 s multi-file | ✅ |
| `plotActiveTab` | tab change, kiz/qx/kizmkfz radios | 0.1–1.4 s | ✅ |
| `quickReduce` | Quick Reduce | seconds | ✅ |
| `autoRef` / `stripOverlap` | menu | seconds | ✅ |
| `exportRawData` / `live_open` / `clip_offspec_colorscale` | menu/button | 0.1–1 s | ✅ |
| `reduceDatasets` | **Reduce** button | dialog + reduction | ❌ (modal dialog) |
| `changeActiveChannel` | channel radios ×12 | recompute all refls + replot | ❌ |
| `normalizeTotalReflection` | Normalize Scaling | fit + replot | ❌ |
| `clearRefList` / `removeRefList` / `clearNormList` | menu | replot | ❌ |
| `overwriteDirectBeam` / `clearOverwrite` | menu | recompute + replot | ❌ |
| `overwriteChanged` | dangle0/directPixel edited | recompute + replot | ❌ |
| `reductionTableChanged` | reduction-table cell edit | `recalculateReflectivity` + replot | ❌ |
| `replotProjections` | logarithmic_y | replot | ❌ |
| `toggleColorbars` | 6 checkboxes (colorbars, log, tthPhi…) | clears 14 figs + full replot | ⚠️ via nested `plotActiveTab` |
| `folderModified` | histo/event/old format toggles | `glob` dir (sshfs-slow) | ❌ |
| `cutPoints` / `visualizePeakfinding` | menu/button | compute + replot | ❌ |

### B. Heavy, continuous (rapid valueChanged; already debounced)  ← coalesced feedback

| Handler | Triggered by | Notes |
|---|---|---|
| `changeRegionValues` | refXPos/Width, refYPos/Width, bgCenter/Width, rangeStart/End, refScale, + bgActive/fanReflectivity/trustDANGLE toggles | redraws lines now, debounced refl replot via `DelayedTrigger` (0.25 s) |
| `change_offspec_colorscale` / `change_gisans_colorscale` | offspec/gisans Imin/Imax | rescale + 4 draws |

Note: the toggles on this handler (`bgActive` = "BG X", `fanReflectivity`,
`trustDANGLE`) are **discrete** but share the continuous handler — they were the
"no feedback" case the user hit (2a).

### C. Dialog-opening (construct + exec; the dialog owns its own progress)

`reduceDatasets`, `fileOpenDialog`, `fileOpenSumDialog`, `open_advanced_background`,
`open_compare_window`, `open_reduction_preview`, `open_rawdata_dialog`,
`open_polarization_window`, `open_nxs_dialog`, `open_logfile_viewer`,
`open_database_search`, `open_filter_dialog`, `helpDialog`. Construction can lag
(esp. DB / polarization). Want "Opening …" ack until the window is up; **no wait
cursor during the modal** (user interacts with it).

### D. Instant (no feedback needed)

`toggleHide`, `set_debug`, `raiseError`, `aboutDialog`, `run_ipython`,
`nextFile`/`prevFile` (just move the list row → re-enters `fileOpen`),
`eventSplitItems→setMaxValue`, `setNorm` (fast unless it replots).

## Proposed design

### Mechanism 1 — complete the discrete coverage (Phase 2a, low risk)

Wrap **every class-A handler** in `with self.busy("<specific message>")`, exactly
as phase 1. Depth-counting already guarantees one "Complete" per user action even
when handlers nest (e.g. `changeActiveChannel` → `plotActiveTab` → `plot_refl`).
Synchronous semantics are unchanged (safe for the test suite and internal
callers). This alone fixes 2a, the Reduce ack (3), and every "no indication"
case **for the op that is actually running**. It does **not** yet acknowledge
*stacked* clicks (that's Mechanism 3).

`reduceDatasets`: show "Opening reduction options…", `processEvents`, **restore
the cursor before `dialog.exec_()`** (interactive), Complete after it returns.

### Mechanism 2 — coalesced status for continuous inputs (Phase 2a)

Class-B handlers must not flash "Complete" on every spinbox tick. Add a tiny
`ActivityIndicator.busy_until_idle(message, settle_ms=400)`:

* each call shows *message* (persistent) and (re)starts a single-shot settle
  timer;
* when the user stops changing for `settle_ms`, the timer fires → "Complete"
  (fading).

So dragging a region spinbox shows "Adjusting extraction region…" continuously,
then one "Complete" ~0.4 s after you stop. The actual replot keeps using the
existing `DelayedTrigger`; this only governs the *status text*. The discrete
toggles sharing this handler (BG-X etc.) get the same treatment — good enough,
and they settle immediately.

### Mechanism 3 — stacked-operation awareness via a deferred command queue (Phase 2b)

This is the only way to surface "X stacked operations…". Add an
`ActivityQueue` owned by MainGUI:

```
dispatch(label, fn, *args):           # called by the re-wired user signals
    queue.append((label, fn, args))
    refresh_status()                  # >1 pending -> "N operations pending…"
    if not draining: QTimer.singleShot(0, drain)

drain():
    draining = True
    set wait cursor
    while queue:
        label, fn, args = queue.popleft()
        show_busy(status_text(label))     # see UX below
        fn(*args)                         # the REAL (synchronous) handler
        app.processEvents()               # ingest clicks that queued during fn
    restore cursor; show_complete("Complete"); draining = False
```

Because every heavy user action is deferred, the only thing `processEvents()`
can re-enter is another *enqueue* (cheap) — so it is safe, and clicks that piled
up during a blocking `fn` get counted the instant `fn` returns.

**Wiring without touching generated code:** in `MainGUI.__init__`, after
`setupUi`, disconnect the class-A/C auto-connections and reconnect them through
`dispatch(...)`. The handler methods stay ordinary synchronous methods (still
callable directly by internal code and the test suite — only *user signals*
defer). ~25 re-wires, all in one place, individually testable.

**Stacked-status UX (user's proposal):**
* `pending > 1` → `"%d operations pending…" % pending`
* `pending == 1` → the running op's specific label ("Rendering off-specular preview…")
* on drain end → fading "Complete"

This delivers 3d: clicking OffSpec during a reduction immediately shows
"2 operations pending…", and when the reduction's blocking section yields, the
count drops and the OffSpec label surfaces.

### What stays unsolved without threading (be honest)

A *single* uninterruptible call — one big `matplotlib draw()` or one numpy
reduction step — still blocks for its full duration; clicks during *that call*
are acknowledged only when it returns (then immediately, via the queue). Phase 2
shrinks the blind window from "the whole multi-step operation" to "one inner
step." Eliminating it entirely is Phase 3 (move compute/IO to a `QThread`/
`QThreadPool`, keeping matplotlib + widgets on the GUI thread).

## Phasing

* **2a** — Mechanisms 1 + 2: wrap all class-A handlers; coalesced status for
  class-B; "Opening…" for class-C. Low risk, no semantic change, big UX win.
  **DONE** (see status below).
* **2b** — Mechanism 3: deferred queue + stacked count. Medium risk (signal
  re-wiring); new tests drive the dispatcher. **Awaiting review.**
* **3 (future)** — worker thread for the genuinely long compute/IO.

### Status — Phase 2a implemented

Decisions taken from review: 2a first; stacked text (2b) will be
`"<label>  (+N queued)"`; wait cursor only for heavier ops.

Implemented:
* `ActivityIndicator.busy_until_idle(message)` — coalesced status with a settle
  timer (no per-tick "Complete" flash).
* `MainGUI.busy(..., show_cursor=)` + `_activity_transient(message)`.
* **Wait cursor by action class** (not a timer): the event loop is blocked during
  a synchronous slot so a live ">200 ms" timer cannot fire mid-op — heavy
  discrete ops show the cursor; quick/continuous ones (`_activity_transient`,
  `show_cursor=False`) never do. This is the faithful equivalent of "only past
  200 ms" / "quick replots keep the normal pointer".
* Discrete handlers wrapped: `clearRefList`, `removeRefList`,
  `changeActiveChannel`, `normalizeTotalReflection`, `reductionTableChanged`,
  `replotProjections`, `toggleColorbars`, `visualizePeakfinding`,
  `reduceDatasets` (no cursor), and all `open_*` dialog openers ("Opening…").
* Continuous (coalesced, no cursor): `changeRegionValues` (the BG-X case),
  `change_offspec_colorscale`, `change_gisans_colorscale`, `overwriteChanged`,
  `folderModified` (sshfs `glob`).
* Deliberately skipped: `setNorm` (borderline, heavily called in internal loops),
  `clearNormList` (instant table clear), `cutPoints`/`overwriteDirectBeam`/
  `clearOverwrite` (feedback comes free via the handler they delegate to).

Tests: `activity_status_test.py` (15) + `responsiveness_test.py` (14) green;
full `main_gui_test.py` re-run for regressions; ruff clean.

**Still open (2b territory):** stacked clicks during a *single* blocking call
are acknowledged only when that call returns.

## Risks / decisions

* **Re-wiring (2b)** changes user-signal delivery from direct to deferred. Internal
  calls and tests stay synchronous. Need a clean disconnect/reconnect and a test
  that a queued action actually runs.
* **`processEvents` re-entrancy** is safe *only if every heavy action is deferred*
  — completeness of routing matters; an un-routed heavy signal could re-enter.
* **Modal dialogs** (`exec_`) run a nested loop; the queue pauses inside `fn`
  (correct). Cursor must be released before `exec_`.
* **Tuning**: settle_ms (~400 ms), Complete hold/fade (2 s / 1.2 s) — all configurable.

## Open questions for review

1. Adopt the deferred-queue (2b) now, or land 2a first and evaluate?
2. Stacked text: literally "N operations pending…", or "Working… (N queued)"?
3. Should the wait cursor appear for sub-second class-A ops, or only past a
   threshold (e.g. >200 ms) to avoid cursor flicker on quick replots?
