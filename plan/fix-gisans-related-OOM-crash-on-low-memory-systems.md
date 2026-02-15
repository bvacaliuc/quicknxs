# Plan: Fix GISANS-Related OOM Crash on Low Memory Systems

## Context

After previous fixes (combined OffSpec extraction, cache clearing, raw_data release), the OOM crash persists when ALL export options are enabled — specifically when `exportGISANS=True`. The strace analysis shows:

- **37 concurrent 134 MB mmap allocations** (total ~5 GB) without intervening frees
- The Python process (PID 1182634) was killed by SIGKILL at 23:42:50
- The last debug log entries were about GISANS `_calc_gisans` and normalization

## Root Cause: GISANS Objects Hold Massive Redundant 3D Arrays

Each `GISANS` object in `_calc_gisans()` stores **6 copies** of the 3D sub-volume plus 5 Q-space arrays:

| Attribute | Type | Size per object |
|---|---|---|
| `self.Iraw = Idata` | View of decompressed data (keeps parent alive) | ~89 MB (via parent) |
| `self.dIraw = sqrt(self.Iraw)` | Copy | ~20 MB |
| `self.I = self.Iraw * scale` | Copy | ~20 MB |
| `self.dI = self.dIraw * scale` | Copy | ~20 MB |
| `self.S = array(self.I)` | Explicit copy | ~20 MB |
| `self.dS = array(self.dI)` | Explicit copy | ~20 MB |
| `self.Qx, self.Qy, self.Qz, self.pi, self.pf` | 5 Q-space arrays | ~100 MB |

**Total per GISANS object: ~134 MB** (matches strace observation)

With 7 datasets × 2 channels = **14 GISANS objects = ~1.9 GB** — all alive simultaneously in `output_data`.

Additionally, `extract_gisans()` (gui_utils.py:167) creates ALL objects **before** showing the GISANSDialog. If the user cancels the dialog, ~1.9 GB was allocated for nothing.

After the dialog, if `lambdaNoDirectPulse` is unchecked, ALL objects are re-created (another ~1.9 GB), and the old ones are only freed when `output_data` dict is reassigned. Peak: ~3.8 GB just for GISANS.

## Implementation Steps

### Step 1: Eliminate redundant arrays in GISANS._calc_gisans() (~60% reduction per object)

**File:** `quicknxs/qreduce.py` — `_calc_gisans()` at line 2037

**Problem:** `self.Iraw`, `self.I`, `self.S` are three separate copies of essentially the same data (differing only by a scale factor). Same for `dIraw`, `dI`, `dS`. After normalization, only `self.S` and `self.dS` are used by `GISANSCalculation.calc_single()`.

**Changes:**
1. Make `self.Iraw` a copy (not a view) so it doesn't keep the decompressed parent array alive
2. Delete `self.I`, `self.dI` after computing `self.S`, `self.dS` — they are never accessed after `_calc_gisans` completes
3. Delete `self.Iraw`, `self.dIraw` after computing `self.S`, `self.dS` — same reason
4. In the `gisans_no_DP` filtering block (line 2109), only filter the arrays that still exist (`self.S`, `self.dS`, `self.Qx`, `self.Qy`, `self.Qz`, `self.pi`, `self.pf`)

**Key insight:** `GISANSCalculation.calc_single()` (gui_utils.py:846) only accesses `data.S`, `data.dS`, `data.Qy`, `data.Qz`, `data.pf`, `data.lamda`, and `data.options`. It never accesses `I`, `dI`, `Iraw`, or `dIraw`. The `__repr__` method accesses `self.Qz.shape`. The `SGrid`, `QyGrid`, `QzGrid` are computed at the end of `_calc_gisans` and use `self.S`, `self.Qy`, `self.Qz`. So we can safely delete `Iraw`, `dIraw`, `I`, `dI` at the end of `_calc_gisans`.

**Result:** Each GISANS object drops from ~134 MB to ~60 MB (S, dS + 5 Q-space arrays). 14 objects = ~840 MB instead of ~1.9 GB.

### Step 2: Process GISANS datasets one channel at a time, release after GISANSCalculation

**File:** `quicknxs/gui_utils.py` — `extract_gisans()` at line 167

**Problem:** All 14 GISANS objects are created and stored simultaneously. Additionally, after the dialog, they may all be re-created.

**Changes:**
1. For the preview (before dialog), only create GISANS objects for the **first dataset** (first channel only) — that's all the `GISANSDialog` needs. This reduces preview memory from ~1.9 GB to ~60 MB.
2. After dialog acceptance, create GISANS objects for all datasets but process them through `GISANSCalculation` **one channel at a time**, deleting the GISANS objects after each channel's calculation completes.
3. After `GISANSCalculation` finishes for a channel, the results are reduced to small 2D histograms. Delete the input GISANS objects immediately.

**Result:** Peak GISANS memory = 7 objects × ~60 MB = ~420 MB (one channel at a time) instead of 14 × 134 MB = ~1.9 GB.

### Step 3: Clear decompression cache between GISANS object creation

**File:** `quicknxs/gui_utils.py` — within revised `extract_gisans()`

**Problem:** Each `GISANS.__init__()` calls `dataset.data` which triggers `MRDataset.data` decompression, storing ~89 MB in `MRDataset._cached_data`. This is never cleared between GISANS objects.

**Changes:** After creating each batch of GISANS objects per channel, clear `MRDataset._cached_data`.

### Step 4: Fix headless script for GISANS

**File:** `scripts/reduce_headless.py`

**Problem:** `extract_gisans()` calls `GISANSDialog(...).exec_()` which requires user interaction. In headless mode this will fail.

**Changes:** Set `exportGISANS=False` in the headless script since GISANS requires interactive lambda range selection.

### Step 5: Add tests

**File:** `tests/qio_test.py`

1. **`test_gisans_no_redundant_arrays`**: Create a GISANS object, verify that `Iraw`, `dIraw`, `I`, `dI` attributes do not exist (deleted after computation), while `S`, `dS`, `Qy`, `Qz` do exist.

## Files to Modify

| File | Changes |
|---|---|
| `quicknxs/qreduce.py` | Delete redundant arrays at end of `_calc_gisans()`, make `Idata` a copy |
| `quicknxs/gui_utils.py` | Restructure `extract_gisans()` to process one channel at a time, clear caches |
| `scripts/reduce_headless.py` | Set `exportGISANS=False` (requires GUI dialog) |
| `tests/qio_test.py` | Add GISANS memory test |

## Expected Memory Impact

| Scenario | Before | After |
|---|---|---|
| GISANS peak (14 objects) | ~1.9 GB | ~420 MB (7 objects/channel × 60 MB) |
| Total pipeline peak | ~3–5 GB | ~1–1.5 GB |
| System with 4 GB available | OOM kill | Should complete |

## Verification

```bash
make test          # All tests pass
make strace-reduce # No OOM kill, process completes
```
