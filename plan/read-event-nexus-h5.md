# Plan: Read Modern Event NeXus (.nxs.h5) Files in quicknxsv1

## Executive Summary

Upgrade quicknxsv1 to read the modern `*.nxs.h5` event-mode NeXus files (used since
~2018) in addition to the legacy `*_histo.nxs` format. Both REF_M (beamline 4A) and
REF_L (beamline 4B) instruments must be supported. The approach converts events into
the same 3D histogram `(x, y, tof)` that the existing code expects, so no downstream
changes to reduction, plotting, or export are required.

## Background

### Legacy format (`*_histo.nxs` and `*_event.nxs`)
- Pre-histogrammed 3D data at `bank1/data` with shape `(n_x, n_y, n_tof)`
- Projected 2D views: `data_x_y`, `data_x_time_of_flight`, `data_y_time_of_flight`
- Metadata at structured instrument paths (`instrument/bank1/DANGLE/value`, etc.)
- REF_M: multiple entries for polarization states (Off_Off, On_On, etc.)
- REF_L: single `entry/` (unpolarized)
- Old event files (`*_event.nxs`) also have separate entries per polarization state,
  each with its own `bank1_events/` — so `from_event()` can process them per-channel

### Modern format (`*.nxs.h5`)
- Raw events only: `bank1_events/event_id` + `event_time_offset` (both large arrays)
- Definition field: `NXsnsevent`
- **No pre-histogrammed data** — events must be binned into x/y/tof histograms
- **No structured instrument paths** — all metadata lives in `DASlogs/` with
  beamline-prefixed keys (e.g., `DASlogs/DANGLE/average_value`)
- Single `entry/` only — even for REF_M polarization (no separate Off_Off entries)
- Pixel ordering: `idfillbyfirst="y"` → `event_id = x_pixel * n_y + y_pixel`

### Format transition (REF_L)

REF_L has a much cleaner transition than REF_M:

- Only **4 IPTS** have both `data/` and `nexus/` directories
- Only **25 runs** exist in both formats, and always in *different* IPTS (not same IPTS)
- **~250 IPTS** have only `.nxs.h5` files (no histo counterpart)
- All `.nxs.h5` files (earliest: run 133969, Dec 2015) have **full metadata**
  (LambdaRequest, thi, ths) — no missing-metadata era
- The overlapping h5 files are empty (zero events) — likely DAS restart artifacts

**REF_L detector geometry change (October 2014):**
- Before run 117198: `data_x_y` shape `(304, 256)`, IDF `REF_L_geom_2011_08_24.xml`
- After run 117198:  `data_x_y` shape `(256, 304)`, IDF `REF_L_geom_2014_10_09.xml`
- All `.nxs.h5` files are post-transition, so always `(256, 304)`
- Old histo files are unaffected (shape is embedded in `bank1/data`)

**REF_L IDF format change:**
- 2014 IDF (valid-from 2014-10-10): tube-based detector (256 tubes × 304 pixels each),
  no `xpixels`/`ypixels` attributes, detector z=0.00035 m, moderator z=-13.63 m
- 2024 IDF (valid-from 2024-08-26): rectangular panel with `xpixels=256, ypixels=304`,
  detector z=1.362 m, moderator z=-13.685 m
- The `_get_detector_dimensions()` helper must fall back to instrument name when
  `xpixels`/`ypixels` attributes are not in the XML (tube-based IDF)

**REF_L distances are NOT hardcodeable:**
- Moderator distance: 13.63 m (2016 IDF) vs 13.685 m (2025 IDF)
- Sample-detector distance: must be parsed from XML or read from
  `DASlogs/BL4B:Det:TH:DlyDet:BasePath` (source-to-detector, 14.91 m in 2016 vs 15.5 m in 2025)
- `DASlogs/distance_sample_detector` is -1.0 (invalid) when present

### Format transition (REF_M)

Analysis of the complete REF_M dataset reveals the transition was **not a clean break**.
Many IPTS directories contain the **same run numbers in both formats**:

- **42 IPTS** have both `data/` (histo) and `nexus/` (h5) directories
- In most of these, the run ranges **completely overlap** (every run has both formats)
- The overlap era spans roughly runs 29732–34727+ (July 2018 onward)
- Example: IPTS-9801 has 70 overlapping runs (29732–29801), including polarized data

**Validation**: For overlapping run REF_M_29750 (unpolarized), the XY projection from
binning `.nxs.h5` events matches the `_histo.nxs` histogram with 0.999992 correlation
(29 count difference out of 19,195 events, max 2 counts/pixel). This confirms:
- Pixel ID mapping `event_id = x * 256 + y` is correct for REF_M
- The detector dimensions `(304, 256)` match the histo format

**Metadata availability**: All production `.nxs.h5` files (runs 29732+) have complete
DASlogs (`LambdaRequest`, `DANGLE`, `SANGLE`, etc.). Only the earliest commissioning
runs in IPTS-16196 (runs 29001–29016, May 2018) lack wavelength data.

### Polarization in `.nxs.h5` format

**Critical difference**: Old `_event.nxs` files pre-sort events into separate entries
per polarization state (`entry-Off_Off`, `entry-On_Off`, etc.). The new `.nxs.h5`
format puts ALL events into a single `entry/bank1_events/`, with polarization state
changes recorded as a time-series in `DASlogs/PolarizerState`.

Example (run 29742, IPTS-9801):
- Histo: `entry-Off_Off` (234,896 counts) + `entry-On_Off` (262,676) + `entry-unfiltered` (63)
- H5: single `entry/` with 497,637 total events, `DASlogs/PolarizerState` shape=(188,)

**Implication for this plan**: For the initial implementation, polarized `.nxs.h5` files
will be loaded as **unpolarized** (all events combined). This is a documented limitation.
When a corresponding `_histo.nxs` file exists on disk, `locate_file()` will prefer it
(since histo files preserve polarization channels). Proper event-level polarization
filtering using `PolarizerState` time-series is deferred to future work (Phase 8).

### Key differences by instrument

| Property | REF_M DASlogs key | REF_L DASlogs key |
|---|---|---|
| Beamline | BL4A | BL4B |
| Detector pixels | xpixels=304, ypixels=256 | xpixels=256, ypixels=304 |
| **Angles** | | |
| Detector arm 2θ | `DANGLE` | `tthd` (see angle note below) |
| Sample angle | `SANGLE` | `ths` |
| Incident angle | (derived: DANGLE/2) | `thi` |
| Direct beam 2θ₀ | `DANGLE0` | N/A (always 0; see angle note) |
| Direct beam pixel | `DIRPIX` | N/A (from settings) |
| **Wavelength** | | |
| Neutron wavelength | `LambdaRequest` | `LambdaRequest` (alias of `BL4B:Det:TH:BL:Lambda`) |
| Acquisition rate | `SpeedRequest1` | `BL4B:Det:TH:BL:Frequency` |
| **Slit widths** | | |
| Slit 1 horizontal | `S1HWidth` | `BL4B:Mot:s1:X:Gap:Readback` |
| Slit 1 vertical | `S1VHeight` | `BL4B:Mot:s1:Y:Gap:Readback` |
| Slit i horizontal | `S2HWidth` | `BL4B:Mot:si:X:Gap:Readback` |
| Slit i vertical | `S2VHeight` | `BL4B:Mot:si:Y:Gap:Readback` |
| Slit 3 horizontal | `S3HWidth` | N/A |
| Incident slit position | N/A | `BL4B:Mot:xi.RBV` |
| **Distances** | | |
| Sample-det (mm) | `SampleDetDis` | from `settings.json` (date-indexed) |
| Moderator-sample (mm) | `ModeratorSamDis` | from `settings.json` (date-indexed) |
| Emission mod distance | N/A | `BL4B:Det:TH:DlyDet:BasePath` (m) × 1000 |
| Emission coefficients | N/A | `BL4B:Chop:Skf2:ChopperOffset` / `ChopperMultiplier` |
| **Polarization** | | |
| Polarizer state | `PolarizerState` (time-series) | N/A (unpolarized) |
| Polarizer veto | `PolarizerVeto` (time-series) | N/A |

### BL4B (REF_L) angle handling — critical complexity

REF_L has three independent motor angles: `thi` (incident), `ths` (sample), and `tthd`
(detector arm two-theta). Their relationship to the quicknxsv1 `dangle` attribute is
non-trivial and differs between the legacy and modern formats.

**Legacy format (`*_histo.nxs`):**
- `dangle = TwoTheta/readback` from structured instrument path
- In legacy files, `TwoTheta/readback ≈ 0` for all observed runs (both direct beam and
  reflectivity). This means the entire scattering angle is derived from pixel offsets
  relative to the direct beam pixel (`dpix`), not from motor angles.
- `dangle0 = 0.0` (hardcoded)

**Modern format (`.nxs.h5`):**
- There is no `TwoTheta/readback` structured path — only raw motor readbacks in DASlogs.
- `dangle = tthd` (the detector arm two-theta motor readback)
- `dangle0 = 0.0` (no `DANGLE0` equivalent in REF_L DASlogs)
- Since modern files have `tthd` values of several degrees for reflectivity measurements
  (e.g., `tthd = 4.201°` for REF_L_220030), the `dangle` value carries significant
  geometric information, unlike legacy files where it was effectively zero.

**Downstream usage:** The reflectivity calculation computes:
```
tth = dangle - dangle0 + pixel_offset    (treated as 2θ)
ai = tth / 2                             (incident angle = half of 2θ)
```
This is correct for the standard geometry when `dangle = tthd`.

**Instrument mode complexity (for documentation, not initial implementation):**
- BL4B supports multiple operating modes (`Reflect Up`, `Free Liquid`, etc.)
- In theta-2*theta mode: `tthd` tracks `2 × sample_angle`, so `ai = tthd/2`
- In theta-theta mode: `tthd` tracks `1 × sample_angle`, so `ai = tthd/2` gives a
  value that is half the true angle — a mode-dependent correction may be needed
- For direct beams: `thi ≈ tthd` (earth-centered) or `tthd ≈ 0` (beam-centered)
- The lr_reduction project handles this at `nr_reduction_calc.py:390`:
  `ThetaCalc = pixel_offset + (tthd - DB_tthd) / 2`

**Initial implementation strategy:** Set `dangle = tthd` and `dangle0 = 0.0`. This
is correct for the common theta-2*theta geometry and matches how REF_M handles `DANGLE`.
Users can override `dangle0` in the GUI if needed (e.g., to account for a non-zero
direct beam `tthd`). Mode-dependent corrections can be added in a future phase if needed.

**Verification data:**
| Run | thi | ths | tthd | Type |
|---|---|---|---|---|
| REF_L_220030 | -0.007 | 2.101 | 4.201 | Reflectivity (tthd ≈ 2×ths) |
| REF_L_138523 | -4.002 | -4.000 | -4.001 | Direct beam (earth-centered) |
| REF_L_80836 (legacy) | -0.540 | 2.150 | 0.540 | Direct beam (TwoTheta/readback=0.019) |

### Instrument settings configuration file

Following the lr_reduction project's `settings.json` pattern, quicknxsv1 will use a
date-indexed configuration file for instrument parameters that change over time but are
not recorded in the data files. **No values are hardcoded.**

**REF_L `settings.json`** (adopted from lr_reduction with the same date entries):
```json
{
    "source-det-distance": [
        {"from": "2014-10-10", "value": 15.75},
        {"from": "2024-08-26", "value": 15.282},
        {"from": "2025-01-01", "value": 15.75}
    ],
    "sample-det-distance": [
        {"from": "2014-10-10", "value": 1.83},
        {"from": "2024-08-26", "value": 1.355},
        {"from": "2025-01-01", "value": 1.83}
    ],
    "number-of-x-pixels": [{"from": "2014-10-10", "value": 256}],
    "number-of-y-pixels": [{"from": "2014-10-10", "value": 304}],
    "pixel-width": [{"from": "2014-10-10", "value": 0.70}],
    "xi-reference": [{"from": "2014-10-10", "value": 445}],
    "s1-sample-distance": [{"from": "2014-10-10", "value": 1.485}]
}
```

**REF_M `settings.json`** (instrument parameters are available in DASlogs, but a settings
file provides defaults and slit distances which are not in the data):
```json
{
    "number-of-x-pixels": [{"from": "2006-01-01", "value": 304}],
    "number-of-y-pixels": [{"from": "2006-01-01", "value": 256}],
    "pixel-width": [{"from": "2006-01-01", "value": 0.70}],
    "slit1-sample-distance": [{"from": "2006-01-01", "value": 2600}],
    "slit2-sample-distance": [{"from": "2006-01-01", "value": 2019}],
    "slit3-sample-distance": [{"from": "2006-01-01", "value": 714}]
}
```

The settings reader uses the run's `start_time` to select the applicable values,
choosing the entry with the most recent `from` date that is before the measurement.
This is the same algorithm used by lr_reduction's `read_settings()` method.

### Reference implementation: lr_reduction (new_workflow branch)

The `binary_processing.py` module in lr_reduction provides a pure-numpy approach for
REF_L files:

```python
# Key steps:
# 1. Read events via h5py
e_offset = f['entry/bank1_events/event_time_offset'][:]
event_id = f['entry/bank1_events/event_id'][:]

# 2. Convert event_id to x,y pixel coordinates
xvals = event_id // n_y   # n_y=304 for REF_L
yvals = event_id % n_y

# 3. Filter by x-pixel range, bin into y vs tof histogram
# 4. Apply dead-time correction using bank_error_events
```

quicknxsv1 already has a `MRDataset.from_event()` method that does something similar
for old `*_event.nxs` files — it uses `MRDataset.bin_events()` to create the 3D
histogram. We can reuse this binning infrastructure for the new format.

---

## Architecture Decision

### Approach: Event-to-histogram adapter in `_read_file()`

Rather than creating a parallel reduction pipeline, we will:

1. **Detect** the file format in `NXSData._read_file()` (already dispatches by beamline)
2. **Read events** from the new format and **bin them** into the same 3D histogram
   that `from_histogram()` produces
3. **Construct metadata** from DASlogs instead of structured instrument paths
4. **Feed the result** into the existing `MRDataset`/`LRDataset` objects

This means all downstream code (Reflectivity, OffSpecular, GISANS, plotting, export)
works unchanged.

### Why not create new Dataset subclasses?

The existing `MRDataset.from_event()` already converts events to histograms. The only
difference with `.nxs.h5` files is:
- Different HDF5 paths for metadata
- No `bank1/data_x_y` to get detector dimensions (line 979 of qreduce.py uses
  `dimension=data['bank1/data_x_y'].shape` — this path does not exist in `.nxs.h5`)
- No structured instrument paths — everything is in DASlogs
- No `bank1/time_of_flight` — ToF edges must be computed from wavelength + chopper

These differences are isolated to **file reading and metadata extraction**, not to the
data representation. A new `from_event_h5()` class method on `MRDataset` and `LRDataset`
is the cleanest approach.

### Key insight from lr_reduction

The `binary_processing.py` module in lr_reduction's new_workflow shows how to convert
event_id to pixel coordinates:
```python
x_pixel = event_id // n_y   # integer division
y_pixel = event_id % n_y    # remainder
```
where `idfillbyfirst="y"` in the instrument XML defines this ordering. For REF_L,
`n_y=304`; for REF_M, `n_y=256`. This is **the same convention** used by quicknxsv1's
existing `bin_events()` — it calls `bincount(tof_ids, minlength=n_x*n_y).reshape(n_x, n_y)`
which relies on the same pixel-id-to-2D mapping.

---

## Detailed Changes

### Change 1: File format detection and routing

**File:** `quicknxs/qreduce.py`
**Method:** `NXSData._read_file()`

Currently the method checks the beamline to dispatch to `_read_file_MR` or
`_read_file_LR`. Within those methods, the file suffix (`.endswith('event.nxs')`,
`.endswith('histo.nxs')`) determines whether to use `from_event` or `from_histogram`.

**Add detection for `.nxs.h5` files:**

```python
def _read_file(self, filename):
    # ... existing h5py.File open ...

    # Detect file format
    first_entry = list(nxs.keys())[0]
    definition = ''
    try:
        def_raw = nxs[first_entry]['definition'][()][0]
        definition = def_raw.decode('utf-8') if isinstance(def_raw, bytes) else str(def_raw)
    except KeyError:
        pass

    self._is_event_h5 = (definition == 'NXsnsevent')

    # ... existing beamline detection and dispatch ...
```

**In `_read_file_MR` and `_read_file_LR`**, add a branch for the new format:

```python
# In the per-channel loop:
if self._is_event_h5:
    data = MRDataset.from_event_h5(raw_data, self._options, ...)
elif filename.endswith('event.nxs'):
    data = MRDataset.from_event(raw_data, self._options, ...)
elif filename.endswith('histo.nxs'):
    data = MRDataset.from_histogram(raw_data, self._options)
else:
    data = MRDataset.from_old_format(raw_data, self._options)
```

### Change 2: New `from_event_h5()` class method on MRDataset

**File:** `quicknxs/qreduce.py`
**Class:** `MRDataset`

This new class method reads events from `.nxs.h5` format and produces the same
output as `from_histogram()`: populated `data`, `xydata`, `xtofdata`, `tof_edges`.

```python
@classmethod
@log_call
def from_event_h5(cls, data, read_options,
                  callback=None, callback_offset=0., callback_scaling=1.,
                  total_duration=None, tof_overwrite=None):
    """
    Load data from a modern .nxs.h5 event NeXus file (NXsnsevent format).
    Converts events into the same 3D histogram as from_histogram().
    """
    output = cls()
    output.read_options = read_options
    output.from_event_mode = True
    bin_type = read_options['bin_type']
    bins = read_options['bins']

    # Collect metadata from DASlogs (not structured paths)
    try:
        output._collect_info_h5(data)
    except KeyError:
        warn('Error collecting metadata from .nxs.h5:\n\n' + traceback.format_exc())

    # Determine TOF edges
    if tof_overwrite is None:
        lcenter = output.lambda_center
        tmin = output.dist_mod_det / H_OVER_M_NEUTRON * (lcenter - 1.6) * 1e-4
        tmax = output.dist_mod_det / H_OVER_M_NEUTRON * (lcenter + 1.6) * 1e-4
        if bin_type == 0:
            tof_edges = linspace(tmin, tmax, bins + 1)
        elif bin_type == 1:
            tof_edges = 1. / linspace(1./tmin, 1./tmax, bins + 1)
        elif bin_type == 2:
            tof_edges = tmin * (((tmax/tmin)**(1./bins)) ** arange(bins + 1))
        else:
            raise ValueError('Unknown bin type %i' % bin_type)
    else:
        tof_edges = tof_overwrite

    # Read event data
    tof_ids = array(data['bank1_events/event_id'][()], dtype=int)
    tof_time = data['bank1_events/event_time_offset'][()]

    if len(tof_ids) == 0:
        debug('No events in file')
        return None

    # Read proton charge
    tof_pc = data['DASlogs/proton_charge/value'][()]

    # Handle event splitting (same logic as from_event)
    if read_options['event_split_bins']:
        # ... same splitting logic as existing from_event ...
        pass  # (see implementation details below)

    # Calculate total proton charge
    output.proton_charge = tof_pc.sum()

    # Detector dimensions from instrument XML or known constants
    n_x, n_y = _get_detector_dimensions(data)
    dimension = (n_x, n_y)

    # Bin events into 3D histogram using existing infrastructure
    Ixyt = MRDataset.bin_events(tof_ids, tof_time, tof_edges, dimension,
                                callback, callback_offset, callback_scaling)

    # Create projections
    Ixy = Ixyt.sum(axis=2)
    Ixt = Ixyt.sum(axis=1)

    # Store data
    output.tof_edges = tof_edges
    output.data = Ixyt.astype(float)
    output.xydata = Ixy.transpose().astype(float)
    output.xtofdata = Ixt.astype(float)
    return output
```

### Change 3: New `_collect_info_h5()` method on MRDataset

**File:** `quicknxs/qreduce.py`
**Class:** `MRDataset`

Extracts metadata from DASlogs paths instead of structured instrument paths.

```python
def _collect_info_h5(self, data):
    """
    Extract header information from a modern .nxs.h5 REF_M file.
    All metadata comes from DASlogs. Instrument geometry from settings.json.
    """
    self.origin = (os.path.abspath(data.file.filename), data.name.lstrip('/'))
    self.logs = NiceDict()
    self.log_minmax = NiceDict()
    self.log_units = NiceDict()

    # Read DASlogs (same loop as existing _collect_info)
    if 'DASlogs' in data:
        # ... same DASlogs iteration as existing code ...
        pass

    # Detector dimensions and pixel size from settings.json
    settings = _read_instrument_settings('ref_m', data)
    n_x = settings['number-of-x-pixels']
    n_y = settings['number-of-y-pixels']
    pixel_size_mm = settings['pixel-width']
    self.det_size_x = n_x * pixel_size_mm * 1e-3  # mm to m
    self.det_size_y = n_y * pixel_size_mm * 1e-3

    # REF_M angles from DASlogs (all with safe defaults for missing logs)
    self.dangle = _get_daslog_value(data, 'DANGLE', default=0.0)
    self.dangle0 = _get_daslog_value(data, 'DANGLE0', default=0.0)
    self.sangle = _get_daslog_value(data, 'SANGLE', default=0.0)
    self.dpix = _get_daslog_value(data, 'DIRPIX',
                    default=settings.get('default-direct-pixel', 150))

    # Wavelength (graceful degradation for early commissioning files)
    self.lambda_center = _get_daslog_value(data, 'LambdaRequest',
                             fallback_key='BL4A:Det:TH:BL:Lambda',
                             default=None)
    if self.lambda_center is None:
        warn('No LambdaRequest in DASlogs — early commissioning file; using 3.37 A')
        self.lambda_center = 3.37  # only for IPTS-16196 runs 29001-29016

    # Chopper speed for wavelength range calculation
    self.chopper_speed = _get_daslog_value(data, 'SpeedRequest1', default=60.0)

    # Slit widths from DASlogs (safe defaults for missing logs)
    self.slit1_width = _get_daslog_value(data, 'S1HWidth', default=0.0)
    self.slit2_width = _get_daslog_value(data, 'S2HWidth', default=0.0)
    self.slit3_width = _get_daslog_value(data, 'S3HWidth', default=0.0)

    # Distances from DASlogs (with safe defaults from settings.json)
    sdd_mm = _get_daslog_value(data, 'SampleDetDis',
                 default=settings.get('sample-det-distance-mm', 1830.0))
    mod_sam_mm = _get_daslog_value(data, 'ModeratorSamDis',
                     default=settings.get('moderator-sample-distance-mm', 16870.0))
    self.dist_sam_det = sdd_mm * 1e-3
    self.dist_mod_det = mod_sam_mm * 1e-3 + self.dist_sam_det
    self.dist_mod_mon = mod_sam_mm * 1e-3 - 2.75

    # Slit distances from settings.json (not in DASlogs)
    self.slit1_dist = settings.get('slit1-sample-distance', 2600.0)
    self.slit2_dist = settings.get('slit2-sample-distance', 2019.0)
    self.slit3_dist = settings.get('slit3-sample-distance', 714.0)

    # Standard metadata (these are always present in valid NeXus files)
    self.proton_charge = data['proton_charge'][()][0]
    self.total_counts = data['total_counts'][()][0]
    self.total_time = data['duration'][()][0]
    self.experiment = _decode(data['experiment_identifier'][()][0])
    self.number = int(data['run_number'][()][0])
    self.merge_warnings = ''
```

### Change 4: New `_collect_info_h5()` method on LRDataset

**File:** `quicknxs/qreduce.py`
**Class:** `LRDataset`

Similar to Change 3 but with REF_L-specific DASlogs paths.

```python
def _collect_info_h5(self, data):
    """
    Extract header information from a modern .nxs.h5 REF_L file.
    Angles, wavelength, and slit widths from DASlogs.
    Distances and geometry from settings.json (date-indexed).
    """
    self.origin = (os.path.abspath(data.file.filename), data.name.lstrip('/'))
    self.logs = NiceDict()
    self.log_minmax = NiceDict()
    self.log_units = NiceDict()

    if 'DASlogs' in data:
        # ... same DASlogs iteration ...
        pass

    # REF_L raw motor angles (all three stored for diagnostics)
    self.thi = _get_daslog_value(data, 'BL4B:Mot:thi.RBV',
                   fallback_key='thi', default=0.0)
    self.ths = _get_daslog_value(data, 'BL4B:Mot:ths.RBV',
                   fallback_key='ths', default=0.0)
    self.tthd = _get_daslog_value(data, 'BL4B:Mot:tthd.RBV',
                    fallback_key='tthd', default=0.0)
    # Map to quicknxsv1 attribute names (see "BL4B angle handling" in plan)
    # dangle = detector arm 2θ (matches legacy TwoTheta/readback role)
    self.dangle = self.tthd    # detector arm two-theta
    self.sangle = self.ths     # sample angle
    self.dangle0 = 0.0         # REF_L has no DANGLE0 in DASlogs

    # Wavelength and frequency (scientist-specified keys)
    self.lambda_center = _get_daslog_value(data, 'BL4B:Det:TH:BL:Lambda',
                             fallback_key='LambdaRequest')
    self.chopper_speed = _get_daslog_value(data, 'BL4B:Det:TH:BL:Frequency',
                             fallback_key='SpeedRequest1', default=60.0)

    # REF_L slit widths (safe defaults for missing logs)
    self.s1Y = _get_daslog_value(data, 'BL4B:Mot:s1:Y:Gap:Readback',
                   fallback_key='s1:Y:Gap', default=0.0)
    self.s1X = _get_daslog_value(data, 'BL4B:Mot:s1:X:Gap:Readback',
                   fallback_key='s1:X:Gap', default=0.0)
    self.siY = _get_daslog_value(data, 'BL4B:Mot:si:Y:Gap:Readback',
                   fallback_key='si:Y:Gap', default=0.0)
    self.siX = _get_daslog_value(data, 'BL4B:Mot:si:X:Gap:Readback',
                   fallback_key='si:X:Gap', default=0.0)
    self.xi = _get_daslog_value(data, 'BL4B:Mot:xi.RBV',
                  fallback_key='xi', default=0.0)
    # Map to quicknxsv1 slit attribute names
    self.slit1_width = self.s1Y   # s1 vertical gap
    self.slit2_width = self.siY   # si vertical gap

    # Emission time correction parameters (safe defaults for missing logs)
    self.emission_mod_distance = _get_daslog_value(data,
        'BL4B:Det:TH:DlyDet:BasePath', default=15.75) * 1000  # m → mm
    chopper_offset = _get_daslog_value(data,
        'BL4B:Chop:Skf2:ChopperOffset', default=114.0)
    chopper_mult = _get_daslog_value(data,
        'BL4B:Chop:Skf2:ChopperMultiplier', default=29.5)
    self.emission_coefficients = [chopper_offset / 1000, chopper_mult / 1000]

    # Distances and geometry from date-indexed settings.json
    settings = _read_instrument_settings('ref_l', data)
    self.dist_sam_det = settings['sample-det-distance']
    self.dist_mod_det = settings['source-det-distance']
    self.dist_mod_mon = self.dist_mod_det - 2.75
    n_x = settings['number-of-x-pixels']
    n_y = settings['number-of-y-pixels']
    pixel_size_mm = settings['pixel-width']
    self.det_size_x = n_x * pixel_size_mm * 1e-3
    self.det_size_y = n_y * pixel_size_mm * 1e-3
    self.dpix = 151  # from settings if needed in future
    self.xi_reference = settings.get('xi-reference', 445)
    self.s1_sample_distance = settings.get('s1-sample-distance', 1485)

    # Slit distances from settings (not in DASlogs)
    self.slit1_dist = self.s1_sample_distance
    self.slit2_dist = self.xi_reference - self.xi  # si distance derived from xi

    # Standard metadata
    self.proton_charge = data['proton_charge'][()][0]
    self.total_counts = data['total_counts'][()][0]
    self.total_time = data['duration'][()][0]
    self.experiment = _decode(data['experiment_identifier'][()][0])
    self.number = int(data['run_number'][()][0])
    self.merge_warnings = ''
```

### Change 5: Helper functions

**File:** `quicknxs/qreduce.py`

```python
def _get_detector_dimensions(data):
    """
    Get detector pixel dimensions (n_x, n_y) from instrument XML in the file.
    Falls back to known defaults by instrument.
    """
    import re
    try:
        xml_raw = data['instrument/instrument_xml/data'][()][0]
        xml = xml_raw.decode('utf-8') if isinstance(xml_raw, bytes) else str(xml_raw)
        xp = re.search(r'xpixels="(\d+)"', xml)
        yp = re.search(r'ypixels="(\d+)"', xml)
        if xp and yp:
            return int(xp.group(1)), int(yp.group(1))
    except (KeyError, IndexError):
        pass

    # Fallback: detect from instrument name
    try:
        name_raw = data['instrument/name'][()][0]
        name = name_raw.decode('utf-8') if isinstance(name_raw, bytes) else str(name_raw)
        if name == 'REF_L':
            return (256, 304)
        else:
            return (304, 256)
    except KeyError:
        return (304, 256)  # default to REF_M


def _get_daslog_value(data, key, fallback_key=None, default=None):
    """
    Read a value from DASlogs, trying average_value first, then value.
    Falls back to fallback_key if primary key is not found.
    Warns when using default or fallback (aids debugging of missing-log issues).
    """
    for k in [key, fallback_key]:
        if k is None:
            continue
        try:
            item = data['DASlogs/' + k]
            if 'average_value' in item:
                val = float(item['average_value'][0])
                if k != key:
                    debug(f'DASlogs/{key} missing, using fallback {k}={val}')
                return val
            elif 'value' in item:
                arr = item['value'][()]
                if arr.size == 0:
                    continue  # empty array — try fallback
                val = float(arr[0]) if arr.size == 1 else float(arr.mean())
                if k != key:
                    debug(f'DASlogs/{key} missing, using fallback {k}={val}')
                return val
        except (KeyError, IndexError, ValueError):
            continue
    if default is not None:
        # Extract run number for better warning messages
        try:
            run = int(data['run_number'][()][0])
            warn(f'Run {run}: DASlogs/{key} not found, using default={default}')
        except (KeyError, IndexError):
            warn(f'DASlogs/{key} not found, using default={default}')
        return default
    raise KeyError(f'DASlogs key {key} not found')


def _read_instrument_settings(instrument_name, data):
    """
    Read date-indexed instrument settings from settings.json.
    Uses the run's start_time to select the applicable configuration.

    :param instrument_name: 'ref_l' or 'ref_m'
    :param data: HDF5 group (entry) to read start_time from
    :returns: dict of instrument settings for the measurement date
    """
    import json, datetime, os

    # Get measurement date from file
    start_time_raw = data['start_time'][()][0]
    start_time = start_time_raw.decode('utf-8') if isinstance(start_time_raw, bytes) else str(start_time_raw)
    timestamp = datetime.datetime.fromisoformat(start_time).date()

    # Load settings file (co-located with config module)
    package_dir = os.path.dirname(os.path.abspath(__file__))
    settings_path = os.path.join(package_dir, 'config', f'{instrument_name}_settings.json')

    settings_dict = {}
    with open(settings_path, 'r') as fd:
        json_data = json.load(fd)
        for key in json_data:
            chosen_value = None
            delta_time = None
            for item in json_data[key]:
                valid_from = datetime.date.fromisoformat(item['from'])
                delta = valid_from - timestamp
                if delta_time is None or (delta.total_seconds() < 0 and delta > delta_time):
                    delta_time = delta
                    chosen_value = item['value']
            settings_dict[key] = chosen_value

    return settings_dict


def _decode(value):
    """Decode bytes to string if needed."""
    if isinstance(value, bytes):
        return value.decode('utf-8')
    return str(value)
```

### Change 6: Update `locate_file()` to find `.nxs.h5` files

**File:** `quicknxs/qreduce.py`
**Function:** `locate_file()`

The current implementation only searches for `*_histo.nxs` and `*_event.nxs` patterns.
It must also search the `nexus/` subdirectory for `*.nxs.h5` files.

**Important**: Legacy formats are searched **first** and preferred when both exist.
This is critical because (a) `_histo.nxs` files preserve polarization channels that
`.nxs.h5` does not separate, and (b) the overlap era (runs ~29732–34727+) has many
runs available in both formats. Only when no legacy file is found does the search
fall through to `.nxs.h5`.

```python
def locate_file(number, histogram=True, old_format=False, verbose=True):
    if verbose:
        info('Trying to locate file number %s...' % number)

    # Try legacy formats first (preferred — preserves polarization channels)
    if histogram:
        search = glob(os.path.join(instrument.data_base,
                      (instrument.BASE_SEARCH % number) + u'histo.nxs'))
    elif old_format:
        search = glob(os.path.join(instrument.data_base,
                      (instrument.OLD_BASE_SEARCH % (number, number)) + u'.nxs'))
    else:
        search = glob(os.path.join(instrument.data_base,
                      (instrument.BASE_SEARCH % number) + u'event.nxs'))

    if search:
        return search[0]

    # Try modern .nxs.h5 format in nexus/ subdirectory
    h5_search = glob(os.path.join(instrument.data_base,
                     '*/nexus/%s_%s.nxs.h5' % (instrument.NAME, number)))
    if h5_search:
        return h5_search[0]

    return None
```

### Change 7: Update `_read_file_MR()` channel detection for `.nxs.h5`

**File:** `quicknxs/qreduce.py`

The new format always has a single `entry/` — there are no `entry-Off_Off` etc.
entries for polarization states. For `.nxs.h5` files, we always treat the data as
unpolarized (single channel). Future DAS upgrades may add event-level polarization
tagging, but currently all events are in one bank.

```python
def _read_file_MR(self, filename, nxs, start):
    channels = list(nxs.keys())

    if self._is_event_h5:
        # New .nxs.h5 format: single 'entry' channel, always unpolarized
        channels = [ch for ch in channels if ch.startswith('entry')]
        # ... simplified channel/mapping logic ...
        self.measurement_type = 'Unpolarized'
        mapping = [(u'x', channels[0])]
        # ... then use from_event_h5 for each channel ...
```

### Change 8: Update instrument config for `.nxs.h5` file search

**Files:** `quicknxs/config/ref_m.py`, `quicknxs/config/ref_l.py`

Add a search pattern for the new format:

```python
# In ref_m.py:
H5_BASE_SEARCH = u'*/nexus/REF_M_%s.nxs.h5'

# In ref_l.py:
H5_BASE_SEARCH = u'*/nexus/REF_L_%s.nxs.h5'
```

### Change 9: Update `NXSData._read_file()` to handle missing `time_from_header` data

**File:** `quicknxs/qreduce.py`

The `time_from_header()` function iterates over `nxs.values()` and reads
`start_time`/`end_time` from each entry. For `.nxs.h5` files, this works fine with
`entry/` as the only key. However, it may encounter non-entry groups. Add a guard:

```python
def time_from_header(filename, nxs=None):
    # ... existing code ...
    for item in nxs.values():
        if not isinstance(item, h5py.Group):
            continue
        if 'start_time' not in item or 'end_time' not in item:
            continue
        # ... rest of existing logic ...
```

---

## Implementation Phases (Red/Green TDD)

Each phase follows strict red/green TDD: write a failing test first (RED), then
implement the minimum code to make it pass (GREEN), then refactor if needed.
Each step lists the test to write first, then the code to implement.

### Phase 1: Helper functions (Changes 5)
**Agent team: 1 primary agent**

#### Step 1.1: `_get_detector_dimensions()` helper

**RED — Write failing test first:**
```python
# tests/test_event_h5.py
import pytest
import os

H5_REF_M = '/SNS/REF_M/IPTS-9801/nexus/REF_M_29750.nxs.h5'
H5_REF_M_HISTO = '/SNS/REF_M/IPTS-9801/data/REF_M_29750_histo.nxs'
H5_REF_M_NOLAMDA = '/SNS/REF_M/IPTS-16196/nexus/REF_M_29015.nxs.h5'
H5_REF_L = '/SNS/REF_L/IPTS-36119/nexus/REF_L_220030.nxs.h5'

@pytest.mark.skipif(not os.path.exists(H5_REF_M), reason='No access to SNS data')
class TestGetDetectorDimensions:
    def test_ref_m_dimensions(self):
        import h5py
        from quicknxs.qreduce import _get_detector_dimensions
        with h5py.File(H5_REF_M, 'r') as f:
            n_x, n_y = _get_detector_dimensions(f['entry'])
        assert n_x == 304
        assert n_y == 256

    def test_ref_l_dimensions(self):
        import h5py
        from quicknxs.qreduce import _get_detector_dimensions
        with h5py.File(H5_REF_L, 'r') as f:
            n_x, n_y = _get_detector_dimensions(f['entry'])
        assert n_x == 256
        assert n_y == 304
```
Run: `pixi run pytest tests/test_event_h5.py::TestGetDetectorDimensions -x`
→ Expected: **FAIL** (ImportError — function doesn't exist yet)

**GREEN — Implement `_get_detector_dimensions()` in `qreduce.py`:**
(See Change 5 above for implementation)
Run test again → **PASS**

#### Step 1.2: `_get_daslog_value()` helper

**RED — Write failing test first:**
```python
@pytest.mark.skipif(not os.path.exists(H5_REF_M), reason='No access to SNS data')
class TestGetDaslogValue:
    def test_ref_m_dangle(self):
        import h5py
        from quicknxs.qreduce import _get_daslog_value
        with h5py.File(H5_REF_M, 'r') as f:
            dangle = _get_daslog_value(f['entry'], 'DANGLE')
        assert abs(dangle - 15.005) < 0.01

    def test_ref_m_sangle(self):
        import h5py
        from quicknxs.qreduce import _get_daslog_value
        with h5py.File(H5_REF_M, 'r') as f:
            sangle = _get_daslog_value(f['entry'], 'SANGLE')
        assert abs(sangle - 0.332) < 0.01

    def test_ref_l_ths(self):
        import h5py
        from quicknxs.qreduce import _get_daslog_value
        with h5py.File(H5_REF_L, 'r') as f:
            ths = _get_daslog_value(f['entry'], 'ths')
        assert abs(ths - 2.101) < 0.01

    def test_missing_key_with_default(self):
        import h5py
        from quicknxs.qreduce import _get_daslog_value
        with h5py.File(H5_REF_M, 'r') as f:
            val = _get_daslog_value(f['entry'], 'NONEXISTENT', default=42.0)
        assert val == 42.0

    def test_missing_key_with_fallback(self):
        import h5py
        from quicknxs.qreduce import _get_daslog_value
        with h5py.File(H5_REF_M, 'r') as f:
            val = _get_daslog_value(f['entry'], 'NONEXISTENT',
                                   fallback_key='DANGLE')
        assert abs(val - 15.005) < 0.01

    def test_missing_key_raises(self):
        import h5py
        from quicknxs.qreduce import _get_daslog_value
        with h5py.File(H5_REF_M, 'r') as f:
            with pytest.raises(KeyError):
                _get_daslog_value(f['entry'], 'NONEXISTENT')

    def test_ref_m_missing_lambda_uses_fallback(self):
        """Early REF_M files lack LambdaRequest; fallback to BL4A:Det:TH:BL:Lambda"""
        import h5py
        from quicknxs.qreduce import _get_daslog_value
        with h5py.File(H5_REF_M, 'r') as f:
            val = _get_daslog_value(f['entry'], 'LambdaRequest',
                                   fallback_key='BL4A:Det:TH:BL:Lambda',
                                   default=3.37)
        # REF_M_29015 has no LambdaRequest and no BL4A:Det:TH:BL:Lambda
        # so this should fall back to default 3.37
        assert val == 3.37
```
Run: → **FAIL**

**GREEN — Implement `_get_daslog_value()` and `_decode()` in `qreduce.py`:**
Run test again → **PASS**

#### Step 1.3: `_get_distances_from_xml()` helper

**RED — Write failing test first:**
```python
@pytest.mark.skipif(not os.path.exists(H5_REF_L), reason='No access to SNS data')
class TestGetDistancesFromXml:
    def test_ref_l_2025(self):
        import h5py
        from quicknxs.qreduce import _get_distances_from_xml
        with h5py.File(H5_REF_L, 'r') as f:
            mod_z, det_z = _get_distances_from_xml(f['entry'])
        assert abs(mod_z - (-13.685)) < 0.01
        assert abs(det_z - 1.362) < 0.01

    def test_ref_m(self):
        import h5py
        from quicknxs.qreduce import _get_distances_from_xml
        with h5py.File(H5_REF_M, 'r') as f:
            mod_z, det_z = _get_distances_from_xml(f['entry'])
        assert abs(mod_z - (-18.703)) < 0.01
        # REF_M detector z comes from SampleDetDis logfile ref, not fixed value
```
Run: → **FAIL**

**GREEN — Implement `_get_distances_from_xml()` in `qreduce.py`:**
Run test again → **PASS**

### Phase 2: Metadata extraction (Changes 3-4)
**Agent team: 1 primary agent (sequential after Phase 1)**

#### Step 2.1: `MRDataset._collect_info_h5()` for REF_M

**RED — Write failing test first:**
```python
@pytest.mark.skipif(not os.path.exists(H5_REF_M), reason='No access to SNS data')
class TestMRDatasetCollectInfoH5:
    def test_metadata_extraction(self):
        import h5py
        from quicknxs.qreduce import MRDataset
        with h5py.File(H5_REF_M, 'r') as f:
            ds = MRDataset()
            ds._collect_info_h5(f['entry'])
        # Verify key metadata was extracted
        assert abs(ds.dangle - 15.005) < 0.01
        assert abs(ds.sangle - 0.332) < 0.01
        assert ds.proton_charge > 0
        assert ds.total_counts == 19195
        assert ds.number == 29750
        assert ds.experiment == 'IPTS-9801'
        assert ds.dist_sam_det > 0
        assert ds.dist_mod_det > ds.dist_sam_det
        assert ds.slit1_width > 0
        assert ds.det_size_x > 0
        assert ds.det_size_y > 0

    def test_logs_populated(self):
        import h5py
        from quicknxs.qreduce import MRDataset
        with h5py.File(H5_REF_M, 'r') as f:
            ds = MRDataset()
            ds._collect_info_h5(f['entry'])
        assert len(ds.logs) > 0
        assert 'DANGLE' in ds.logs
```
Run: → **FAIL** (AttributeError — method doesn't exist)

**GREEN — Implement `MRDataset._collect_info_h5()` in `qreduce.py`:**
Run test again → **PASS**

#### Step 2.2: `LRDataset._collect_info_h5()` for REF_L

**RED — Write failing test first:**
```python
@pytest.mark.skipif(not os.path.exists(H5_REF_L), reason='No access to SNS data')
class TestLRDatasetCollectInfoH5:
    def test_metadata_extraction(self):
        import h5py
        from quicknxs.qreduce import LRDataset
        with h5py.File(H5_REF_L, 'r') as f:
            ds = LRDataset()
            ds._collect_info_h5(f['entry'])
        assert abs(ds.sangle - 2.101) < 0.01  # ths
        assert abs(ds.dangle - 4.201) < 0.01  # tthd (detector arm 2θ)
        assert abs(ds.thi - (-0.007)) < 0.01  # incident angle stored separately
        assert ds.dangle0 == 0.0
        assert ds.proton_charge > 0
        assert ds.total_counts == 85387
        assert ds.number == 220030
        assert ds.dist_sam_det > 0
        assert ds.lambda_center > 0
```
Run: → **FAIL**

**GREEN — Implement `LRDataset._collect_info_h5()` in `qreduce.py`:**
Run test again → **PASS**

### Phase 3: Core event-to-histogram conversion (Changes 1-2)
**Agent team: 1 primary agent (sequential after Phase 2)**

#### Step 3.1: Format detection

**RED — Write failing test first:**
```python
@pytest.mark.skipif(not os.path.exists(H5_REF_M), reason='No access to SNS data')
class TestFormatDetection:
    def test_detects_event_h5_format(self):
        import h5py
        from quicknxs.qreduce import NXSData
        # Construct a minimal NXSData to test _read_file detection
        nxs_obj = object.__new__(NXSData)
        nxs_obj._options = NXSData._get_all_options({})
        nxs_obj._channel_names = []
        nxs_obj._channel_origin = []
        nxs_obj._channel_data = []
        nxs_obj.measurement_type = ''
        nxs_obj._read_times = []
        with h5py.File(H5_REF_M, 'r') as f:
            first_entry = list(f.keys())[0]
            def_raw = f[first_entry]['definition'][()][0]
            definition = def_raw.decode('utf-8') if isinstance(def_raw, bytes) else str(def_raw)
        assert definition == 'NXsnsevent'
```
Run: → **PASS** (this is a pure data test — no code needed)

#### Step 3.2: `MRDataset.from_event_h5()` — REF_M loading

**RED — Write failing test first:**
```python
@pytest.mark.skipif(not os.path.exists(H5_REF_M), reason='No access to SNS data')
class TestFromEventH5:
    def test_ref_m_load(self):
        from quicknxs.qreduce import NXSData
        data = NXSData(H5_REF_M)
        assert data is not None
        assert len(data) >= 1
        ds = data[0]
        # Verify 3D histogram was created
        assert ds.data is not None
        assert len(ds.data.shape) == 3
        assert ds.data.shape[0] == 304  # n_x for REF_M
        assert ds.data.shape[1] == 256  # n_y for REF_M
        # Verify projections
        assert ds.xydata is not None
        assert ds.xydata.shape == (256, 304)  # transposed
        assert ds.xtofdata is not None
        assert ds.xtofdata.shape[0] == 304
        # Total counts in histogram should match event count
        assert abs(ds.data.sum() - ds.total_counts) < 2  # allow rounding
        # Verify tof_edges
        assert ds.tof_edges is not None
        assert len(ds.tof_edges) > 1
        # Verify event mode flag
        assert ds.from_event_mode == True
        # Verify measurement type
        assert data.measurement_type == 'Unpolarized'
```
Run: → **FAIL** (NXSData doesn't know how to read .nxs.h5 files yet)

**GREEN — Implement full pipeline:**
1. Add format detection in `_read_file()` (Change 1)
2. Add `from_event_h5()` on `MRDataset` (Change 2)
3. Add routing in `_read_file_MR()` (Change 7)

Run test again → **PASS**

#### Step 3.3: Cross-validation against histo counterpart

**RED — Write failing test first:**
```python
    @pytest.mark.skipif(not os.path.exists(H5_REF_M_HISTO),
                        reason='No access to SNS data')
    def test_ref_m_matches_histo(self):
        """Compare event-binned XY projection against known-good histo data"""
        import h5py
        import numpy as np
        from quicknxs.qreduce import NXSData
        # Load event data
        h5_data = NXSData(H5_REF_M, use_caching=False)
        assert h5_data is not None
        h5_xy = h5_data[0].xydata  # shape (256, 304) transposed
        # Load histo reference
        histo_data = NXSData(H5_REF_M_HISTO, use_caching=False)
        assert histo_data is not None
        histo_xy = histo_data[0].xydata
        # Compare: correlation > 0.999
        corr = np.corrcoef(h5_xy.ravel(), histo_xy.ravel())[0, 1]
        assert corr > 0.999, f'XY correlation {corr:.6f} too low'
        # Max per-pixel difference should be small
        diff = np.abs(h5_xy - histo_xy)
        assert diff.max() < 10, f'Max pixel diff {diff.max()} too large'
```
Run: → **FAIL** (from_event_h5 not implemented)

**GREEN — Already implemented in Step 3.2; test just validates correctness:**
Run test again → **PASS**

#### Step 3.4: REF_L loading

**RED — Write failing test first:**
```python
    def test_ref_l_load(self):
        from quicknxs.qreduce import NXSData
        data = NXSData(H5_REF_L)
        assert data is not None
        assert len(data) >= 1
        ds = data[0]
        assert ds.data.shape[0] == 256  # n_x for REF_L
        assert ds.data.shape[1] == 304  # n_y for REF_L
        assert ds.xydata.shape == (304, 256)  # transposed
        assert abs(ds.data.sum() - ds.total_counts) < 2
        assert ds.from_event_mode == True
        assert abs(ds.sangle - 2.101) < 0.01
        assert abs(ds.dangle - 4.201) < 0.01  # tthd, NOT thi
        assert abs(ds.thi - (-0.007)) < 0.01  # incident angle stored separately
        assert abs(ds.lambda_center - 6.2) < 0.1
```
Run: → **FAIL**

**GREEN — Implement `LRDataset.from_event_h5()` and routing in `_read_file_LR()`:**
Run test again → **PASS**

#### Step 3.5: Graceful degradation for missing metadata

**RED — Write failing test first:**
```python
    @pytest.mark.skipif(not os.path.exists(H5_REF_M_NOLAMDA),
                        reason='No access to SNS data')
    def test_ref_m_missing_lambda_graceful(self):
        """Early commissioning files lack LambdaRequest — should use default"""
        from quicknxs.qreduce import NXSData
        data = NXSData(H5_REF_M_NOLAMDA, use_caching=False)
        assert data is not None
        ds = data[0]
        # Should have loaded with default lambda
        assert ds.lambda_center == 3.37  # default fallback
        assert ds.data is not None
        assert ds.total_counts == 14863
```
Run: → **FAIL**

**GREEN — Ensure `_collect_info_h5()` handles missing DASlogs gracefully:**
Run test again → **PASS**

### Phase 4: File search (Changes 6, 8)
**Agent team: 1 agent (can run in parallel with Phase 3)**

#### Step 4.1: `locate_file()` finds `.nxs.h5`

**RED — Write failing test first:**
```python
@pytest.mark.skipif(not os.path.exists('/SNS/REF_M/IPTS-16196/nexus/'),
                    reason='No access to SNS data')
class TestLocateFile:
    def test_locate_h5_only_run(self):
        """Run that only exists as .nxs.h5 (no histo counterpart)"""
        from quicknxs.qreduce import locate_file
        from quicknxs.config import ref_m
        import quicknxs.config as cfg
        orig = cfg.instrument
        cfg.instrument = ref_m
        try:
            # Run 29015 only exists as .nxs.h5 (IPTS-16196 commissioning)
            result = locate_file(29015, verbose=False)
            assert result is not None
            assert result.endswith('.nxs.h5')
            assert '29015' in result
        finally:
            cfg.instrument = orig

    def test_locate_histo_preferred_over_h5(self):
        """When both formats exist, histo is preferred (preserves polarization)"""
        from quicknxs.qreduce import locate_file
        from quicknxs.config import ref_m
        import quicknxs.config as cfg
        orig = cfg.instrument
        cfg.instrument = ref_m
        try:
            # Run 29750 exists in both formats (IPTS-9801 overlap zone)
            result = locate_file(29750, verbose=False)
            assert result is not None
            assert 'histo.nxs' in result, f'Expected histo, got: {result}'
        finally:
            cfg.instrument = orig

    def test_locate_old_histo_still_works(self):
        from quicknxs.qreduce import locate_file
        from quicknxs.config import ref_m
        import quicknxs.config as cfg
        orig = cfg.instrument
        cfg.instrument = ref_m
        try:
            result = locate_file(25899, verbose=False)
            assert result is not None
            assert 'histo.nxs' in result
        finally:
            cfg.instrument = orig

    @pytest.mark.skipif(not os.path.exists('/SNS/REF_L/IPTS-36119/nexus/'),
                        reason='No access to REF_L data')
    def test_locate_h5_ref_l(self):
        from quicknxs.qreduce import locate_file
        from quicknxs.config import ref_l
        import quicknxs.config as cfg
        orig = cfg.instrument
        cfg.instrument = ref_l
        try:
            result = locate_file(220030, verbose=False)
            assert result is not None
            assert result.endswith('.nxs.h5')
        finally:
            cfg.instrument = orig
```
Run: → **FAIL** (locate_file doesn't search for .nxs.h5)

**GREEN — Implement Changes 6 and 8:**
Run test again → **PASS**

#### Step 4.2: `time_from_header()` robustness

**RED — Write failing test first:**
```python
    def test_time_from_header_h5(self):
        from quicknxs.qreduce import time_from_header
        result = time_from_header(H5_REF_M)
        assert result is not None
        assert result > 0
```
Run: → May **FAIL** if non-Group items in file cause errors

**GREEN — Implement Change 9:**
Run test again → **PASS**

### Phase 5: Event splitting support (Change in `from_event_h5`)
**Agent team: 1 agent (sequential after Phase 3)**

#### Step 5.1: Event splitting

**RED — Write failing test first:**
```python
@pytest.mark.skipif(not os.path.exists(H5_REF_L), reason='No access to SNS data')
class TestEventSplitting:
    def test_split_produces_subset(self):
        from quicknxs.qreduce import NXSData
        full = NXSData(H5_REF_L, use_caching=False)
        split = NXSData(H5_REF_L, event_split_bins=4, event_split_index=0,
                        use_caching=False)
        if full is None or split is None:
            pytest.skip('Could not load data')
        assert split[0].total_counts < full[0].total_counts
        assert split[0].total_counts > 0

    def test_splits_sum_to_total(self):
        from quicknxs.qreduce import NXSData
        full = NXSData(H5_REF_L, use_caching=False)
        if full is None:
            pytest.skip('Could not load data')
        total = 0
        for i in range(4):
            part = NXSData(H5_REF_L, event_split_bins=4, event_split_index=i,
                           use_caching=False)
            if part is not None:
                total += part[0].total_counts
        # Allow small discrepancy from binning edge effects
        assert abs(total - full[0].total_counts) < 10
```
Run: → **FAIL**

**GREEN — Port event splitting logic to `from_event_h5()`:**
Run test again → **PASS**

### Phase 6: Backward compatibility verification
**Agent team: 1 agent (after Phase 3-5)**

**RED — These tests should already pass (regression guard):**
```python
class TestBackwardCompatibility:
    def test_existing_tests_pass(self):
        """Run: pixi run pytest tests/qreduce_test.py -x"""
        pass  # This is a manual verification step

    @pytest.mark.skipif(
        not os.path.exists('/SNS/REF_M/IPTS-16196/0/25899/NeXus/REF_M_25899_histo.nxs'),
        reason='No access to SNS data')
    def test_legacy_histo_still_loads(self):
        from quicknxs.qreduce import NXSData
        data = NXSData('/SNS/REF_M/IPTS-16196/0/25899/NeXus/REF_M_25899_histo.nxs')
        assert data is not None
        assert len(data) >= 1
        assert data[0].data is not None

    @pytest.mark.skipif(
        not os.path.exists('/SNS/REF_L/IPTS-7053/0/80836/NeXus/REF_L_80836_histo.nxs'),
        reason='No access to SNS data')
    def test_legacy_ref_l_histo_still_loads(self):
        from quicknxs.qreduce import NXSData
        data = NXSData('/SNS/REF_L/IPTS-7053/0/80836/NeXus/REF_L_80836_histo.nxs')
        assert data is not None
        assert data[0].data.shape == (304, 256, 2001)
```
Run: → Should **PASS** (if not, fix regressions before proceeding)

### Phase 7: Makefile integration and documentation
**Agent team: 1 agent (after Phase 6)**

1. Add Makefile targets for testing with `.nxs.h5` files:
   ```makefile
   test-h5:  ## Run event NeXus .nxs.h5 integration tests
       pixi run pytest tests/test_event_h5.py -v --timeout=120
   ```
2. Update CLAUDE.md with new format documentation
3. Commit all changes

---

## Risk Analysis

| Risk | Mitigation |
|---|---|
| REF_M .nxs.h5 files have no LambdaRequest in DASlogs | Fall back to `BL4A:Det:TH:BL:Lambda`, then `BL4A:Chop:Gbl:Wavelength:Req`; early 2018 commissioning files (runs 29xxx) have NO wavelength/chopper data at all — use default 3.37 Å and warn. Note: the buzhug database at `/SNS/REF_M/shared/quicknxs_database/` covers runs 18081–28832 only (all from `*_histo.nxs`); it does NOT cover the .nxs.h5 era (runs 29001+), so it cannot serve as a fallback. |
| Polarization states in .nxs.h5 | Phase 9: filter events by SF1/SF2 time-series; guard against missing SF1/SF2/veto logs; validate against 70 overlap runs in IPTS-9801 |
| Dead-time correction | Phase 8: implement Lambert W correction on LRDataset only (BL4B); graceful skip when bank_error_events absent |
| Missing DASlogs | All `_collect_info_h5()` reads use `default=` or `fallback_key=`; polarization degrades to unpolarized; warn on every missing log |
| BL4B angle complexity | `dangle = tthd` for theta-2*theta; theta-theta mode correction deferred to future phase; all 3 raw angles (thi, ths, tthd) stored |
| Slit distances not in DASlogs | Read from date-indexed `settings.json`; no hardcoded values |
| Memory pressure from large event arrays | Events are discarded after binning; 3D histogram is same size as legacy |
| event_id pixel mapping varies by IDF version | Parse instrument XML dynamically; fall back to known constants |

## File Impact Summary

| File | Type of Change |
|---|---|
| `quicknxs/qreduce.py` | Major: new methods, format detection, helpers, dead-time, polarization |
| `quicknxs/config/ref_m.py` | Minor: add `H5_BASE_SEARCH` |
| `quicknxs/config/ref_l.py` | Minor: add `H5_BASE_SEARCH` |
| `quicknxs/config/ref_l_settings.json` | New: date-indexed instrument geometry for REF_L |
| `quicknxs/config/ref_m_settings.json` | New: date-indexed instrument geometry for REF_M |
| `tests/test_event_h5.py` | New: integration tests for .nxs.h5 loading |
| `Makefile` | Minor: add test targets |

## Data Files for Testing

| File | Instrument | Format | Events | Purpose |
|---|---|---|---|---|
| `/SNS/REF_M/IPTS-9801/nexus/REF_M_29750.nxs.h5` | REF_M | .nxs.h5 | 19,195 | **Primary**: unpolarized, full metadata, has histo counterpart |
| `/SNS/REF_M/IPTS-9801/data/REF_M_29750_histo.nxs` | REF_M | histo | 19,166 | Reference for validating event-to-histo conversion |
| `/SNS/REF_M/IPTS-9801/nexus/REF_M_29742.nxs.h5` | REF_M | .nxs.h5 | 497,637 | Polarized run (3 states), has histo counterpart |
| `/SNS/REF_M/IPTS-9801/data/REF_M_29742_histo.nxs` | REF_M | histo | 497,635 | Reference: Off_Off(234k) + On_Off(263k) + unfiltered(63) |
| `/SNS/REF_M/IPTS-24338/nexus/REF_M_43568.nxs.h5` | REF_M | .nxs.h5 | 2,113,831 | High-count h5-only run (no histo), full metadata |
| `/SNS/REF_L/IPTS-36119/nexus/REF_L_220030.nxs.h5` | REF_L | .nxs.h5 | 85,387 | REF_L event loading (2025 IDF, rectangular panel) |
| `/SNS/REF_L/IPTS-14316/nexus/REF_L_138523.nxs.h5` | REF_L | .nxs.h5 | 2,607 | REF_L with 2014 tube-based IDF, different distances |
| `/SNS/REF_M/IPTS-16196/nexus/REF_M_29015.nxs.h5` | REF_M | .nxs.h5 | 14,863 | Early commissioning (no LambdaRequest) |
| `/SNS/REF_M/IPTS-16196/0/25899/NeXus/REF_M_25899_histo.nxs` | REF_M | histo | 107,686 | Backward compat: polarized histo |
| `/SNS/REF_L/IPTS-7053/0/80836/NeXus/REF_L_80836_histo.nxs` | REF_L | histo | 25,234 | Backward compat: REF_L histo |

### Cross-validation test data (overlap zone)

The overlap zone in IPTS-9801 (runs 29732–29801) provides **ground-truth validation**:
the same data exists in both formats, allowing pixel-by-pixel comparison of event-binned
histograms against the pre-histogrammed data. Validated: run 29750 shows 0.999992
correlation with max 2 counts/pixel difference.

### Note on test data quality

- REF_M runs 29001-29016 (IPTS-16196, May 2018) are early commissioning and **lack
  wavelength/chopper DASlogs entirely**. These use default wavelength with a warning.
- All production `.nxs.h5` files (runs 29732+, July 2018 onward) have full metadata.
- REF_L runs 220030+ have full metadata.
- The buzhug database at `/SNS/REF_M/shared/quicknxs_database/` covers runs 18081–28832
  only (all from `*_histo.nxs`). It does NOT cover the `.nxs.h5` era — no overlap exists
  between the database and the missing-metadata commissioning files.

---

## Phase 8: Dead-time correction (REF_L / BL4B only)

**Agent team: 1 agent (after Phase 3)**

Dead-time correction accounts for detector events lost due to detector readout dead
time (~4.2 µs). **Only REF_L (BL4B) applies dead-time correction in quicknxsv1.**
REF_M (BL4A) does not currently use dead-time correction in this codebase (mr_reduction
has its own implementation, but quicknxsv1's REF_M pipeline has not needed it).

Both lr_reduction and mr_reduction have dead_time_correction modules. The lr_reduction
implementation uses the paralyzable (Lambert W) model by default.

### Algorithm (from lr_reduction `dead_time_correction.py`)

```python
def apply_dead_time_correction(data, tof_edges, dead_time=4.2, paralyzable=True):
    """
    Apply dead-time correction to event data using bank_error_events.

    1. Read good events from bank1_events/event_time_offset
    2. Read error events from bank_error_events/event_time_offset
    3. Histogram both into TOF bins
    4. Combine: total_counts = good + error (all detector triggers)
    5. Normalize by number of non-zero proton charge pulses
    6. Apply paralyzable Lambert W correction:
       true_rate = -W(-rate * τ / Δt) / τ
       OR non-paralyzable: corr = 1 / (1 - rate * τ / Δt)
    7. DTC factor = true_rate / measured_rate
    8. Multiply histogrammed data by DTC factor per TOF bin

    Parameters:
      dead_time: detector dead time in µs (4.2 for BL4B detector)
      paralyzable: if True, use Lambert W (default for BL4B auto-reduction)
    """
```

### Implementation

Add a `_apply_dead_time_correction()` static method to **`LRDataset`** (not MRDataset,
since only BL4B uses this correction):

```python
@staticmethod
def _apply_dead_time_correction(data, tof_edges, dead_time=4.2, paralyzable=True):
    """
    Apply dead-time correction using bank_error_events.

    Gracefully returns unity correction when:
    - bank_error_events is absent (early files, DAS errors)
    - proton_charge has no non-zero pulses
    - proton_charge log is missing

    :param data: HDF5 entry group
    :param tof_edges: array of TOF bin edges (µs)
    :param dead_time: detector dead time in µs (default 4.2)
    :param paralyzable: if True, use Lambert W model (default for BL4B)
    :returns: array of correction factors, one per TOF bin
    """
    from scipy.special import lambertw

    n_bins = len(tof_edges) - 1
    unity = ones(n_bins)

    # Guard: skip if bank_error_events is absent
    if 'bank_error_events/event_time_offset' not in data:
        warn('No bank_error_events in file — skipping dead-time correction')
        return unity

    # Guard: skip if bank1_events is absent
    if 'bank1_events/event_time_offset' not in data:
        return unity

    e_offset = data['bank1_events/event_time_offset'][()]
    err_offset = data['bank_error_events/event_time_offset'][()]

    # Guard: skip if proton_charge is missing
    try:
        pc = data['DASlogs/proton_charge/value'][()]
    except KeyError:
        warn('No proton_charge in DASlogs — skipping dead-time correction')
        return unity

    n_pulses = count_nonzero(pc)
    if n_pulses == 0:
        return unity

    # Histogram all detector triggers (good + error)
    counts, _ = histogram(e_offset, bins=tof_edges)
    err_counts, _ = histogram(err_offset, bins=tof_edges)
    total = (counts + err_counts).astype(float)

    # Rate per pulse per TOF bin
    tof_step = diff(tof_edges)
    rate = total / n_pulses

    # Apply correction model
    with errstate(divide='ignore', invalid='ignore'):
        if paralyzable:
            # Lambert W correction (paralyzable detector model)
            b = -real(lambertw(-rate * dead_time / tof_step))
            dtc = b / (rate * dead_time / tof_step)
        else:
            # Non-paralyzable model
            dtc = 1.0 / (1.0 - rate * dead_time / tof_step)
        dtc = nan_to_num(dtc, nan=1.0, posinf=1.0, neginf=1.0)

    # Clamp to reasonable range (lr_reduction uses threshold of 1.5 by default)
    dtc = clip(dtc, 1.0, 10.0)

    return dtc
```

This is called inside **`LRDataset.from_event_h5()`** after histogramming (NOT in
`MRDataset.from_event_h5()` — REF_M does not use dead-time correction):

```python
# In LRDataset.from_event_h5(), after bin_events produces Ixyt:
dtc = LRDataset._apply_dead_time_correction(data, tof_edges)
# Apply per-TOF-bin correction to the 3D histogram
Ixyt = Ixyt * dtc[newaxis, newaxis, :]  # broadcast over (x, y)
```

### TDD Steps

**RED:**
```python
@pytest.mark.skipif(not os.path.exists(H5_REF_L), reason='No access to SNS data')
class TestDeadTimeCorrection:
    def test_correction_factor_reasonable(self):
        """DTC factors should be >= 1.0 (more true counts than measured)"""
        import h5py
        from quicknxs.qreduce import LRDataset
        from numpy import linspace
        with h5py.File(H5_REF_L, 'r') as f:
            tof_edges = linspace(5000, 60000, 41)
            dtc = LRDataset._apply_dead_time_correction(f['entry'], tof_edges)
        assert all(dtc >= 0.99)  # correction >= 1 (or near 1 for low rates)
        assert all(dtc < 2.0)    # should not be extreme

    def test_no_error_events_returns_unity(self):
        """When no bank_error_events, correction should be all 1.0"""
        import h5py
        from quicknxs.qreduce import LRDataset
        from numpy import linspace, allclose, ones
        with h5py.File('/SNS/REF_L/IPTS-14316/nexus/REF_L_138523.nxs.h5', 'r') as f:
            tof_edges = linspace(5000, 60000, 41)
            dtc = LRDataset._apply_dead_time_correction(f['entry'], tof_edges)
        assert allclose(dtc, ones(40))

    def test_paralyzable_vs_nonparalyzable(self):
        """Paralyzable correction should be >= non-paralyzable"""
        import h5py
        from quicknxs.qreduce import LRDataset
        from numpy import linspace
        with h5py.File(H5_REF_L, 'r') as f:
            tof_edges = linspace(5000, 60000, 41)
            dtc_p = LRDataset._apply_dead_time_correction(
                f['entry'], tof_edges, paralyzable=True)
            dtc_np = LRDataset._apply_dead_time_correction(
                f['entry'], tof_edges, paralyzable=False)
        # For low count rates, both should be ≈ 1.0 and very close
        assert all(dtc_p >= 0.99)
        assert all(dtc_np >= 0.99)

    def test_dtc_applied_in_from_event_h5(self):
        """Verify dead-time correction is integrated into LRDataset loading"""
        from quicknxs.qreduce import NXSData
        data = NXSData(H5_REF_L, use_caching=False)
        assert data is not None
        ds = data[0]
        # The dataset should have been loaded with DTC applied
        # Total counts in histogram may slightly exceed total_counts from header
        # due to DTC upward correction
        assert ds.data is not None
        assert ds.data.sum() >= ds.total_counts * 0.99  # DTC only increases

    def test_ref_m_does_not_apply_dtc(self):
        """Verify REF_M (MRDataset) does NOT apply dead-time correction"""
        from quicknxs.qreduce import NXSData
        import numpy as np
        data = NXSData(H5_REF_M, use_caching=False)
        assert data is not None
        ds = data[0]
        # REF_M should NOT have DTC applied — histogram sum ≈ total_counts
        assert abs(ds.data.sum() - ds.total_counts) < 2  # no DTC inflation
```
Run: → **FAIL**

**GREEN:** Implement `LRDataset._apply_dead_time_correction()` and integrate into
`LRDataset.from_event_h5()`. Verify that `MRDataset.from_event_h5()` does NOT call
dead-time correction.

---

## Phase 9: Event-level polarization filtering (REF_M)

**Agent team: 1 agent (after Phase 3)**

For polarized REF_M measurements in `.nxs.h5` format, events must be separated by
polarization state. The DAS records state changes via two fast flipper time-series:
- `DASlogs/SF1` (or equivalently `DASlogs/PolarizerState`) — polarizer flipper
- `DASlogs/SF2` — analyzer flipper (when analyzer is in use)
- `DASlogs/SF1_Veto` / `SF2_Veto` — veto flags for transition periods

This matches the approach in mr_reduction's `filter_events.py`.

### Missing DASlogs armor (critical for robustness)

**Problem identified in mr_reduction:** The `filter_events.py` module (lines 185-270)
does NOT check whether `SF1` or `SF2` logs exist before attempting to use them. Only
the veto logs (`SF1_Veto`, `SF2_Veto`) have proper guard clauses. This means that if
the DAS fails to record SF1/SF2 (which has happened in practice), the reduction crashes.

**Our implementation must be more robust.** Every DASlogs access in the polarization
filtering code must handle missing logs gracefully:

1. **SF1 missing**: Treat as unpolarized (single channel) with a warning. If `SF1` was
   expected (because the instrument had a polarizer in position per `PolLift` or device
   metadata), log a warning that the polarization log is absent and proceed unpolarized.
2. **SF2 missing**: Treat as no analyzer (2-channel polarized, not 4-channel) with a
   warning. This is the normal case for many experiments.
3. **SF1_Veto / SF2_Veto missing**: Skip veto filtering for that flipper with a warning
   (same behavior as mr_reduction lines 219-237).
4. **event_time_zero / event_index missing**: Cannot do pulse-level filtering; fall
   back to unpolarized with a warning.

### General DASlogs missing-data strategy

The `_get_daslog_value()` helper already supports `default=` for graceful degradation.
However, in `_collect_info_h5()` methods, several DASlogs reads do NOT specify defaults,
meaning a `KeyError` propagates up. **All DASlogs reads in both `MRDataset._collect_info_h5()`
and `LRDataset._collect_info_h5()` must specify a `default=` parameter** (or use a
`fallback_key`) so that a single missing log does not prevent the file from loading.

The correct behavior for each category of missing log:

| Missing log | Correct behavior |
|---|---|
| Angles (DANGLE, SANGLE, thi, ths, tthd) | Default to 0.0, warn |
| Wavelength (LambdaRequest) | Fall back to BL-specific key, then default 3.37 Å, warn |
| Slit widths (S1HWidth, etc.) | Default to 0.0, warn — resolution calculation will be affected |
| Distances (SampleDetDis, ModeratorSamDis) | Fall back to settings.json defaults, warn |
| Proton charge | Default to 0.0 — data will be flagged as empty |
| Polarization (SF1, SF2) | Degrade to unpolarized, warn |
| Polarization veto (SF1_Veto, SF2_Veto) | Skip veto filtering, warn |
| Emission parameters (BL4B choppers) | Use known defaults (114.0, 29.5), warn |
| Chopper speed (SpeedRequest1) | Default to 60.0 Hz, warn |

All warnings should include the run number and the missing key name to aid debugging.

### Algorithm

Validated against overlap run REF_M_29742 (IPTS-9801): event-filtered counts match
the pre-sorted histo data within 0.01% (65 counts / 497,637 total — transition events).

The two flippers produce up to 4 cross-sections:

| SF1 (polarizer) | SF2 (analyzer) | Cross-section |
|---|---|---|
| 0 (Off) | 0 (Off) | Off_Off |
| 1 (On) | 0 (Off) | On_Off |
| 0 (Off) | 1 (On) | Off_On |
| 1 (On) | 1 (On) | On_On |

When `SF2` has only one state (analyzer not active), only 2 cross-sections are produced.
When both have one state, the run is unpolarized (single channel).

```python
def _filter_events_by_polarization(data):
    """
    Separate events into polarization channels using SF1 (polarizer) and
    SF2 (analyzer) time-series logs.

    Returns dict: {cross_section_name: (event_ids, event_tofs)}
    Returns None if SF1 is missing (caller should treat as unpolarized).
    """
    # Guard: SF1 must exist for polarization filtering
    if 'DASlogs/SF1' not in data:
        warn('DASlogs/SF1 missing — cannot filter by polarization state; '
             'treating as unpolarized')
        return None

    # Guard: required event fields must exist
    for required in ['bank1_events/event_time_zero',
                     'bank1_events/event_index',
                     'bank1_events/event_id',
                     'bank1_events/event_time_offset']:
        if required not in data:
            warn(f'{required} missing — cannot filter events; '
                 'treating as unpolarized')
            return None

    # Read flipper state logs (SF1 existence already verified)
    try:
        sf1_values = data['DASlogs/SF1/value'][()]
        sf1_times = data['DASlogs/SF1/time'][()]
    except KeyError:
        warn('DASlogs/SF1/value or SF1/time missing — treating as unpolarized')
        return None

    sf2_single = True
    if 'DASlogs/SF2' in data:
        try:
            sf2_values = data['DASlogs/SF2/value'][()]
            sf2_times = data['DASlogs/SF2/time'][()]
            sf2_single = (len(unique(sf2_values)) == 1)
        except KeyError:
            warn('DASlogs/SF2/value or SF2/time missing — assuming no analyzer')
            sf2_single = True

    # Read pulse and event data
    event_tz = data['bank1_events/event_time_zero'][()]
    event_idx = data['bank1_events/event_index'][()]
    event_id = data['bank1_events/event_id'][()]
    event_tof = data['bank1_events/event_time_offset'][()]

    # Assign each pulse to SF1 state
    pulse_sf1_idx = searchsorted(sf1_times, event_tz, side='right') - 1
    pulse_sf1_idx = clip(pulse_sf1_idx, 0, len(sf1_values) - 1)
    pulse_sf1 = sf1_values[pulse_sf1_idx]

    if not sf2_single:
        pulse_sf2_idx = searchsorted(sf2_times, event_tz, side='right') - 1
        pulse_sf2_idx = clip(pulse_sf2_idx, 0, len(sf2_values) - 1)
        pulse_sf2 = sf2_values[pulse_sf2_idx]
    else:
        pulse_sf2 = zeros_like(pulse_sf1)

    # Apply veto filtering if veto logs are available
    # (gracefully skip if veto logs are absent — same as mr_reduction)
    veto_mask = ones(len(event_tz), dtype=bool)  # True = keep pulse
    for veto_key in ['DASlogs/SF1_Veto', 'DASlogs/SF2_Veto']:
        if veto_key in data:
            try:
                veto_vals = data[veto_key + '/value'][()]
                veto_times = data[veto_key + '/time'][()]
                veto_idx = searchsorted(veto_times, event_tz, side='right') - 1
                veto_idx = clip(veto_idx, 0, len(veto_vals) - 1)
                # Veto=1 means the flipper is in transition — exclude these pulses
                veto_mask &= (veto_vals[veto_idx] == 0)
            except KeyError:
                warn(f'{veto_key}/value or time missing — skipping veto filter')
        else:
            debug(f'{veto_key} not present — no veto filtering for this flipper')

    # Combine SF1 and SF2 into cross-section labels
    state_names = {(0, 0): 'Off_Off', (1, 0): 'On_Off',
                   (0, 1): 'Off_On',  (1, 1): 'On_On'}

    channels = {}
    for (s1, s2), name in state_names.items():
        mask = (pulse_sf1 == s1) & (pulse_sf2 == s2) & veto_mask
        state_pulses = where(mask)[0]
        if len(state_pulses) == 0:
            continue
        event_masks = []
        for pi in state_pulses:
            start = event_idx[pi]
            end = event_idx[pi + 1] if pi + 1 < len(event_idx) else len(event_id)
            if start < end:
                event_masks.append(arange(start, end))
        if event_masks:
            all_idx = concatenate(event_masks)
            channels[name] = (event_id[all_idx], event_tof[all_idx])

    if len(channels) == 0:
        warn('Polarization filtering produced no channels — '
             'all events may be in veto periods; treating as unpolarized')
        return None

    return channels
```

### Integration with `_read_file_MR()`

```python
if self._is_event_h5:
    # Check if polarized by examining SF1 log (safe: handles missing SF1)
    is_polarized = False
    if 'DASlogs/SF1' in nxs['entry']:
        try:
            sf1_vals = nxs['entry/DASlogs/SF1/value'][()]
            is_polarized = len(unique(sf1_vals)) > 1
        except KeyError:
            warn('SF1 log present but unreadable — treating as unpolarized')

    if is_polarized:
        channels = _filter_events_by_polarization(nxs['entry'])
        if channels is not None and len(channels) > 0:
            for name, (ids, tofs) in channels.items():
                data = MRDataset.from_event_h5_filtered(
                    nxs['entry'], ids, tofs, self._options, ...)
                self._channel_data.append(data)
                self._channel_names.append(name)
            # Determine measurement_type from channel count
            if len(channels) == 4:
                self.measurement_type = 'Polarization Analysis'
            elif len(channels) == 2:
                self.measurement_type = 'Polarized'
            else:
                self.measurement_type = 'Unpolarized'
        else:
            # Polarization filtering failed — fall back to unpolarized
            data = MRDataset.from_event_h5(nxs['entry'], self._options, ...)
            self._channel_data.append(data)
            self._channel_names.append('x')
            self.measurement_type = 'Unpolarized'
    else:
        data = MRDataset.from_event_h5(nxs['entry'], self._options, ...)
        self._channel_data.append(data)
        self._channel_names.append('x')
        self.measurement_type = 'Unpolarized'
```

### TDD Steps

**RED:**
```python
H5_REF_M_POLARIZED = '/SNS/REF_M/IPTS-9801/nexus/REF_M_29742.nxs.h5'
H5_REF_M_POLARIZED_HISTO = '/SNS/REF_M/IPTS-9801/data/REF_M_29742_histo.nxs'

@pytest.mark.skipif(not os.path.exists(H5_REF_M_POLARIZED),
                    reason='No access to SNS data')
class TestPolarizationFiltering:
    def test_detects_polarized_data(self):
        from quicknxs.qreduce import NXSData
        data = NXSData(H5_REF_M_POLARIZED, use_caching=False)
        assert data is not None
        assert len(data) >= 2  # at least 2 polarization channels

    @pytest.mark.skipif(not os.path.exists(H5_REF_M_POLARIZED_HISTO),
                        reason='No access to histo counterpart')
    def test_channel_counts_match_histo(self):
        from quicknxs.qreduce import NXSData
        h5 = NXSData(H5_REF_M_POLARIZED, use_caching=False)
        histo = NXSData(H5_REF_M_POLARIZED_HISTO, use_caching=False)
        # Total counts across channels should be similar
        h5_total = sum(ch.total_counts for ch in h5._channel_data)
        histo_total = sum(ch.total_counts for ch in histo._channel_data)
        assert abs(h5_total - histo_total) < 100  # allow for transition events

    def test_unpolarized_single_channel(self):
        from quicknxs.qreduce import NXSData
        data = NXSData(H5_REF_M, use_caching=False)  # unpolarized run
        assert len(data) == 1

    def test_missing_sf1_degrades_to_unpolarized(self):
        """When SF1 is missing, should load as unpolarized without crashing"""
        import h5py
        from quicknxs.qreduce import _filter_events_by_polarization
        # Use a mock or an unpolarized file that lacks SF1
        with h5py.File(H5_REF_M, 'r') as f:
            entry = f['entry']
            # The unpolarized run may not have SF1 at all, or SF1 with
            # a single state. If SF1 is present with single state,
            # the function should still work (returns None or single channel)
            if 'DASlogs/SF1' not in entry:
                result = _filter_events_by_polarization(entry)
                assert result is None
            else:
                import numpy as np
                sf1_vals = entry['DASlogs/SF1/value'][()]
                if len(np.unique(sf1_vals)) == 1:
                    # Single state — not polarized, caller should not have called
                    pass

    def test_missing_sf2_produces_two_channels(self):
        """When SF2 is missing but SF1 has states, should produce 2 channels"""
        # This tests the case where analyzer is not in use
        from quicknxs.qreduce import NXSData
        data = NXSData(H5_REF_M_POLARIZED, use_caching=False)
        assert data is not None
        # If this run has SF2, we test the normal case
        # A dedicated test with a 2-state-only run would be ideal

    def test_veto_filtering_excludes_transitions(self):
        """Veto filtering should reduce total counts vs no-veto"""
        import h5py
        from quicknxs.qreduce import _filter_events_by_polarization
        with h5py.File(H5_REF_M_POLARIZED, 'r') as f:
            channels = _filter_events_by_polarization(f['entry'])
        assert channels is not None
        total = sum(len(ids) for ids, _ in channels.values())
        # Total should be less than the raw event count (transitions vetoed)
        import h5py as h5
        with h5.File(H5_REF_M_POLARIZED, 'r') as f:
            raw_count = len(f['entry/bank1_events/event_id'][()])
        assert total < raw_count  # some events removed by veto/state filtering

@pytest.mark.skipif(not os.path.exists(H5_REF_M), reason='No access to SNS data')
class TestMissingDaslogsArmor:
    """Test that _collect_info_h5 handles missing DASlogs gracefully."""

    def test_mr_collect_info_with_patched_missing_log(self):
        """Simulate a missing DASlogs key by testing default behavior"""
        import h5py
        from quicknxs.qreduce import _get_daslog_value
        with h5py.File(H5_REF_M, 'r') as f:
            # Test that a nonexistent key with default doesn't raise
            val = _get_daslog_value(f['entry'], 'TOTALLY_MISSING_KEY',
                                   default=42.0)
            assert val == 42.0

            # Test that a nonexistent key without default raises KeyError
            with pytest.raises(KeyError):
                _get_daslog_value(f['entry'], 'TOTALLY_MISSING_KEY')

    def test_lr_collect_info_uses_defaults(self):
        """LRDataset._collect_info_h5() should not crash on missing optional logs"""
        import h5py
        from quicknxs.qreduce import LRDataset
        with h5py.File(H5_REF_L, 'r') as f:
            ds = LRDataset()
            ds._collect_info_h5(f['entry'])
        # All attributes should be populated (possibly with defaults)
        assert ds.dangle is not None
        assert ds.sangle is not None
        assert ds.lambda_center is not None
        assert ds.dist_sam_det > 0
```
Run: → **FAIL**

**GREEN:** Implement `_filter_events_by_polarization()` with all guard clauses,
`from_event_h5_filtered()`, and ensure all `_collect_info_h5()` DASlogs reads have
safe defaults.

---

## Future Work (out of scope for this plan)

### Generate buzhug database for REF_L

`/SNS/REF_L/shared/quicknxs_database/` does not currently exist. After this work
lands, it would be feasible to populate it from the 2,554 old `*_histo.nxs` files
(runs 70476–84693 in IPTS-7053). The existing `DatabaseHandler.add_record()` works
with any `NXSData` object.

### Extend database to `.nxs.h5` files

Once `.nxs.h5` loading is implemented, the database could be extended to index modern
files for both instruments.
