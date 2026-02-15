# Plan: Fix OOM Crash During Corrected Off-Specular Extraction

## Context

The application crashes with exit code 137 (SIGKILL from Linux OOM killer) when performing a full reduction with all options selected in the ReduceDialog. The `strace.dat` confirms the pixi wrapper process is killed by SIGKILL. The `debug.log` last entry was:

```
[INFO] - 2026-02-14 21:10:30,832 - gui_utils.py:97:execute Extracting corrected off-specular data...
```

This crash occurs DURING `extract_offspecular_corr()` — **before** the previous OOM fix's `release_raw_data()` call can run.

## Root Cause Analysis

### Memory State at Crash Point

When `extract_offspecular_corr()` begins (gui_utils.py:98), the following data is simultaneously resident in memory:

| Structure | Location | Est. Size | Status |
|---|---|---|---|
| `raw_data` — 10 NXSData instances, each containing 3D detector arrays (304x256x150 float64) | `Exporter.raw_data` | **~2.5 GB** | Needed by extract_offspecular_corr |
| `output_data['Specular']` — 1D reflectivity curves | `Exporter.output_data` | ~1 MB | Already consumed, not needed |
| `output_data['OffSpec']` — 7-column rdata arrays per dataset per channel | `Exporter.output_data` | **~1-2 GB** | Redundant (see below) |
| `corr_data` — normalization file re-read from disk | `extract_offspecular_corr` local | **~256 MB** | Redundant read |
| `OffSpecular` intermediates — Qx, Qz, ki_z, kf_z, S, dS arrays per dataset | Loop locals | ~200-500 MB | Transient but overlapping |
| `DetectorTailCorrector` — shape function + convolution intermediates | `corrector` local | ~50-100 MB | Persistent through loop |

**Peak total: ~4.5-6+ GB** — enough to trigger the OOM killer on a 4-8 GB system.

### Three Root Causes

**Root Cause 1: OffSpec output is redundant when OffSpecCorr is also selected.**

`extract_offspecular()` (line 659) and `extract_offspecular_corr()` (line 688) produce nearly identical data — same Qx, Qz, ki_z, kf_z, dS arrays, differing only in the S column (corrected vs uncorrected). When both are selected:
- OffSpec (~1-2 GB) is built first and persists in `output_data['OffSpec']`
- OffSpecCorr (~1-2 GB) is then built, doubling memory usage
- `smooth_offspec()` (line 734) **prefers OffSpecCorr** when available, making OffSpec wasted
- `execute()` (lines 108-109) already has logic to delete OffSpec when not explicitly exported

**Root Cause 2: Normalization data is redundantly re-read from disk.**

`extract_offspecular_corr()` (lines 697-702) reads the normalization file from disk to create `corr_data`, even though the same normalization file's data is already loaded in `raw_data` (or was loaded during `Exporter.__init__` → `read_data()`). The normalization datasets are stored in `self.norms`, which came from `refli.options['normalization']` — the same files that produced entries in `raw_data`. This adds ~256 MB of redundant memory.

**Root Cause 3: OffSpecular intermediate objects persist across loop iterations.**

In both `extract_offspecular()` and `extract_offspecular_corr()`, the `offspec = OffSpecular(...)` object (containing 6 large 2D arrays) from the previous iteration persists until the next iteration reassigns the variable. During OffSpecCorr, the `corrector(S)` call inside `correct_shape_set` also creates per-row copies. No explicit cleanup occurs between iterations.

### Why the Previous Fix Didn't Help

The previous OOM fix (commit `6b4e172`) moved `release_raw_data()` between extraction and smoothing phases. But the crash occurs DURING extraction — `extract_offspecular_corr()` itself needs `raw_data`, so it cannot be released beforehand. The fix correctly prevents OOM during smoothing, but this is a separate crash point earlier in the pipeline.

## Implementation Steps

Steps are ordered by memory impact (highest first). Each is independently testable.

---

### Step 1: Defer OffSpec extraction when OffSpecCorr is also selected (~1-2 GB saved)

**File:** `quicknxs/gui_utils.py` — `Reducer.execute()` (line 78)

**Problem:** When both `exportOffSpecular` (or `exportOffSpecularSmoothed`) AND `exportOffSpecularCorr` are selected, `extract_offspecular()` runs first, creating ~1-2 GB of OffSpec data that persists in memory while `extract_offspecular_corr()` builds a near-duplicate set.

**Fix:** Skip `extract_offspecular()` when `exportOffSpecularCorr` is also selected. The OffSpec data can be derived from OffSpecCorr data (they are identical except for the S column), or OffSpec can be extracted after OffSpecCorr finishes and raw_data is released if it is independently needed for export.

Since `smooth_offspec()` already prefers OffSpecCorr (line 734), and `export_data` / `plot_result` iterate all `output_data.items()`, the simplest approach is:

```python
# In Reducer.execute():
needs_offspec = opts['exportOffSpecular'] or opts['exportOffSpecularSmoothed']
needs_offspec_corr = opts['exportOffSpecularCorr']

if needs_offspec and not needs_offspec_corr:
    # Only uncorrected off-specular needed
    info('Extracting off-specular data...')
    self.exporter.extract_offspecular()
elif needs_offspec_corr:
    # Corrected off-specular needed — extract it (smoothing will use it)
    info('Extracting corrected off-specular data...')
    self.exporter.extract_offspecular_corr()
    if needs_offspec:
        # Also need uncorrected for separate export — create from corr by copying
        # and restoring uncorrected S values. But this still needs raw_data.
        # Alternative: extract uncorrected AFTER releasing raw_data is not possible.
        # Best approach: extract both but release OffSpec before starting OffSpecCorr.
        pass
```

**Refined approach:** Since both extractions need `raw_data`, the cleanest fix is:

1. If both are selected, extract OffSpecCorr ONLY (since smoothing prefers it)
2. If user also needs OffSpec for direct export, generate it from OffSpecCorr by copying the arrays and replacing S with uncorrected values — BUT this also needs raw_data
3. **Simplest effective fix:** When both are selected, extract OffSpec first, then immediately before starting OffSpecCorr, move OffSpec data out of `output_data` into a local variable, extract OffSpecCorr, then restore OffSpec to `output_data`:

```python
if needs_offspec:
    info('Extracting off-specular data...')
    self.exporter.extract_offspecular()

if needs_offspec_corr:
    # Temporarily remove OffSpec from memory during OffSpecCorr extraction
    offspec_backup = self.exporter.output_data.pop('OffSpec', None)
    info('Extracting corrected off-specular data...')
    self.exporter.extract_offspecular_corr()
    if offspec_backup is not None and opts['exportOffSpecular']:
        self.exporter.output_data['OffSpec'] = offspec_backup
    del offspec_backup
```

Wait — popping and holding locally doesn't free memory. The **actually effective** approach:

**Final approach:** When both OffSpec AND OffSpecCorr are selected, skip `extract_offspecular()` entirely. Instead, produce OffSpec as a side-effect of `extract_offspecular_corr()` by saving the uncorrected S values before correction:

```python
# In Exporter.extract_offspecular_corr(), add parameter to also produce uncorrected:
def extract_offspecular_corr(self, also_uncorrected=False):
    output_data = ...  # OffSpecCorr output
    if also_uncorrected:
        uncorr_output_data = dict([(channel, []) for channel in self.channels])
        # ... same column_units/names setup ...

    for refli in self.refls:
        for channel in self.channels:
            offspec = OffSpecular(fdata[channel], **opts)
            # Save uncorrected rdata BEFORE correction
            if also_uncorrected:
                rdata_uncorr = np.asarray([...]).transpose((1, 2, 0))
                uncorr_output_data[channel].append(rdata_uncorr)
            S = corrector(S)  # Apply correction
            rdata = np.asarray([...]).transpose((1, 2, 0))
            output_data[channel].append(rdata)

    self.output_data['OffSpecCorr'] = output_data
    if also_uncorrected:
        self.output_data['OffSpec'] = uncorr_output_data
```

This avoids building OffSpecular objects TWICE (once for OffSpec, once for OffSpecCorr), saving ~500 MB of intermediate objects plus the CPU time of double extraction. The small cost is storing both rdata arrays simultaneously per iteration (~50 MB), which is far less than building all OffSpec first (~1-2 GB cumulative) and then all OffSpecCorr.

**Changes:**

1. **`quicknxs/qio.py`** — Add `also_uncorrected=False` parameter to `extract_offspecular_corr()`. When True, save uncorrected rdata arrays to `self.output_data['OffSpec']` alongside the corrected ones.

2. **`quicknxs/gui_utils.py`** — In `Reducer.execute()`, when both OffSpec and OffSpecCorr are needed, call `extract_offspecular_corr(also_uncorrected=True)` instead of calling both `extract_offspecular()` and `extract_offspecular_corr()` separately:
   ```python
   needs_offspec = opts['exportOffSpecular'] or opts['exportOffSpecularSmoothed']
   needs_offspec_corr = opts['exportOffSpecularCorr']

   if needs_offspec and not needs_offspec_corr:
       info('Extracting off-specular data...')
       self.exporter.extract_offspecular()
   elif needs_offspec_corr:
       info('Extracting corrected off-specular data...')
       self.exporter.extract_offspecular_corr(also_uncorrected=needs_offspec)
   ```

**Memory savings:** ~1-2 GB (eliminates the full OffSpec dataset from being built separately while OffSpecCorr is also being built).

---

### Step 2: Reuse normalization data already in memory (~256 MB saved)

**File:** `quicknxs/qio.py` — `Exporter.extract_offspecular_corr()` (lines 697-702)

**Problem:** The normalization file is re-read from disk to create `corr_data` for the DetectorTailCorrector, even though the normalization file's data may already be accessible.

**Current code:**
```python
corr_ds = self.norms[0]
if type(corr_ds.origin) is list:
    flist = [origin[0] for origin in corr_ds.origin]
    corr_data = NXSMultiData(flist, **corr_ds.read_options)[0]
else:
    corr_data = NXSData(corr_ds.origin[0], **corr_ds.read_options)[0]
corrector = DetectorTailCorrector(corr_data.xdata, x0=corr_ds.options['x_pos'])
```

**Analysis:** `self.norms[0]` is a normalization dataset object. The normalization data is read into `self.raw_data` during `read_data()` if the normalization file happens to be one of the reflection files. However, normalization files are typically separate datasets not in `self.refls`, so they are NOT in `raw_data`.

**Fix:** Check if the normalization data is already in `raw_data` before re-reading:
```python
corr_ds = self.norms[0]
norm_number = corr_ds.options.get('number', None)
if norm_number is not None and norm_number in self.raw_data:
    corr_data = self.raw_data[norm_number][0]
elif type(corr_ds.origin) is list:
    flist = [origin[0] for origin in corr_ds.origin]
    corr_data = NXSMultiData(flist, **corr_ds.read_options)[0]
else:
    corr_data = NXSData(corr_ds.origin[0], **corr_ds.read_options)[0]
corrector = DetectorTailCorrector(corr_data.xdata, x0=corr_ds.options['x_pos'])
del corr_data  # Only xdata was needed, release the rest
```

Additionally, add `del corr_data` after the corrector is created, since only `corr_data.xdata` is needed (it's copied into the corrector during `__init__`).

**Memory savings:** ~256 MB from avoiding redundant disk read, plus ~256 MB from early `del corr_data`.

---

### Step 3: Release intermediate objects within extraction loops (~200-500 MB saved)

**File:** `quicknxs/qio.py` — `extract_offspecular()` and `extract_offspecular_corr()`

**Problem:** The `offspec` object (containing 6 large 2D arrays: Qx, Qz, ki_z, kf_z, S, dS) persists from one loop iteration to the next. Additionally, the local variables `Qx, Qz, ki_z, kf_z, S, dS` hold references to these arrays.

**Fix:** Add explicit `del` statements after extracting rdata:

```python
for channel in self.channels:
    offspec = OffSpecular(fdata[channel], **opts)
    Qx, Qz, ki_z, kf_z, S, dS = (offspec.Qx, offspec.Qz, offspec.ki_z, offspec.kf_z,
                                   offspec.S, offspec.dS)
    del offspec  # Release the OffSpecular object (still have refs to its arrays)

    # ... build rdata ...
    rdata = np.asarray([Qx[:, PN:P0], ...]).transpose((1, 2, 0))
    output_data[channel].append(rdata)
    ki_max = max(ki_max, ki_z.max())
    del Qx, Qz, ki_z, kf_z, S, dS, rdata  # Release array references
```

Apply the same pattern to both `extract_offspecular()` (line 676) and `extract_offspecular_corr()` (line 714).

**Memory savings:** ~200-500 MB (one OffSpecular object's worth of arrays freed earlier per iteration).

---

### Step 4: Release Specular output before off-specular extraction (~small but principled)

**File:** `quicknxs/gui_utils.py` — `Reducer.execute()`

**Problem:** `output_data['Specular']` is built before off-specular extraction but is not needed until export/plotting. It occupies memory during the peak-memory extraction phase.

**Fix:** This is a minor saving (~1 MB for 1D data) but follows the principle of minimizing concurrent memory. Skip this change — the savings are negligible and the code complexity isn't worth it for specular data.

**Decision:** Skip — not worth the complexity for ~1 MB savings.

---

### Step 5: Add gc.collect() after releasing OffSpecular intermediates

**File:** `quicknxs/qio.py`

**Problem:** Python's reference-counting GC immediately frees objects when their refcount hits zero (from `del`), but numpy arrays allocated via the C allocator may not be returned to the OS immediately. Cyclic references (if any) also require the cyclic GC.

**Fix:** Add `gc.collect()` at the end of `extract_offspecular_corr()`, after the extraction loop completes and before the method returns. Do NOT add gc.collect() inside the inner loop — it would be too slow.

```python
import gc

def extract_offspecular_corr(self, also_uncorrected=False):
    # ... extraction loop ...
    self.output_data['OffSpecCorr'] = output_data
    if also_uncorrected:
        self.output_data['OffSpec'] = uncorr_output_data
    gc.collect()
```

**Memory savings:** Variable — ensures cyclic references are cleaned up before the next phase.

---

### Step 6: Add tests

**File:** `tests/qio_test.py` — `ExportTest` class

**New tests:**

1. **`test_extract_offspecular_corr_also_uncorrected`**: Call `extract_offspecular_corr(also_uncorrected=True)`. Verify both `output_data['OffSpecCorr']` and `output_data['OffSpec']` are populated. Verify OffSpec S values differ from OffSpecCorr S values (correction was applied). Verify all other columns (Qx, Qz, ki_z, kf_z, dS) are identical between OffSpec and OffSpecCorr.

2. **`test_combined_extraction_memory_equivalence`**: Extract using both methods:
   - Method A: `extract_offspecular()` then `extract_offspecular_corr()`
   - Method B: `extract_offspecular_corr(also_uncorrected=True)`
   Verify that the OffSpec output from Method A matches Method B (array equality).
   Verify that the OffSpecCorr output is identical in both methods.

3. **`test_corr_data_cleanup`**: Verify that after `extract_offspecular_corr()` returns, no reference to the normalization file's full data persists (only the corrector's shape function).

**File:** `tests/main_gui_test.py`

4. **`test_execute_combined_offspec`**: Mock the Exporter to verify that when both `exportOffSpecular` and `exportOffSpecularCorr` are True, `extract_offspecular()` is NOT called but `extract_offspecular_corr(also_uncorrected=True)` IS called.

---

## Summary of Changes

| File | Changes | Memory Saved |
|---|---|---|
| `quicknxs/qio.py` | Add `also_uncorrected` param to `extract_offspecular_corr()`; add `del corr_data` after corrector creation; add `del offspec, Qx, Qz, ...` in extraction loops; add `gc.collect()` at end; reuse norm data from raw_data if available | ~2-3 GB peak |
| `quicknxs/gui_utils.py` | Restructure `execute()` to call `extract_offspecular_corr(also_uncorrected=True)` when both OffSpec and OffSpecCorr are selected | ~1-2 GB |
| `tests/qio_test.py` | Add 3 new tests | — |
| `tests/main_gui_test.py` | Add 1 new test | — |

## Expected Peak Memory After Fix

| Before Fix | After Fix |
|---|---|
| raw_data (~2.5 GB) + OffSpec (~1-2 GB) + OffSpecCorr building (~1-2 GB) + corr_data (~256 MB) = **~5-6 GB** | raw_data (~2.5 GB) + OffSpecCorr+OffSpec building simultaneously (~50 MB overhead per iteration) = **~3 GB** |

The ~3 GB peak should be manageable on a 4 GB system (with ~1 GB for OS + Python overhead), and comfortable on 8 GB systems.

## Verification

```bash
cd /home/bvacaliuc/Projects/Claude/quicknxsv1
make test  # All existing + new tests pass
```

For real-world validation: run full reduction with all options selected on actual MR reflectometer data and confirm:
1. No OOM kill (process completes)
2. Output files are identical to pre-change output for both OffSpec and OffSpecCorr
3. OffSpec arrays from `also_uncorrected=True` match those from standalone `extract_offspecular()`
