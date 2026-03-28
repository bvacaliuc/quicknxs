# Plan: sshfs Timeout Protection for `locate_file()`

## Problem Statement

`_find_file_in_ipts()` calls `os.listdir(data_base)` on the calling thread before the
`ThreadPoolExecutor` is entered. When the sshfs mount is stale or slow, this call can
block indefinitely. The calling context matters:

| Caller | Thread | Consequence of stall |
|--------|--------|----------------------|
| `openByNumber()` in `main_gui.py` | Main (Qt) | Full GUI freeze — no input, no repaints |
| `NXSData.__new__()` in `qreduce.py` (int argument) | Main or worker | Same freeze if called from GUI |

The `ThreadPoolExecutor` + `as_completed(timeout=30)` already protects the `os.path.isfile`
calls inside the worker threads. The unprotected call is specifically:

```python
ipts_dirs = [d for d in os.listdir(data_base) if d.startswith('IPTS')]
```

---

## Why SIGALRM Is the Wrong Tool Here

The plan notes originally sketched SIGALRM as the solution. This section documents why
it fails for this specific scenario and what to do instead.

### The D-state problem

The sshfs mounts are mounted **without** `-o intr`:

```
fuse.sshfs (ro,nosuid,nodev,relatime,user_id=1000,group_id=1000)
```

When `os.listdir()` calls `getdents64` over sshfs:

1. The kernel FUSE module puts the calling process into **D-state** (uninterruptible sleep)
   while waiting for the FUSE daemon to respond
2. The FUSE daemon (sshfs) is in **S-state** (interruptible sleep) waiting for the SSH socket
3. **SIGALRM is delivered to the process, but the process cannot act on it** — it is in
   D-state and cannot receive signals

With `-o intr`, FUSE would put the process into **S-state** instead, allowing signals to
interrupt the wait. Without it, SIGALRM fires after the alarm period but the process
remains stuck until either the FUSE daemon responds or it is killed.

### What SIGALRM *would* protect against

SIGALRM works correctly when the blocking call is in S-state:

- A TCP socket `read()` waiting for data (interruptible)
- A file I/O on a local filesystem (fast)
- `os.listdir()` on a soft NFS mount (returns ETIMEDOUT after the soft timeout)

SIGALRM is appropriate for the `openByNumber()` guard if we also fix the mount options
(see Mitigation B below), but it should not be the *only* protection.

### Python 3 / PEP 475 note

Python 3.5+ (PEP 475) re-runs system calls that receive EINTR. **This does not
prevent SIGALRM from working** — if the signal handler raises an exception, the
exception propagates and the retry does not happen. The constraint is purely the
D-state issue above.

### SIGALRM thread constraint

`signal.signal()` and `signal.alarm()` must be called from the **main thread**.
`NXSData.__new__()` may be called from a `ThreadPoolExecutor` worker (e.g., during
a batch load). Placing SIGALRM inside `_find_file_in_ipts()` would raise
`ValueError: signal only works in main thread` in that case.

---

## Recommended Implementation: Two-Layer Protection

### Layer 1 (primary): Thread-isolate `os.listdir` inside `_find_file_in_ipts()`

Move `os.listdir(data_base)` into a daemon thread with a timeout. This works
regardless of D-state, thread context, or mount options:

```python
import threading

def _listdir_with_timeout(path, timeout=10.0):
    '''os.listdir with a wall-clock timeout. Returns list or None on timeout/error.'''
    result = []
    exc = []
    done = threading.Event()

    def _work():
        try:
            result.extend(os.listdir(path))
        except OSError as e:
            exc.append(e)
        finally:
            done.set()

    t = threading.Thread(target=_work, daemon=True)
    t.start()
    if done.wait(timeout=timeout):
        return result if not exc else None
    # Timed out — the thread is stuck (likely D-state sshfs)
    # The daemon thread will be garbage-collected when the process exits.
    # Log for diagnostics but do not block.
    return None
```

In `_find_file_in_ipts()`:

```python
def _find_file_in_ipts(data_base, candidates, timeout=30):
    try:
        all_entries = _listdir_with_timeout(data_base, timeout=10.0)
    except Exception:
        return None
    if not all_entries:
        return None
    ipts_dirs = [d for d in all_entries if d.startswith('IPTS')]
    # ... rest unchanged
```

**Why this works even in D-state**: The main thread is no longer the one in D-state.
The daemon thread is stuck, but the main thread (Qt event loop) continues. The stuck
daemon thread eventually dies when either the FUSE mount recovers or the process exits.
Daemon threads do not prevent process exit.

**Tradeoff**: Each stalled call leaks one daemon thread until mount recovery. In
practice, a stalled mount means multiple calls will each spawn a stuck thread. At 20
threads per pool + 1 listdir thread per call, repeated stall → hang cycles could
accumulate threads. In practice, users retry rarely enough that this is not a concern.
Add a guard: if a previous listdir thread is still alive, return `None` immediately
rather than spawning another.

### Layer 2 (secondary): SIGALRM in `openByNumber()` as a belt-and-suspenders guard

Once the mount has `-o intr` (see Mitigation B) or when on a soft-mount NFS, SIGALRM
provides a hard deadline for the entire `locate_file()` call including the thread pool:

```python
import signal

def _alrm_handler(signum, frame):
    raise TimeoutError('locate_file timed out after network stall')

@log_call
def openByNumber(self, number=None, do_plot=True):
    ...
    # Save previous handler (in case another part of the app uses SIGALRM)
    old_handler = signal.signal(signal.SIGALRM, _alrm_handler)
    signal.alarm(35)   # slightly longer than _find_file_in_ipts timeout=30
    try:
        found_path = locate_file(int(number),
                                  histogram=self.ui.histogramActive.isChecked(),
                                  old_format=self.ui.oldFormatActive.isChecked())
    except (ValueError, TypeError):
        found_path = None
    except TimeoutError:
        found_path = None
        self.ui.statusbar.showMessage(u'Search timed out — is the SNS mount available?')
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)
        QtWidgets.QApplication.instance().restoreOverrideCursor()
    ...
```

**Platform guard**: wrap the SIGALRM block with `if hasattr(signal, 'SIGALRM')` so
the code runs on Windows without error (though quicknxsv1 only runs on Linux in
production; this future-proofs it).

---

## Engineering Tradeoffs Summary

| Aspect | SIGALRM | Thread isolation |
|--------|---------|-----------------|
| Protects against D-state stall | **No** (requires `-o intr`) | **Yes** |
| Works from worker thread | **No** (main thread only) | Yes |
| Works on Windows | No | Yes |
| Protects `os.listdir` specifically | Yes (if S-state) | Yes |
| Protects full `locate_file()` call | Yes (if S-state) | No (thread pool already protected) |
| Code complexity | Low (~10 lines) | Moderate (~20 lines) |
| Risk of stuck threads accumulating | N/A | Low (daemon threads, rare stalls) |
| Risk of interfering with other alarm users | Low (save/restore handler) | N/A |

**Recommendation**: Implement Layer 1 (thread isolation for `os.listdir`) as the primary
fix. Add Layer 2 (SIGALRM in `openByNumber()`) as a belt-and-suspenders guard that also
improves the user message when the full search times out.

---

## Mitigation B: Fix the sshfs Mount Options (not a code change)

The root cause of D-state stalls is the mount missing `-o intr,reconnect,ServerAliveInterval=15`:

```bash
# Recommended remount:
sudo umount -l /home/bvacaliuc/SNS/REF_M
sshfs 6ov@analysis.sns.gov:/SNS/REF_M/ /home/bvacaliuc/SNS/REF_M \
  -o ro,intr,reconnect,ServerAliveInterval=15,ServerAliveCountMax=3
```

With `-o intr`, FUSE puts the calling process into S-state (interruptible) rather than
D-state, making SIGALRM work correctly. With `reconnect,ServerAliveInterval=15`, the
sshfs daemon detects dead connections within ~45 seconds and returns an error, naturally
unblocking any waiting process.

This is a **system-level fix** that benefits all programs using the mount, not just
quicknxsv1. The code fix should be implemented regardless so that quicknxsv1 degrades
gracefully even if a user has not updated their mount options.

---

## Files to Change

| File | Change |
|------|--------|
| `quicknxs/qreduce.py` | Add `_listdir_with_timeout()`; modify `_find_file_in_ipts()` to use it |
| `quicknxs/main_gui.py` | Add SIGALRM guard in `openByNumber()` (Layer 2) |
| `tests/qreduce_test.py` | Add `ListdirTimeoutTests` class |
| `tests/main_gui_test.py` | Add `test_open_by_number_timeout` test |

---

## TDD Test Cases

### `tests/qreduce_test.py` — `ListdirTimeoutTests`

```python
class ListdirTimeoutTests(unittest.TestCase):

    def test_listdir_returns_entries_on_success(self):
        '''_listdir_with_timeout returns directory entries normally.'''
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, 'IPTS-1'))
            os.makedirs(os.path.join(tmpdir, 'shared'))
            result = qreduce._listdir_with_timeout(tmpdir, timeout=5.0)
        self.assertIsNotNone(result)
        self.assertIn('IPTS-1', result)

    def test_listdir_returns_none_on_oserror(self):
        '''_listdir_with_timeout returns None for a non-existent path.'''
        result = qreduce._listdir_with_timeout('/nonexistent/path/xyz', timeout=5.0)
        self.assertIsNone(result)

    def test_listdir_returns_none_on_timeout(self):
        '''_listdir_with_timeout returns None when the call does not complete.'''
        import threading
        block = threading.Event()

        original_listdir = os.listdir
        def slow_listdir(path):
            block.wait()  # block until test releases it
            return original_listdir(path)

        with mock.patch('os.listdir', side_effect=slow_listdir):
            result = qreduce._listdir_with_timeout('/tmp', timeout=0.1)

        block.set()  # release the stuck thread
        self.assertIsNone(result)

    def test_find_file_returns_none_when_listdir_times_out(self):
        '''_find_file_in_ipts returns None gracefully when os.listdir times out.'''
        with mock.patch('quicknxs.qreduce._listdir_with_timeout', return_value=None):
            result = qreduce._find_file_in_ipts('/SNS/REF_M', [('nexus', 'REF_M_99999.nxs.h5')])
        self.assertIsNone(result)
```

### `tests/main_gui_test.py` — addition to `FileLoadingFixes`

```python
@unittest.skipUnless(hasattr(signal, 'SIGALRM'), 'SIGALRM not available')
def test_open_by_number_sigalrm_timeout(self):
    '''openByNumber() handles TimeoutError from SIGALRM gracefully.'''
    with mock.patch('quicknxs.main_gui.locate_file',
                    side_effect=TimeoutError('stall')):
        result = self.gui.openByNumber('40205')
    self.assertFalse(result)
    self.assertIn('timed out', self.gui.ui.statusbar.currentMessage().lower())
```

---

## Implementation Order (TDD)

1. Write `ListdirTimeoutTests` and `test_open_by_number_sigalrm_timeout` → confirm red
2. Implement `_listdir_with_timeout()` in `qreduce.py`
3. Modify `_find_file_in_ipts()` to call `_listdir_with_timeout()`
4. Add SIGALRM guard to `openByNumber()` in `main_gui.py`
5. Run tests → confirm green
6. Integration test: manually stall the mount (`sudo tc qdisc add dev eth0 root netem delay 60s`)
   or test with `timeout=0.01` to simulate stall

---

## Out of Scope

- Making `NXSData.__new__(int)` non-blocking — this requires the QThread refactor (next step #3)
- Rewriting sshfs mount unit files to include `-o intr` — system administration task
