# Plan: Integrate REF_L Instrument Support into quicknxsv1

## Context

quicknxsv1 is a neutron reflectometry data reduction tool currently supporting only the
SNS Magnetism Reflectometer (REF_M, beamline 4A). The historical `refl_dev` branch
(origin/refl_dev) prototyped REF_L (Liquids Reflectometer, beamline 4B) support when the
code was Python 2 / Qt4. This plan integrates those concepts into the modern Python 3 /
Qt5 codebase on the `feature/integrate-refl_dev` branch, using the existing config system
and architecture.

**Goal:** A single quicknxsv1 that can reduce REF_L histogram data files, with all
existing output capabilities (ASCII, MATLAB, GenX, gnuplot, plots), while preserving
full REF_M functionality.

---

## Single Software vs. Two Separate Applications

### Pros of a single codebase (RECOMMENDED)

| Benefit | Detail |
|---------|--------|
| **~90% code reuse** | Core reduction (Reflectivity, OffSpecular, GISANS), export (qio), calculation (qcalc), GUI framework, database, plotting are instrument-agnostic |
| **Unified maintenance** | Bug fixes, Qt upgrades, dependency updates apply to both instruments simultaneously |
| **Existing abstraction** | The config system already has `ref_m.py` / `ref_l.py` with an alias mechanism (`config.instrument`) designed for this |
| **Same detector** | Both instruments use the same 304×256 pixel detector with identical physical dimensions (0.2128 × 0.1792 m) |
| **Shared export pipeline** | `qio.Exporter` uses `%(instrument.NAME)s` string interpolation — works for both instruments without code changes |
| **Lower deployment burden** | One package to install, one CI pipeline, one release process |

### Cons of a single codebase

| Concern | Mitigation |
|---------|------------|
| **Conditional logic in `_read_file` and `_collect_info`** | Limited to ~2 branch points (beamline detection + metadata extraction); well-isolated |
| **Risk of breaking REF_M while adding REF_L** | Full REF_M test suite runs on every change; add REF_L tests in parallel |
| **REF_L doesn't use polarization** | Polarization mapping code simply doesn't activate for REF_L (single `entry` channel) |
| **Different slit count (3 vs 4)** | `Reflectivity.slits` is already a list — just append slit4 when present |
| **Complexity in instrument-specific constants** | Move POLY_CORR_PARAMS, ANALYZER_IN, etc. to config modules |

### Verdict

**Single codebase is feasible and recommended.** The instruments share the same detector
hardware, the same NeXus file structure (with minor path differences), and the same physics.
The existing config proxy system was designed for exactly this use case. A separate application
would duplicate ~4000+ lines of core code for no architectural benefit.

---

## Key Instrument Differences (from data file analysis)

| Attribute | REF_M (4A) | REF_L (4B) |
|-----------|-----------|-----------|
| Beamline ID | `4A` | `4B` |
| Detector angle path | `instrument/bank1/DANGLE/value` | `instrument/bank1/TwoTheta/readback` |
| Sample angle path | `sample/SANGLE/value` | `instrument/bank1/Theta/readback` |
| DANGLE0/DIRPIX | Present (ancient format) | Not present |
| Wavelength path | `DASlogs/LambdaRequest/value` | `DASlogs/LambdaRequest/value` (same) |
| Sample-det distance | `instrument/bank1/SampleDetDis/value` (scalar, mm) | `instrument/bank1/distance` (2D array, meters) |
| Mod-det distance | `instrument/moderator/ModeratorSamDis/value` (mm) + sam_det | `instrument/moderator/distance` (meters, negative) |
| Slit widths | `instrument/aperture[1-3]/S[1-3]HWidth/value` or R-L | `DASlogs/S[1-4]HWidth/value` |
| Slit distances | `instrument/aperture[1-3]/distance` | `instrument/aperture[1-2]/distance` (only 1&2 present) |
| Number of slits | 3 | 4 (S1-S4, though S3/S4 may be invalid in some runs) |
| Polarization | Multi-entry (Off_Off, On_On, etc.) | Single `entry` (unpolarized) |
| Analyzer/Polarizer | `instrument/analyzer/*`, `instrument/polarizer/*` | Not present |
| Detector geometry | Same 304×256, 0.2128×0.1792 m | Same 304×256, 0.2128×0.1792 m |
| Event mode files | Available | Not available in IPTS-7053 (histogram only) |
| Data array paths | `bank1/data`, `data_x_y`, `data_x_time_of_flight` | Same, plus `data_y_time_of_flight` |

---

## Implementation Plan

### Phase 1: LRDataset Class and Instrument Detection

**Files to modify:** `quicknxs/qreduce.py`

#### 1a. Create `LRDataset` class

Introduce `LRDataset` as a subclass (or parallel class) of `MRDataset` with its own
`_collect_info()` method that reads REF_L-specific HDF5 paths:

```python
class LRDataset(MRDataset):
    """Representation of one measurement channel of the Liquids Reflectometer."""
    dpix = 151  # default direct beam pixel for REF_L (from refl_dev branch)

    def _collect_info(self, data):
        """Extract header information from REF_L HDF5 file."""
        # Shared logic: origin, logs, log_minmax, log_units (reuse parent's DASlogs loop)
        # REF_L specific:
        #   lambda_center from DASlogs/LambdaRequest/value (same path as REF_M)
        #   dangle from instrument/bank1/TwoTheta/readback
        #   dangle0 = 0.0 (always, REF_L has no DANGLE0)
        #   sangle from instrument/bank1/Theta/readback
        #   dist_sam_det from instrument/bank1/distance (mean of 2D array)
        #   dist_mod_det from -instrument/moderator/distance + dist_sam_det
        #   slit widths from DASlogs/S[1-4]HWidth/value
        #   slit distances from instrument/aperture[1-2]/distance (S3/S4 may not have distances)
        # ...
```

**Design decisions:**
- **Inherit from MRDataset** rather than creating a separate base class (as refl_dev did).
  The modern codebase's `MRDataset` has compression support, active area detection, and
  other features that didn't exist in the refl_dev era. Inheriting lets `LRDataset` reuse
  `from_histogram`, `from_event`, `bin_events`, `devide_bin`, all properties, and `__repr__`.
  Only `_collect_info` needs overriding.
- **Factory class methods** (`from_histogram`, `from_event`) are inherited unchanged — they
  call `cls()` and `_collect_info()` polymorphically.
- **Slit handling**: Store `slit4_width` and `slit4_dist` as additional attributes. The
  `Reflectivity` class constructs a `self.slits` list from the dataset, so it naturally
  accommodates a 4th slit.

#### 1b. Instrument detection in `NXSData._read_file()`

Add beamline detection after opening the HDF5 file:

```python
beamline = nxs[channels[0]]['instrument/beamline'][()][0]
if isinstance(beamline, bytes):
    beamline = beamline.decode('utf-8')
self._beamline = beamline
```

Then use the beamline to select the Dataset class:

```python
DatasetClass = LRDataset if beamline == '4B' else MRDataset
```

For REF_L files, skip the polarization/analyzer/mapping logic entirely (REF_L has no
polarizer or analyzer). Instead, treat all entries as unpolarized and use a simplified
channel mapping.

#### 1c. Handle missing fields gracefully

REF_L files lack `instrument/analyzer/*`, `instrument/polarizer/*`, and
`sample/SANGLE/value`. Wrap these lookups in try/except blocks (several already are) and
provide sensible defaults when missing.

**Estimated changes:** ~120 lines new code in qreduce.py

---

### Phase 2: Complete REF_L Configuration

**Files to modify:** `quicknxs/config/ref_l.py`

Expand the stub with:

```python
config_file = ''

NAME = 'REF_L'
BEAMLINE = '4B'

data_base = u'/SNS/REF_L'
BASE_SEARCH = u'*/data/REF_L_%s_'
OLD_BASE_SEARCH = u'*/*/%s/NeXus/REF_L_%s*'
LIVE_DATA = u'/SNS/REF_L/shared/LiveData/meta_data.xml'
EXTENSION_SCRIPTS = u'/SNS/REF_L/shared/quicknxs_scripts'

# Auto-reduction paths
AUTOREFL_LIVE_IMAGE = u'/SNS/REF_L/shared/LiveData/autorefl.png'
AUTOREFL_LIVE_INDEX = u'/SNS/REF_L/shared/LiveData/autorefl_index.txt'
AUTOREFL_RESULT_IMAGE = u'%(origin_path)s/../shared/autoreduce/reflectivity_%(numbers)s.png'
autorefl_folder = u'/SNS/REF_L/shared/autoreduce/'

# Background defaults (initial values, can be tuned)
START_BG = (4, 104)

# Detector region (from the geometry file found in IPTS-7053 data)
DETECTOR_REGION = {
    b'REF_L_geom_2011_08_24.xml': ((8, 295), (8, 246)),
}

# Database fields (REF_L motors from DASlogs inspection)
DATABASE_ADDITIONAL_FIELDS = [
    ('S1W', 'S1HWidth', float),
    ('S2W', 'S2HWidth', float),
    ('S3W', 'S3HWidth', float),
    ('S4W', 'S4HWidth', float),
    ('S1H', 'S1VHeight', float),
    ('S2H', 'S2VHeight', float),
]

DATABASE_DIRECT_BEAM_COMPARE = [
    ('s1h', 'S1VHeight', float, 1.0),
    ('s2h', 'S2VHeight', float, 1.0),
]

database_file = u'/SNS/REF_L/shared/quicknxs_database'
```

**Estimated changes:** ~35 lines replacing the 17-line stub

---

### Phase 3: Move Instrument-Specific Constants to Config

**Files to modify:** `quicknxs/qreduce.py`, `quicknxs/config/ref_m.py`, `quicknxs/config/ref_l.py`

Currently hardcoded in qreduce.py module scope:

| Constant | Current value | Action |
|----------|---------------|--------|
| `POLY_CORR_PARAMS` | REF_M calibration coefficients | Move to `ref_m.py`; REF_L gets its own or `None` |
| `ANALYZER_IN`, `NEW_ANALYZER_IN` | REF_M analyzer positions | Move to `ref_m.py`; not applicable to REF_L |
| `POLARIZER_IN`, `SUPERMIRROR_IN` | REF_M polarizer positions | Move to `ref_m.py`; not applicable to REF_L |
| `MAPPING_*` | Polarization state mappings | Keep in qreduce.py (only used for REF_M path) |

In `_correct_sensitivity()`, read `POLY_CORR_PARAMS` from config:

```python
from .config import instrument
# ...
poly_params = getattr(instrument, 'POLY_CORR_PARAMS', None)
```

This allows REF_L to either have its own calibration or skip polynomial sensitivity
correction entirely.

**Estimated changes:** ~20 lines moved/refactored

---

### Phase 4: Entry Point & Instrument Selection

**Files to modify:** `scripts/quicknxs`

Add a command-line argument to select the instrument:

```python
parser.add_argument('--instrument', choices=['ref_m', 'ref_l'], default='ref_m',
                    help='Instrument to configure for (default: ref_m)')
# ...
config.instrument = config.proxy.add_alias(args.instrument, 'instrument')
```

This is minimally invasive — the config proxy alias mechanism already supports this.
Users launch with `quicknxs --instrument ref_l` to work with REF_L data.

**Alternative considered:** Auto-detect from loaded file's beamline field. This is
more complex and has UX issues (what instrument does the GUI configure before any file
is loaded?). A command-line flag is simpler and more explicit.

**Estimated changes:** ~5 lines

---

### Phase 5: Reflectivity Class Updates

**Files to modify:** `quicknxs/qreduce.py`

The `Reflectivity.__init__` currently constructs `self.slits` from the dataset:

```python
self.slits = [(dataset.slit1_width, dataset.slit1_dist),
              (dataset.slit2_width, dataset.slit2_dist),
              (dataset.slit3_width, dataset.slit3_dist)]
```

Update to dynamically include slit4 if present:

```python
self.slits = [(dataset.slit1_width, dataset.slit1_dist),
              (dataset.slit2_width, dataset.slit2_dist),
              (dataset.slit3_width, dataset.slit3_dist)]
if hasattr(dataset, 'slit4_width'):
    self.slits.append((dataset.slit4_width, dataset.slit4_dist))
```

The `get_resolution()` method uses `self.slits` as a list, so it naturally handles
variable-length slit lists.

**Estimated changes:** ~5 lines

---

### Phase 6: Tests

**Files to create/modify:**
- `tests/qreduce_test.py` — add REF_L tests
- `tests/test_refl_data.nxs` — copy a small REF_L histo file for test data

#### Test cases:

1. **`test_lr_nxsdata_load_histogram`** — Load a REF_L histogram file, verify it returns
   an NXSData with one LRDataset channel
2. **`test_lr_dataset_metadata`** — Verify LRDataset extracts correct metadata:
   - `dangle` from TwoTheta/readback
   - `sangle` from Theta/readback
   - `dangle0 == 0.0`
   - `lambda_center` from LambdaRequest
   - `dist_sam_det` and `dist_mod_det` computed correctly
   - Slit widths from DASlogs
3. **`test_lr_reflectivity_extraction`** — Create a Reflectivity from an LRDataset,
   verify Q, I, dI arrays are populated and have correct shape
4. **`test_lr_locate_file`** — Verify `locate_file()` finds REF_L files when instrument
   config is set to ref_l
5. **`test_mr_unchanged`** — Verify existing REF_M tests still pass (regression)
6. **`test_instrument_detection`** — Load both REF_M and REF_L files, verify correct
   Dataset class is instantiated

#### Test data strategy:

Copy `/SNS/REF_L/IPTS-7053/0/80836/NeXus/REF_L_80836_histo.nxs` to `tests/` as
`test_refl_histo.nxs` (or similar). The file is ~2.5 MB, reasonable for a test fixture.

**Estimated changes:** ~150 lines of new test code

---

### Phase 7: GUI Compatibility Verification

**Files to review (may need minor changes):**
- `quicknxs/main_gui.py` — `loadFile()` calls `NXSData()` which now auto-detects;
  verify the GUI handles `LRDataset` objects (same interface as `MRDataset`)
- `quicknxs/gui_utils.py` — `Reducer` class drives export; uses `Reflectivity` which
  is instrument-agnostic
- `quicknxs/auto_reflectivity.py` — reads `instrument.LIVE_DATA`; will work once
  `ref_l.py` config is complete

**Expected outcome:** Minimal or no GUI changes needed because `LRDataset` inherits the
same interface as `MRDataset`. The GUI interacts through properties (`xdata`, `ydata`,
`tof`, `lamda`, etc.) that are defined on the base class.

---

### Phase 8: Deferred Items (Not in initial implementation)

These items from the refl_dev branch are intentionally deferred:

| Feature | Reason |
|---------|--------|
| **AsyncCache / Prefetcher** | Performance optimization; not needed for correctness. Can be added later. |
| **Separate REF_L UI layout** (`main_window_ltest.ui`) | The existing UI should work for both instruments. A specialized UI can be designed later if needed. |
| **Event mode for REF_L** | No event files available in IPTS-7053. When available, `from_event` is inherited from MRDataset and should work (the event format is detector-agnostic). |
| **ReflectivityDataset base class** | The refl_dev approach of extracting a base class is architecturally cleaner but requires moving ~200 lines of existing code. For now, `LRDataset(MRDataset)` is simpler and lower-risk. Can refactor later. |

---

## Execution Order

```
Phase 1  ──► Phase 2  ──► Phase 3  ──► Phase 4
(LRDataset)  (Config)     (Constants)  (Entry point)
                                           │
Phase 5  ◄──────────────────────────────────┘
(Reflectivity)
    │
Phase 6  ──► Phase 7
(Tests)      (GUI verify)
```

## Verification

1. **Run existing REF_M tests:** `make test-core` — must all pass (regression)
2. **Run new REF_L tests:** `pytest tests/qreduce_test.py -k lr` — all new tests pass
3. **Manual verification with data:**
   ```python
   from quicknxs import config
   config.instrument = config.proxy.add_alias('ref_l', 'instrument')
   from quicknxs.qreduce import NXSData, Reflectivity
   d = NXSData('/SNS/REF_L/IPTS-7053/0/80836/NeXus/REF_L_80836_histo.nxs')
   print(type(d[0]))  # should be LRDataset
   r = Reflectivity(d[0])
   print(r.Q.shape, r.I.shape)  # should have data
   ```
4. **GUI launch:** `quicknxs --instrument ref_l` — opens without errors, can browse `/SNS/REF_L/`
5. **Full pipeline:** `make lint` passes
6. **Compare output:** Extract reflectivity for run 80830, compare Q/R/dR values against
   `/SNS/REF_L/IPTS-7053/shared/autoreduce/reflectivity_70830.txt` reference

## Critical Files

| File | Role |
|------|------|
| `quicknxs/qreduce.py` | Core: add LRDataset, instrument detection |
| `quicknxs/config/ref_l.py` | Config: complete REF_L constants |
| `quicknxs/config/ref_m.py` | Config: receive moved constants |
| `scripts/quicknxs` | Entry: add --instrument flag |
| `tests/qreduce_test.py` | Tests: REF_L test cases |
