# TODO — `QToolBox` / `QDockWidget` page sizing (deficiency)

**Status:** open deficiency, deferred. Discovered 2026-05-31 during the prompt-34
follow-up (Flux 10^ placement); resolution chosen this session was a workaround
(move the control to a roomier tab), not a fix.

## What the tension is

`quicknxs/main_gui.py` is loaded from one of two compiled `.ui` modules — the
`default_interface` (`QToolBox`-based, with pages "Reflectivity Extraction
(Basic)", "(Advanced)", "Peak Finder Algorithm", "Plot Options") and the
`docked_interface` (each section in its own `QDockWidget`). In both forms the
"Reflectivity Extraction (Basic)" panel — the natural home for BG-X and flux-floor
controls — is sized at design time for its **original** 6 rows
(`page.setGeometry(0, 0, 256, 132)` in `default_interface.py:152`,
`dockWidget_4` with a tight fixed height in `docked_interface.py`).

Adding a 7th row programmatically from `MainGUI.__init__` (e.g. a "Flux 10^"
label + spinbox alongside `bgActive`/`bgCenter`/`bgWidth`) forces the page
widget's `sizeHint().height()` past what the QToolBox section / dock widget
allocates, and the container wraps the page in a `QScrollArea` showing
scrollbars (vertical always, horizontal sometimes).

Runtime mitigations tried this session and rejected:
- `_container.adjustSize()` + `setMinimumHeight(sizeHint().height())` — kept the
  vertical scrollbar regardless of window size, because the minimum height we
  set was slightly larger than what QToolBox could allocate.
- Walking up the parent chain to `QDockWidget` / `QToolBox` and calling
  `setMinimumHeight(... + buffer)` / `resize(...)` — same result.
- Placing the new label + spinbox into an existing row's empty cells —
  `gridLayout_3` (default) and `gridLayout_12` (docked) put their existing
  widgets in **different columns**, so a single hard-coded `(row, col)` overlaps
  in one interface or the other.

Workaround in effect (`04fb840`): the Flux 10^ control lives in the Off-Specular
tab (`OffSpec_Tab`), where there is room. The user accepted this; their N1+N2
preference (cluster all BG controls together) is conceptually right but blocked
by the structural constraint.

## What a proper fix looks like

The clean fix is to **edit the two `.ui` files** so the BG section reserves
space for the additional row(s) at design time:

1. `designer/default_interface.ui` — open in Qt Designer, add a row at the
   bottom of `gridLayout_3` (inside `self.page`) with empty label + spinbox
   placeholders, increase `page` height to accommodate, save, then
   `./compile_gui.sh` to regenerate `quicknxs/default_interface.py`.
2. `designer/docked_interface.ui` — same treatment for `gridLayout_12` inside
   `self.dockWidgetContents_4`, ensure `dockWidget_4` minimum height grows.
3. Move the runtime widget creation in `main_gui.py.__init__` from
   `self.ui.OffSpec_Tab` back to `self.ui.bgActive.parentWidget()`, hooking
   the placeholder rows in the regenerated `.py`.
4. Re-test against both interfaces in both expanded and compact window sizes;
   compare against `~/shared/REF_M/QuickNXSv1/prompt34/*-scrollbars*.png`.

## Why we did not do it this session

- Editing two `.ui` files plus running `pyuic5` regenerates the committed
  `default_interface.py` and `docked_interface.py` — a wide diff that touches
  every widget's compiled code, easy to miss subtle changes.
- Without a display we cannot visually verify before-and-after.
- The user's primary goal ("no scrollbars in the Reflectivity Extraction (Basic)
  panel") is satisfied by the OffSpec_Tab workaround.

## Acceptance for the fix

- "Reflectivity Extraction (Basic)" shows BG-X **and** Flux 10^ controls with
  **no** scrollbars at the default window size, in both `default_interface`
  and `docked_interface`.
- Resizing the main window narrower / shorter behaves the same as before for
  the other rows (no regression in the existing 6 rows' layout).
- `tests/main_gui_test.py::test_offspec_flux_floor_control` updated to assert
  the spinbox is parented under `bgActive.parentWidget()` (current test asserts
  `OffSpec_Tab`).
