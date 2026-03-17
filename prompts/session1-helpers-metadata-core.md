# Session 1: Helpers, Metadata Extraction, and Core Event-to-Histogram

## Context

You are working in the **quicknxsv1** project (a Python/Qt neutron reflectometry
application) on branch `feature/read-event-nexus`. The goal is to add support for
reading modern `.nxs.h5` event-mode NeXus files.

**Read these files first** (in this order):
1. `CLAUDE.md` — project conventions, capabilities, CI/CD, branch model
2. `plan/read-event-nexus-h5.md` — the full implementation plan (scientist-reviewed)
3. `~/.claude/projects/-home-bvacaliuc-Projects-Claude-2/memory/MEMORY.md` — prior session state

## Your task

Implement **Phases 1, 2, and 3** from the plan using red/green TDD. This covers:

- **Phase 1**: Helper functions (`_get_detector_dimensions()`, `_get_daslog_value()`,
  `_read_instrument_settings()`, `_decode()`)
- **Phase 2**: Metadata extraction (`MRDataset._collect_info_h5()` and
  `LRDataset._collect_info_h5()`)
- **Phase 3**: Core event-to-histogram conversion (`MRDataset.from_event_h5()`,
  `LRDataset.from_event_h5()`, format detection, routing in `_read_file_MR`/`_read_file_LR`)

## TDD workflow

For each step:
1. **RED**: Write the failing test in `tests/test_event_h5.py`
2. Run the test with `pixi run pytest tests/test_event_h5.py::<TestClass>::<test_method> -x`
   to confirm it fails
3. **GREEN**: Implement the minimum code in `quicknxs/qreduce.py` to make it pass
4. Run the test again to confirm it passes
5. Move to the next step

## Critical implementation details

### Angles (BL4B)
The plan documents this carefully in the "BL4B angle handling" section:
- `self.dangle = self.tthd` (detector arm 2θ), NOT `self.thi`
- `self.sangle = self.ths`
- Store all three raw angles (`thi`, `ths`, `tthd`) on the LRDataset object

### Missing DASlogs armor
Every `_get_daslog_value()` call in `_collect_info_h5()` methods MUST have a `default=`
parameter. See the "General DASlogs missing-data strategy" table in the plan.

### Settings files
Create `quicknxs/config/ref_l_settings.json` and `quicknxs/config/ref_m_settings.json`
with the date-indexed entries specified in the plan.

## Network mount caveats

Test data is on sshfs mounts at `/SNS/REF_M/` and `/SNS/REF_L/`. Rules:
- **Always use `timeout` when running tests** that access these paths
- Use `pixi run pytest ... --timeout=120` or wrap commands with `timeout 30`
- If a mount is unresponsive, stop accessing it — do not retry in a loop
- Never use background Bash commands for network mount operations

## OOM awareness

This machine has 8 GB RAM. To avoid OOM:
- Run tests selectively with `-k` before full suites
- Avoid parallel subagents when running tests
- Close HDF5 file handles promptly in test code

## When finished

1. Run the full test file: `pixi run pytest tests/test_event_h5.py -v --timeout=120`
2. Run existing tests to verify no regressions: `pixi run pytest tests/qreduce_test.py -x --timeout=120`
3. Commit all changes with a descriptive message
4. **Update** `~/.claude/projects/-home-bvacaliuc-Projects-Claude-2/memory/MEMORY.md`
   with a checkpoint:
   - Which phases are complete (with test pass/fail counts)
   - Which files were modified or created
   - Any issues encountered or deviations from the plan
   - What remains for Session 2 (Phases 4-7)
