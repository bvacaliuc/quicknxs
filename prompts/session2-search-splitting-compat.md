# Session 2: File Search, Event Splitting, Backward Compatibility, Makefile

## Context

You are working in the **quicknxsv1** project on branch `feature/read-event-nexus`.
This is the second of three implementation sessions for `.nxs.h5` event file support.
This session was aborted prematurely due to token limits, please review work done so far.

**Read these files first** (in this order):
1. `CLAUDE.md` — project conventions
2. `plan/read-event-nexus-h5.md` — the full implementation plan
3. `~/.claude/projects/-home-bvacaliuc-Projects-Claude-2/memory/MEMORY.md` — **critical:
   contains checkpoint from Session 1** with completed phases, modified files, and any
   issues encountered

## Your task

Implement **Phases 4, 5, 6, and 7** from the plan. Session 1 completed Phases 1-3
(helpers, metadata, core event-to-histogram). Build on that work.

- **Phase 4**: File search — update `locate_file()` to find `.nxs.h5` files, add
  `H5_BASE_SEARCH` to instrument configs, make `time_from_header()` robust
- **Phase 5**: Event splitting support — port the event-split logic from the existing
  `from_event()` to `from_event_h5()` for both `MRDataset` and `LRDataset`
- **Phase 6**: Backward compatibility verification — ensure legacy `*_histo.nxs` and
  `*_event.nxs` files still load correctly after all changes
- **Phase 7**: Makefile integration — add `test-h5` target, update documentation

## TDD workflow

Same as Session 1:
1. **RED**: Write failing test
2. Run test to confirm failure
3. **GREEN**: Implement minimum code
4. Run test to confirm pass

Add new tests to `tests/test_event_h5.py` (already created in Session 1).

## Phase-specific notes

### Phase 4: locate_file()
- Legacy formats searched **first** and preferred (preserves polarization channels)
- `.nxs.h5` is the fallback when no legacy file is found
- Search pattern: `*/nexus/{INSTRUMENT}_{number}.nxs.h5`
- Add `H5_BASE_SEARCH` to `quicknxs/config/ref_m.py` and `quicknxs/config/ref_l.py`
- The `time_from_header()` function must handle non-Group items in `.nxs.h5` files

### Phase 5: Event splitting
- The existing `from_event()` has event-split logic using `event_split_bins` and
  `event_split_index` options — port this to `from_event_h5()`
- Events are split by time (proton charge pulse boundaries), not by pixel
- Test that 4 splits sum to the total

### Phase 6: Backward compatibility
- Run the existing test suite: `pixi run pytest tests/qreduce_test.py -x --timeout=120`
- Test legacy histo files still load via `NXSData()`
- This is a regression guard — these tests should pass without changes

### Phase 7: Makefile
- Add `test-h5` target: `pixi run pytest tests/test_event_h5.py -v --timeout=120`
- Do NOT modify CLAUDE.md — it was already updated in a prior session

## Network mount caveats

- Always use `timeout` for SNS data access
- Use `pixi run pytest ... --timeout=120`
- If mount is unresponsive, stop — do not retry

## OOM awareness

- Run tests selectively with `-k` before full suites
- Phase 5 event splitting tests load data multiple times — run individually first
- Phase 6 regression tests may load large legacy files — use `--timeout=120`

## When finished

1. Run all event h5 tests: `pixi run pytest tests/test_event_h5.py -v --timeout=120`
2. Run existing tests: `pixi run pytest tests/qreduce_test.py -x --timeout=120`
3. Commit all changes with a descriptive message
4. **Update** `~/.claude/projects/-home-bvacaliuc-Projects-Claude-2/memory/MEMORY.md`:
   - Which phases are complete (with test pass/fail counts)
   - Which files were modified or created
   - Any issues or deviations from the plan
   - What remains for Session 3 (Phases 8-9)
