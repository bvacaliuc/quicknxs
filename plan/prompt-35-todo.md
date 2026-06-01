# prompt-35 — UI usability + freeze diagnosis + v4.17.0rc5 comparison (2026-05-30)

Live-test feedback from user (session running on UPS power, time-limited). Items
captured as I work; remaining items go to the bottom for the next session.

User confirmed:
- Off-spec controls (BG-X + flux floor 10^) appear and work.
- BG-X tracks the main background checkbox; preview updates on toggle.
- Flux-floor changes the preview at -2 and -8 (see PNGs in session13/).
- Reduction runs, but comparability to `correctReduction` is uncertain (see N6).

## N1 + N2 — Consolidate UI (resolved 2026-06-01)
- BG-X: the off-spec mirror checkbox was removed — `bgActive` is the single
  BG-X control.
- Flux floor placement: **reverted to the Off-Specular tab.** Attempt to put it
  next to `bgActive` in the Reflectivity Extraction (Basic) QToolBox page made
  the page sprout vertical (and sometimes horizontal) scrollbars regardless of
  how we tried to expand the page widget's geometry, because the QToolBox page
  was originally sized for its 6-row content and adding a row pushed it past
  the allocated section height. Compact label ("Flux 10^") and width-capped
  spinbox (60 px) are kept; the control sits in the OffSpec tab next to the
  Imin/Imax controls, where there is room. Documented in `CLAUDE.md`.

## N3 — Harmonize flux-floor spinbox with v1 immediate-recalc behavior
- v1's spinboxes recompute on every `valueChanged`; v2 waits for Enter
  (`editingFinished`). The new flux-floor spinbox was wired to
  `editingFinished` (v2-style), inconsistent with v1. Switch to `valueChanged`
  (debounced via DelayedTrigger if available, else direct) and record the v2
  Enter behavior as a *future* harmonization project in the project CLAUDE.md.

## N4 — UI freezes without immediate statusbar/cursor feedback (PARTIAL FIX 2026-05-30)
- Parsed `~/.quicknxs/debug.log` (1063 events). Biggest non-idle gaps:

  | gap   | after / before                              | meaning |
  |------:|---------------------------------------------|---------|
  |  109s | gui_utils @log_call → qio.py:898 export     | reduction → export gap |
  |   98s | gui_utils @log_call → main_gui:2341         | reduction commit |
  |   98s | gui_utils 479 → 500                         | reduction body |
  |   65s | gui_logging.setup → loadExtraction          | startup-ish |
  |   57s | qreduce:3363 _calc_offspec → qreduce:380    | off-spec extract → next channel |
  |   43s | gui_utils 500 → 546                         | reduction inner |
  |   38s | qreduce:3363 _calc_offspec → main_gui:1857  | off-spec extract → next handler |
  |   27s | qreduce:3363 _calc_offspec → main_gui:686   | off-spec extract |
  |   26s | qreduce:3363 _calc_offspec → main_gui:686   | off-spec extract |

- **Root cause** of the BG-X / flux-floor freeze: `plot_offspec` iterates every
  reduction-list file and re-runs `OffSpecular` per channel — with 3 runs × 2
  channels that's ~6 invocations of off-spec extraction at ~5s each = ~30s. No
  `busy()` wrapper, so the user just sees a frozen UI.
- **Applied (this commit):** wrap `_replotOffspec` in `with self.busy('Off-specular
  preview...')` so the statusbar message + wait cursor fire INSTANTLY when bgActive
  toggles or the flux-floor changes. The actual work is still slow; the user now
  sees feedback throughout.
- **Remaining for next session:**
  - **Coalesce valueChanged** so spinning the flux-floor spinbox doesn't queue
    multiple 30s recomputes: switch the connection to a DelayedTrigger / QTimer
    (≈300 ms) or use `_activity_transient` for the tick stream + a settled
    redraw. Currently every step of the spinbox triggers a full off-spec replot.
  - **Speed up `plot_offspec` itself**: re-load and re-extract on every preview
    is the cost (see the 25–57s gaps after `_calc_offspec`). Options: cache
    per-run `OffSpecular` results keyed on `(file, channel, item.options)`
    until the inputs change; or recompute only the channels visible in the
    plot grid (currently all 4 are iterated even if only 2 channels exist).
  - **N4 sub-item — reduction dialog statusbar feedback** (N5): the
    statusbar text was stuck at "Opening reduction dialog…" during reduction.
    The 109s and 98s gaps in the export/reduce path confirm the dialog runs
    long without updating the statusbar. Wire the reduction loop to update the
    main statusbar (or propagate the dialog's progress into it) at least once
    per file/channel.
  - **N4 sub-item — Overview-tab switch 30s freeze**: gather the timestamp the
    user observed and trace which slot ran; almost certainly missing a
    `busy()`. Common culprits: `plotActiveTab` on tab switch (matplotlib
    `draw()` cost per CLAUDE.md responsiveness section).

## N6 — Comparison vs `correctReduction` shows identical metrics for default + 10^-8 (FIXED CAUSE 2026-05-30)
- The user's two comparison `.txt` files (default flux-floor and `flux-floor-10e-8`)
  have BYTE-IDENTICAL metrics (median 0.547, spec 0.904, offspec 0.528).
- Root cause: the off-spec flux-floor (and BG-X) **bake into `refl.options` only at
  `calcReflParams` time** (i.e. when each run is added to the reduction list). The
  user changed the spinbox AFTER reducing, so the stored options retained the old
  values; the export silently used them.
- **Applied (this commit):** `Reducer.execute()` now refreshes
  `subtract_background` and `offspec_flux_floor` on every `refl.options` from the
  live GUI before the Exporter is built. The off-spec extraction
  (`Exporter.extract_offspecular`) constructs `OffSpecular()` fresh from
  `refl.options`, so the new values propagate to export.
  - Note (specular path): the specular R(Q) is already computed in each
    Reflectivity object, so changing `subtract_background` here does NOT
    recompute the specular; only the off-spec re-extracts. If the user also
    wants the specular to honor a late BG-X toggle, they need to re-Calc each
    item (existing workflow). Documented for the next session.
- **User-facing follow-up:** with this fix the user should re-run the same
  reduction (flux floor 10^-8, BG off) and now see DIFFERENT metrics; if they
  still don't match `correctReduction` (v4.3.0rc1), the residual is the
  smoothing-parameter mismatch (v4.17.0rc5-like vs v4.3.0rc1 defaults), not a
  reduction-engine issue.  Yesterday's matched run (paired + flux-floor 1e-3 +
  BG-off + v1 default smoothing) gave median 1.067 — the user's run with flux
  floor 10^-8 + v4.17.0rc5-like smoothing will differ in the off-spec wings
  because of the smoothing kernel differences.

## N5 — Off-spec preview vs smoothing-parameters dialog discrepancies
- Axes scales, colormap, intensity scale differ between the two views.
- **Colormap (FIXED 2026-05-30):** the smoothing dialog's `plot.pcolormesh`
  call (`gui_utils.py:759`) had no `cmap=` kwarg, so it fell through to
  matplotlib's default (viridis), whereas the main off-spec preview uses
  `cmap=self.color` from the Plot-Options dropdown (default `gist_ncar`).
  `SmoothDialog.drawPlot` now reads `self.parent().color` and passes it to
  pcolormesh, so both views use the SAME colormap from Plot Options. If the
  user prefers viridis, change it in the Plot Options dropdown — it now
  applies everywhere.
- **Intensity scale / axes:** the smoothing-parameters dialog renders the full
  un-clipped intensity range with its own auto-limits. The off-spec preview is
  clipped to `offspecImin`/`offspecImax` (user-set). The user wants the
  off-spec preview to **start with full-scale rendering** like the smoothing
  dialog. Plan: on first plot (or until the user clicks Clip), auto-fit the
  Imin/Imax from the actual data extent.
- **Statusbar frozen at "Opening reduction dialog…":** the reduction dialog's
  inner progress isn't propagated to the main-window statusbar. Add a
  statusbar update from the reduction loop (at least once per channel/run).

### N5 sub-item — Smoothing σ default + anisotropy + x/y coupling (FUTURE)
- User changed σ to **0.000525** and noted a black spot at (0,0.1) — a more
  appropriate default than 0.0005. Also the spot anisotropy is an artifact of
  single-entry σ vs the (Δk, Qz) coordinate scaling.
- **Future work (NOT this session):** revisit the σ default, make σ x/y coupled
  by default (single value drives a sensible (σx, σy) pair given the axis
  scaling), and address the visible anisotropy.

## N6 — Comparison vs **v4.17.0rc5** is still off
- User ran reduction with no BG, flux floor 10^-8, smoothing similar to
  v4.17.0rc5. Result diverges from `correctReduction` (made by v4.3.0rc1).
  Artifact: `session13/compare-v4.3.0rc1-vs-v1.3.0dev49-flux-floor-10e-8.{png,txt}`.
- **Hypothesis:** `correctReduction` is **v4.3.0rc1** output (the target
  we matched at median 1.067). v4.17.0rc5 is a *different* version of v2 with
  possibly different defaults (e.g. coarser TOF binning, different smoothing
  kernel `xysigma0`, different DB-association). Without a v4.17.0rc5 reference,
  matching it from v1 requires copying its specific knobs (tof_bins step, σ,
  band, BG, scale).
- **Investigate this session if time permits:** read the `.txt` to see what
  metric the user used; if it includes the actual numbers, compute the residual
  factor and check whether it's another global scale / smoothing / binning
  effect.

## Remaining investigations / open items (carry forward)
- [ ] N4 — `~/.quicknxs/debug.log` freeze timeline → wrap heavy slots in busy/_activity_transient.
- [ ] N5 — colormap unification, full-scale offspec preview start, reduction-dialog statusbar updates.
- [ ] N5 σ-default + anisotropy + x/y coupling.
- [ ] N6 — figure out the v4.17.0rc5 vs `correctReduction` (v4.3.0rc1) divergence and whether v1 can match v4.17.0rc5 without changing the v4.3.0rc1 match.

## Notes (this session)
- BG controls now live in ONE place (BG section); the Off-Spec tab mirror is removed.
- Flux floor spinbox uses immediate recalc (v1 convention); a CLAUDE.md note flags the v1→v2 (Enter) harmonization as a future project.
