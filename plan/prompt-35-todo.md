# prompt-35 — UI usability + freeze diagnosis + v4.17.0rc5 comparison (2026-05-30)

Live-test feedback from user (session running on UPS power, time-limited). Items
captured as I work; remaining items go to the bottom for the next session.

User confirmed:
- Off-spec controls (BG-X + flux floor 10^) appear and work.
- BG-X tracks the main background checkbox; preview updates on toggle.
- Flux-floor changes the preview at -2 and -8 (see PNGs in session13/).
- Reduction runs, but comparability to `correctReduction` is uncertain (see N6).

## N1 + N2 — Consolidate UI: BG-X stays at the main BG section; move flux floor there too
- The BG-X checkbox in the Off-Specular tab was a mirror of `bgActive`. Two
  controls for one logical flag confused the user. Remove the off-spec BG-X
  mirror; keep only `bgActive` (in the existing BG controls). Move the
  "Flux floor 10^" spinbox to sit alongside `bgActive` so all BG-related
  controls live together.

## N3 — Harmonize flux-floor spinbox with v1 immediate-recalc behavior
- v1's spinboxes recompute on every `valueChanged`; v2 waits for Enter
  (`editingFinished`). The new flux-floor spinbox was wired to
  `editingFinished` (v2-style), inconsistent with v1. Switch to `valueChanged`
  (debounced via DelayedTrigger if available, else direct) and record the v2
  Enter behavior as a *future* harmonization project in the project CLAUDE.md.

## N4 — UI freezes without immediate statusbar/cursor feedback
- User observed long no-response periods (>30s) for actions including: BG-X
  toggle, flux-floor change, switching to Overview after reduction. After
  enabling debug logging the timing should be visible in `~/.quicknxs/debug.log`.
- **Investigate:** read the log for the timestamps the user described and
  identify which handlers ran without a `busy()` / `_activity_transient()`
  wrapper. Likely culprits: `_onOffspecBgX` → `plot_offspec` (heavy: re-reads
  every reduction-list file + computes off-spec per channel; per CLAUDE.md
  responsiveness section, the OffSpec Preview is ~1.4s **per re-render**), and
  the smoothing-parameters dialog open.
- **Plan:** wrap the off-spec replot in `with self.busy('Off-specular preview…')`
  so the user sees the message + wait cursor instantly; for high-frequency
  inputs (valueChanged) use `_activity_transient` to coalesce.

## N5 — Off-spec preview vs smoothing-parameters dialog discrepancies
- Axes scales, colormap, intensity scale differ between the two views.
- **Colormap:** main plot options has a "Colorbar" checkbox + dropdown
  (user sees `gist_ncar` selected). The smoothing-parameters dialog uses a
  different colormap. Locate where the smoothing dialog sets its cmap; either
  (a) bind it to the same `self.color` (`misc.cmap` config) the main offspec
  uses, or (b) document the dichotomy if there's a deliberate reason.
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
