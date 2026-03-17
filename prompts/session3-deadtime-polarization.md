# Session 3: Dead-Time Correction and Polarization Filtering

## Context

You are working in the **quicknxsv1** project on branch `feature/read-event-nexus`.
This is the third and final implementation session for `.nxs.h5` event file support.

**Read these files first** (in this order):
1. `CLAUDE.md` — project conventions
2. `plan/read-event-nexus-h5.md` — the full implementation plan (especially Phases 8-9
   which have detailed algorithms, guard clauses, and test cases)
3. `~/.claude/projects/-home-bvacaliuc-Projects-Claude-2/memory/MEMORY.md` — **critical:
   contains checkpoints from Sessions 1 and 2** with completed phases and any issues

## Your task

Implement **Phases 8 and 9** from the plan. Sessions 1-2 completed Phases 1-7.

- **Phase 8**: Dead-time correction (REF_L / BL4B only)
- **Phase 9**: Event-level polarization filtering (REF_M)

These are the most complex phases. Read the plan's Phase 8 and Phase 9 sections
carefully — they contain complete algorithms, guard clauses for missing data, and
detailed test cases.

## TDD workflow

Same as prior sessions. Add tests to `tests/test_event_h5.py`.

## Phase 8: Dead-time correction — critical details

- **LRDataset ONLY** — add `_apply_dead_time_correction()` as a static method on
  `LRDataset`, NOT on `MRDataset`
- REF_M (BL4A) does NOT use dead-time correction in quicknxsv1
- Call it inside `LRDataset.from_event_h5()` after `bin_events()` produces the 3D histogram
- Uses Lambert W function from `scipy.special.lambertw` (paralyzable model, default)
- Also implement non-paralyzable model (`1 / (1 - rate * τ / Δt)`) via `paralyzable` param
- Dead time parameter: 4.2 µs (matches lr_reduction's BL4B auto-reduction)
- **Guard clauses** (return unity correction when):
  - `bank_error_events/event_time_offset` is missing
  - `bank1_events/event_time_offset` is missing
  - `DASlogs/proton_charge/value` is missing
  - No non-zero proton charge pulses
- Clamp correction factors to `[1.0, 10.0]` range
- Warn (don't crash) on all missing-data conditions
- Test that REF_M does NOT have DTC applied (histogram sum ≈ total_counts)

## Phase 9: Polarization filtering — critical details

- Implement `_filter_events_by_polarization()` as a module-level function
- Returns `dict: {cross_section_name: (event_ids, event_tofs)}` or `None` on failure
- **Guard clauses** (return None / degrade to unpolarized when):
  - `DASlogs/SF1` is missing entirely
  - `DASlogs/SF1/value` or `SF1/time` is unreadable
  - `bank1_events/event_time_zero` or `event_index` is missing
  - All events end up in veto periods (empty channels)
- `DASlogs/SF2` missing = no analyzer = 2-channel (Off_Off, On_Off), not an error
- `DASlogs/SF1_Veto` / `SF2_Veto` missing = skip veto filtering, warn
- Implement veto filtering: events during flipper transitions (veto=1) are excluded
- Cross-section names: `Off_Off`, `On_Off`, `Off_On`, `On_On`
- Implement `MRDataset.from_event_h5_filtered()` — same as `from_event_h5()` but takes
  pre-filtered `event_ids` and `event_tofs` arrays instead of reading from the file
- Integration in `_read_file_MR()`: check SF1 existence and state count before filtering;
  fall back to unpolarized if filtering fails or returns None
- Validate against REF_M_29742 overlap run (histo vs h5 channel counts within 100 events)

## Network mount caveats

- Always use `timeout` for SNS data access
- Use `pixi run pytest ... --timeout=120`
- Phase 9 tests load polarized data (REF_M_29742: ~500K events) — may be slow over sshfs
- If mount is unresponsive, stop — do not retry

## OOM awareness

- Phase 8 loads both good and error event arrays simultaneously — use `del` after binning
- Phase 9 loads event arrays + pulse timing arrays — monitor memory
- Run tests individually first (`-k test_name`) before the full suite
- `scipy.special.lambertw` may allocate large intermediate arrays — ensure TOF bins
  are reasonable (40-100 bins, not thousands)

## When finished

1. Run all event h5 tests: `pixi run pytest tests/test_event_h5.py -v --timeout=120`
2. Run existing tests: `pixi run pytest tests/qreduce_test.py -x --timeout=120`
3. Run a quick sanity check loading both REF_M and REF_L h5 files:
   ```python
   pixi run python -c "
   from quicknxs.qreduce import NXSData
   d = NXSData('/SNS/REF_M/IPTS-9801/nexus/REF_M_29750.nxs.h5', use_caching=False)
   print(f'REF_M unpolarized: {len(d)} channels, {d[0].data.shape}')
   d = NXSData('/SNS/REF_M/IPTS-9801/nexus/REF_M_29742.nxs.h5', use_caching=False)
   print(f'REF_M polarized: {len(d)} channels')
   d = NXSData('/SNS/REF_L/IPTS-36119/nexus/REF_L_220030.nxs.h5', use_caching=False)
   print(f'REF_L: {len(d)} channels, {d[0].data.shape}, dangle={d[0].dangle:.3f}')
   "
   ```
4. Commit all changes with a descriptive message
5. **Update** `~/.claude/projects/-home-bvacaliuc-Projects-Claude-2/memory/MEMORY.md`:
   - All 9 phases complete with test results
   - Full list of modified/created files
   - Any remaining issues or known limitations
   - Mark the feature as implementation-complete, ready for integration testing
