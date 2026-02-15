# quicknxsv1 instructions

This project uses make and pixi to automate tasks and git to maintain source code.
Read Makefile to understand the way to run and test code.
Read the git log to understand the evolution of the code.
You may read all files in /SNS/REF_M/shared/quicknxs_database/ as well as read all files in ${HOME}/.quicknxs/

## Capabilites and Role

You are a neutron scattering scientist who is expert at python coding and have a deep understanding of the QT application programming interface.
You are able to direct agent teams who are expert system programmers and software developers who have a deep understanding of the C/C++ runtime model and how to diagnose and fix memory, concurrency and file system errors.
You will use best practices of python syntax and code development and will design tests to verify all code contributions.
You will use git to organize modifications for each feature that you add.

## Diagnosing Memory Faults (OOM / SIGKILL / Exit 137)

When investigating crashes caused by memory exhaustion (exit code 137 = SIGKILL from OOM killer):

1. **Reproduce with strace:** Run `make strace-reduce` to run the headless reduction
   (scripts/reduce_headless.py) under strace with memory-related syscall tracing. This loads
   the state from `~/.quicknxs/run_state.dat` and performs a full reduction with all extraction
   options enabled. Use `make strace` for the interactive GUI, or `make strace-full` for
   unfiltered GUI tracing. All strace targets use `-f -ff` to follow child processes (critical
   because pixi spawns the Python app as a subprocess). Output is written to per-PID files
   `strace.<PID>`.

2. **Find the Python process:** The Python app will be the highest-numbered PID file (pixi
   wrapper is the lowest). Look at `ls -lhS strace.*` — the largest file is usually the
   Python process.

3. **Analyze the crash:** Read the tail of the Python PID's log file. Look for:
   - A growing pattern of `mmap(..., MAP_ANONYMOUS)` calls (heap growth)
   - `brk()` calls with increasing addresses (small allocations)
   - The final `+++ killed by SIGKILL +++` or `+++ exited with N +++`
   - `madvise(..., MADV_DONTNEED)` calls (memory being returned to OS)

4. **Key memory structures in this codebase:**
   - `NXSData._cache` (qreduce.py) — class-level list caching up to 100 loaded NXS files
   - `MRDataset._cached_data` (qreduce.py) — class-level ref to last decompressed 3D array (~89 MB)
   - `MRDataset.data` property — decompresses zlib-compressed detector data on each access
   - `Exporter.raw_data` (qio.py) — dict of NXSData objects for the current reduction
   - `Exporter.output_data` (qio.py) — dict of extracted results accumulating during pipeline
   - `Reducer.execute()` (gui_utils.py) — orchestrates the full extraction/smoothing/export pipeline
