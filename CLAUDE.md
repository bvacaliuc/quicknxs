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

## Secure Temporary Files

When a task requires writing a temporary script or data file (e.g. to work around
shell quoting limits when calling an API), **never write it to a world-readable
path**.  `/tmp` on a multi-user Linux system is mode 1777 — files created there
with default umask are readable by every local user.

**Always create temporary files with mode 600 (owner read/write only):**

```python
import os, tempfile

# Preferred: tempfile.NamedTemporaryFile — mode 600 by default
with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False) as fh:
    fh.write(script_content)
    tmp_path = fh.name
try:
    # use tmp_path ...
finally:
    os.unlink(tmp_path)   # always clean up
```

Or with the Write tool followed by an immediate chmod:

```bash
# After writing the file, restrict permissions immediately
chmod 600 /path/to/tempfile
```

**Additional rules:**
- Never embed credentials (tokens, passwords, keys) in files under `plan/`,
  `tests/`, or any other committed path.  Use environment variables or
  `~/.netrc` / `~/.config` files (also mode 600) instead.
- Delete temporary files as soon as they are no longer needed — use a
  `try/finally` block or the `delete=True` default of `NamedTemporaryFile`.
- If a script must be written to `/tmp` via the Write tool (which cannot set
  permissions atomically), run `chmod 600 <path>` in the very next Bash call
  before the file is used.

## CI/CD

### Branching model
- **`next`** is the default integration branch — all PRs target `next`
- **`master`** is the legacy stable branch — leave it alone; never commit directly to it
- Feature/fix branches follow `feature/**`, `bug/**`, `fix/**`, `chore/**` naming
- Always ensure your branch is up to date with `origin/next` before opening a PR

### Branch protection
- Both `next` and `master` require `lint` and `test` CI checks to pass before merge
- `next` has `enforce_admins: true` — no bypass, even via API; always go through a PR
- Never force-push to any protected branch

### GitHub Actions workflows
- **`ci.yml`** — lint (`ruff check quicknxs/`) + test (`pytest --cov=quicknxs`) on every push/PR
- **`update-lockfile.yml`** — monthly pixi.lock refresh; opens a PR on `chore/update-pixi-lockfile`

### Required secrets (Settings → Secrets and variables → Actions)
- **`CODECOV_TOKEN`** — upload coverage reports to Codecov after each test run
- **`WORKFLOW_PAT`** — classic PAT with repo *Contents* and *Pull requests* write access;
  required because `GITHUB_TOKEN` pushes are silenced by GitHub's anti-loop protection,
  meaning `peter-evans/create-pull-request` would create a PR branch that never receives
  CI and therefore can never be merged automatically.  If this PAT expires, re-encrypt
  and re-upload it via the GitHub Secrets API using PyNaCl sealed box encryption.

### GitHub Actions gotchas
- `workflow_dispatch` check runs do **not** satisfy PR branch protection — only check runs
  triggered by a `push` or `pull_request` event count toward required status checks
- The `GITHUB_TOKEN` anti-loop rule suppresses push events from actions using that token;
  any workflow that creates branches and needs CI to run on them must use a PAT instead

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

3. **Analyze the crash:** Read the tail of the Python PID's strace file. Look for:
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
