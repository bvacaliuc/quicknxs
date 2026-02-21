# Plan: Fix Remaining OOM Crash During Reduction Pipeline

## Context

Despite the previous fixes (commit `6c838fd`: combined extraction with `also_uncorrected`, `del` intermediates, `del corr_data`), the application still crashes with exit code 137 (OOM kill) during `extract_offspecular_corr()`.

The target system has **7.6 GB RAM** with only **~4.1 GB available** (3.5 GB already used by other processes) and **swap nearly full** (7.3/7.8 GB used). This means the reduction pipeline has at most **~4 GB** before the OOM killer fires.

## Revised Root Cause Analysis

### Key Architectural Discovery: `NXSData._cache` (Class-Level Cache)

`NXSData` (qreduce.py:191) maintains a **class-level** `_cache` list that holds up to `MAX_CACHE=100` NXSData objects. Every file loaded during the GUI session — including files the user browsed through before starting the reduction — is cached here.

**Critical problem:** `release_raw_data()` (qio.py:610) only clears `self.raw_data` (the Exporter's reference), but the **same NXSData objects remain alive in `NXSData._cache`**. The cache is NEVER cleared during reduction. This means `release_raw_data()` frees almost nothing — it only drops the Exporter's dict references, but the objects' refcount stays >0 due to the class-level cache.

### Key Architectural Discovery: `MRDataset._cached_data` (Decompressed Data Cache)

When `USE_COMPRESSION=True` (which it is on all non-cluster machines, qreduce.py:90), MRDataset stores 3D detector arrays compressed via zlib (~5-18 MB per dataset instead of ~89 MB). However, `MRDataset._cached_data` (qreduce.py:1179) is a **class-level** reference to the LAST decompressed 3D array (~89 MB). This cache is never explicitly cleared.

### Revised Memory Budget at Crash Point

When `extract_offspecular_corr()` runs with "all options selected" on 10 datasets:

| Structure | Location | Compressed | Decompressed | Notes |
|---|---|---|---|---|
| NXSData._cache (GUI session files) | Class-level | 200-400 MB | — | User may have browsed 20+ files |
| raw_data (10 NXSData objects) | Exporter.raw_data | 0 (shared refs with cache) | — | Same objects as cache |
| MRDataset._cached_data | Class-level | — | **89 MB** | Last decompressed 3D array |
| Specular output_data | Exporter.output_data | — | ~1 MB | Already extracted |
| OffSpecCorr + OffSpec building | Exporter.output_data | — | **320 MB** | 10 × 16 MB × 2 |
| corr_data (norm decompression) | Local variable | — | **89 MB** | Now del'd after corrector, but at peak both decompressions coexist |
| OffSpecular intermediates | Loop locals | — | ~3 MB | Per iteration, now del'd |
| Python + Qt + matplotlib baseline | Process | — | **500-800 MB** | Varies with session activity |
| NXSData.__new__ re-read via cache | NXSData(corr_ds.origin...) | — | — | Goes through _cache, may trigger decompression |

**Estimated total: 1.2-1.7 GB** for the data structures alone, on top of 500-800 MB baseline. With 4.1 GB available, this seems like it should fit.

**BUT**: The previous PLAN.md overestimated `raw_data` at "~2.5 GB" assuming no compression. With compression, compressed storage is much smaller. So why does it still crash?

### The Real Culprit: Transient Decompression Spikes

Each time `dataset.data` is accessed, `MRDataset.data` (qreduce.py:1181) decompresses the FULL 3D array:
```python
data = frombuffer(zlib.decompress(self._data_zipped), dtype=self._data_dtype).copy()
```

This creates:
1. `zlib.decompress()` output: a bytes object of ~89 MB
2. `frombuffer()`: a numpy array wrapping those bytes (no copy, same memory)
3. `.copy()`: a SECOND 89 MB array (required because frombuffer gives read-only)

**Peak during decompression: ~178 MB per access.** The old decompressed array (from `_cached_data`) is freed only after the new one takes its place.

In `extract_offspecular_corr()`, for EACH dataset × channel:
1. `OffSpecular(fdata[channel], **opts)` accesses `dataset.data` → 178 MB spike
2. Inside `_calc_offspec()`, `_calc_bg()` also accesses `dataset.data` → cache hit (no spike)
3. But the corrector's `corrector(S)` is fine (small arrays)

For 10 datasets × 1-4 channels = 10-40 decompressions. Each individual spike is ~178 MB, overlapping with the output data accumulating.

### The Missing Piece: What Else Uses Memory?

The GUI itself holds significant memory:
- `MainGUI.active_data` — an NXSData (shared with cache)
- Matplotlib figures for all visible plots (refl, offspec, GISANS, xy, xtof, x, y tabs) — each can hold rendered bitmaps
- `PlotDialog` instances if plotting results
- Qt widget tree, pixmaps, stylesheets

With all these, the baseline could be 800 MB-1.5 GB on a session that's been used for a while.

**Revised peak estimate: 1.5 GB baseline + 400 MB cache + 178 MB decompression + 320 MB output + misc = ~2.4-2.8 GB**, which on a system with 4.1 GB available SHOULD fit. Unless:

1. The user has more than 20 cached files (up to 100!)
2. Multiple large matplotlib canvases are open
3. Swap pressure causes thrashing leading to timing-dependent OOM

## Implementation Steps

Since we're uncertain about exact memory usage, we implement **all feasible memory reductions** to maximize headroom.

---

### Step 1: Clear `NXSData._cache` at start of reduction (~200-400+ MB freed)

**File:** `quicknxs/qio.py` — `Exporter.__init__()` and `release_raw_data()`

**Problem:** `NXSData._cache` accumulates every file loaded during the GUI session (up to 100 files × ~10-20 MB compressed each = up to 2 GB). During reduction, these cached objects serve no purpose — `read_data()` already has its own references in `self.raw_data`.

**Changes:**

1. In `release_raw_data()`, clear the class-level caches:
```python
def release_raw_data(self):
    '''Release raw data to free memory after all extractions are complete.'''
    self.raw_data.clear()
    NXSData._cache.clear()
    MRDataset._cached_data = None
    MRDataset._cached_object = None
    import gc; gc.collect()
```

2. Also clear caches at the START of reduction in `Exporter.__init__()`, AFTER `read_data()` has loaded everything needed. The loaded NXSData objects are held in `self.raw_data` which prevents them from being GC'd even after cache clear:
```python
def __init__(self, channels, refls, sample_length=10., spin_asymmetry=False):
    # ... existing setup ...
    self.read_data()
    # Clear cache to free memory from previously browsed files.
    # Our raw_data dict holds its own references, so our data survives.
    NXSData._cache.clear()
    MRDataset._cached_data = None
    MRDataset._cached_object = None
    import gc; gc.collect()
    # ... rest of init ...
```

**Memory savings:** Up to 2 GB depending on session history. Minimum ~100-200 MB for a typical session.

**Risk:** After the reduction completes, the GUI's `active_data` will still work (it holds its own reference). But clicking on a new file in the GUI won't benefit from the cache for previously loaded files — they'll be re-read from disk. This is an acceptable tradeoff since file reads are fast (~1s) and reduction is infrequent.

---

### Step 2: Clear `MRDataset._cached_data` after each extraction phase (~89 MB freed)

**File:** `quicknxs/qio.py`

**Problem:** `MRDataset._cached_data` holds ~89 MB of decompressed data from the last `dataset.data` access. This persists between extraction phases.

**Changes:** After each extraction method completes, clear the decompression cache:
```python
# At end of extract_reflectivity():
MRDataset._cached_data = None
MRDataset._cached_object = None

# At end of extract_offspecular():
MRDataset._cached_data = None
MRDataset._cached_object = None

# At end of extract_offspecular_corr() (before gc.collect):
MRDataset._cached_data = None
MRDataset._cached_object = None
```

**Memory savings:** 89 MB between extraction phases.

---

### Step 3: Reduce decompression transient memory (89 MB saved per access)

**File:** `quicknxs/qreduce.py` — `MRDataset.data` property (line 1180)

**Problem:** The current decompression code:
```python
data = frombuffer(zlib.decompress(self._data_zipped), dtype=self._data_dtype).copy()
```
creates TWO copies: the `zlib.decompress` bytes object (~89 MB) AND the `.copy()` result (~89 MB), for a transient peak of ~178 MB.

**Fix:** Use `np.frombuffer` directly and make the copy in one step, letting the intermediate bytes object be freed:
```python
@property
def data(self):
    if MRDataset._cached_object is self:
        return MRDataset._cached_data
    raw_bytes = zlib.decompress(self._data_zipped)
    data = np.frombuffer(raw_bytes, dtype=self._data_dtype).reshape(self._data_shape).copy()
    del raw_bytes  # explicitly free the intermediate bytes object
    MRDataset._cached_data = data
    MRDataset._cached_object = self
    return data
```

The `del raw_bytes` ensures the intermediate bytes object is freed before the function returns, reducing the transient peak from ~178 MB to ~89 MB.

**Memory savings:** ~89 MB transient reduction per `dataset.data` access.

---

### Step 4: Process datasets one at a time (lazy loading) (~50-150 MB freed)

**File:** `quicknxs/qio.py` — `read_data()` and extraction methods

**Problem:** `read_data()` loads ALL 10 datasets upfront into `self.raw_data`. With compression, this is ~100-200 MB. If we could load on-demand and release after use, only one dataset would be resident at a time (~10-20 MB + 89 MB decompressed).

**However**, multiple extraction methods (reflectivity, offspec, offspec_corr, gisans) iterate over the same datasets. Loading on-demand per extraction call would mean re-reading files from disk 2-4 times.

**Compromise approach:** Keep `read_data()` as is (loading all datasets is only ~100-200 MB compressed, which is acceptable). Instead, focus on releasing datasets from `raw_data` **after the last extraction that needs them**.

Since datasets are iterated in order and all extraction methods use the same loop structure, we could release each dataset after it's been processed by ALL extraction methods. But this requires restructuring the pipeline to process one dataset at a time across all methods — too invasive.

**Decision:** Skip this step. The compressed storage (~100-200 MB for 10 datasets) is reasonable. Focus on clearing the much larger `NXSData._cache` instead (Step 1).

---

### Step 5: Add tests

**File:** `tests/qio_test.py`

**New tests:**

1. **`test_cache_cleared_on_init`**: Create an Exporter, verify `NXSData._cache` is empty after init (cleared after read_data). Then verify `raw_data` is still populated (our data survived the cache clear).

2. **`test_cache_cleared_on_release`**: Create an Exporter, call `release_raw_data()`, verify both `NXSData._cache` and `MRDataset._cached_data` are cleared.

3. **`test_decompression_cache_cleared_after_extraction`**: After `extract_reflectivity()`, verify `MRDataset._cached_data is None`.

---

## Summary of Changes

| File | Changes | Memory Saved |
|---|---|---|
| `quicknxs/qio.py` | Clear `NXSData._cache` in `__init__` (after `read_data`) and `release_raw_data`; clear `MRDataset._cached_data/object` after each extraction method and in `release_raw_data` | **200-2000 MB** (cache) + **89 MB** (decompression cache) |
| `quicknxs/qreduce.py` | Add `del raw_bytes` in `MRDataset.data` property to reduce transient decompression peak | **89 MB transient** per access |
| `tests/qio_test.py` | Add 3 new tests | — |

## Expected Impact

These changes eliminate the two largest hidden memory consumers:
1. `NXSData._cache` — previously held ALL browsed files, now cleared before reduction
2. `MRDataset._cached_data` — previously held last decompressed array between phases, now explicitly cleared

Combined with the previous fixes (combined extraction, `del` intermediates, `del corr_data`), the peak memory during reduction should be:

| Component | Before All Fixes | After All Fixes |
|---|---|---|
| NXSData._cache (session files) | 200-2000 MB | **0 MB** (cleared) |
| raw_data (compressed) | 100-200 MB | 100-200 MB (unchanged) |
| MRDataset._cached_data | 89 MB persistent | 89 MB transient only |
| Decompression transient | 178 MB | **89 MB** |
| OffSpec + OffSpecCorr output | 320 MB | 320 MB (unchanged) |
| Python + Qt + matplotlib | 500-800 MB | 500-800 MB (unchanged) |
| **Total peak** | **~1.4-3.3 GB** | **~1.0-1.4 GB** |

On a system with 4.1 GB available, 1.0-1.4 GB data usage should provide comfortable headroom.

## Verification

```bash
cd /home/bvacaliuc/Projects/Claude/quicknxsv1
pixi run test  # All existing + new tests pass
```
