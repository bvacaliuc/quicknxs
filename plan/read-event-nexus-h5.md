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

| Property | REF_M (.nxs.h5) | REF_L (.nxs.h5) |
|---|---|---|
| Beamline | BL4A | BL4B |
| Detector pixels | xpixels=304, ypixels=256 | xpixels=256, ypixels=304 |
| Angles | `DASlogs/DANGLE`, `DASlogs/SANGLE` | `DASlogs/thi`, `DASlogs/ths` |
| Wavelength | `DASlogs/LambdaRequest` (MISSING) | `DASlogs/LambdaRequest` |
| Slit widths | `DASlogs/S1HWidth` etc. | `DASlogs/SiHWidth`, `DASlogs/SiVHeight` |
| Sample-det dist | `DASlogs/SampleDetDis` or `DASlogs/BL4A:Mot:SampleDetDis` | From instrument XML (fixed at 1.362 m for current IDF) |
| Moderator dist | `DASlogs/BL4A:Mot:ModeratorSamDis` (18703 mm) | From instrument XML (13.685 m) |
| DIRPIX | `DASlogs/BL4A:Mot:DIRPIX` | Not applicable |
| DANGLE0 | `DASlogs/BL4A:Mot:DANGLE0` | Not applicable |

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
    All metadata comes from DASlogs rather than structured instrument paths.
    """
    self.origin = (os.path.abspath(data.file.filename), data.name.lstrip('/'))
    self.logs = NiceDict()
    self.log_minmax = NiceDict()
    self.log_units = NiceDict()

    # Read DASlogs (same loop as existing _collect_info)
    if 'DASlogs' in data:
        # ... same DASlogs iteration as existing code ...
        pass

    # REF_M angles from DASlogs
    self.dangle = _get_daslog_value(data, 'DANGLE')
    self.dangle0 = _get_daslog_value(data, 'BL4A:Mot:DANGLE0', default=0.0)
    self.sangle = _get_daslog_value(data, 'SANGLE')
    self.dpix = _get_daslog_value(data, 'BL4A:Mot:DIRPIX', default=150)

    # Wavelength — try multiple DASlogs keys; early commissioning files lack all of them
    self.lambda_center = _get_daslog_value(data, 'LambdaRequest',
                             fallback_key='BL4A:Det:TH:BL:Lambda',
                             default=3.37)
    # Note: if lambda_center falls back to default, warn so user knows ToF binning may be wrong

    # Slit widths from DASlogs
    self.slit1_width = _get_daslog_value(data, 'S1HWidth', default=3.0)
    self.slit2_width = _get_daslog_value(data, 'S2HWidth', default=2.0)
    self.slit3_width = _get_daslog_value(data, 'S3HWidth', default=0.05)

    # Distances — different source than old format
    sdd_mm = _get_daslog_value(data, 'SampleDetDis',
                 fallback_key='BL4A:Mot:SampleDetDis', default=2555.05)
    self.dist_sam_det = sdd_mm * 1e-3

    mod_sam_mm = _get_daslog_value(data, 'BL4A:Mot:ModeratorSamDis', default=18703.0)
    self.dist_mod_det = mod_sam_mm * 1e-3 + self.dist_sam_det
    self.dist_mod_mon = mod_sam_mm * 1e-3 - 2.75

    # Detector size from instrument XML
    n_x, n_y = _get_detector_dimensions(data)
    pixel_size = 0.0007  # 0.7 mm per pixel
    self.det_size_x = n_x * pixel_size
    self.det_size_y = n_y * pixel_size

    # Standard metadata
    self.proton_charge = data['proton_charge'][()][0]
    self.total_counts = data['total_counts'][()][0]
    self.total_time = data['duration'][()][0]
    self.experiment = _decode(data['experiment_identifier'][()][0])
    self.number = int(data['run_number'][()][0])
    self.merge_warnings = ''

    # Slit distances — use known REF_M values as defaults
    self.slit1_dist = 2600.0
    self.slit2_dist = 2019.0
    self.slit3_dist = 714.0
```

### Change 4: New `_collect_info_h5()` method on LRDataset

**File:** `quicknxs/qreduce.py`
**Class:** `LRDataset`

Similar to Change 3 but with REF_L-specific DASlogs paths.

```python
def _collect_info_h5(self, data):
    """
    Extract header information from a modern .nxs.h5 REF_L file.
    """
    self.origin = (os.path.abspath(data.file.filename), data.name.lstrip('/'))
    self.logs = NiceDict()
    self.log_minmax = NiceDict()
    self.log_units = NiceDict()

    if 'DASlogs' in data:
        # ... same DASlogs iteration ...
        pass

    # REF_L angles: thi → dangle, ths → sangle
    self.dangle = _get_daslog_value(data, 'thi', default=0.0)
    self.dangle0 = 0.0
    self.sangle = _get_daslog_value(data, 'ths', default=0.0)
    self.dpix = 151  # default for REF_L

    # Wavelength
    self.lambda_center = _get_daslog_value(data, 'LambdaRequest', default=6.2)

    # REF_L slit widths from DASlogs
    self.slit1_width = _get_daslog_value(data, 'SiHWidth',
                           fallback_key='BL4B:Mot:si:X:Gap:Readback', default=20.0)
    self.slit2_width = _get_daslog_value(data, 'SiVHeight',
                           fallback_key='BL4B:Mot:si:Y:Gap:Readback', default=1.2)
    self.slit3_width = 0.05  # REF_L default

    # Distances from instrument XML (fixed geometry)
    self.dist_sam_det = 1.362  # from instrument XML detector1 z
    self.dist_mod_det = 13.685 + self.dist_sam_det  # moderator z + sample-det
    self.dist_mod_mon = self.dist_mod_det - 2.75

    # Detector size
    n_x, n_y = _get_detector_dimensions(data)
    pixel_size = 0.0007
    self.det_size_x = n_x * pixel_size
    self.det_size_y = n_y * pixel_size

    self.proton_charge = data['proton_charge'][()][0]
    self.total_counts = data['total_counts'][()][0]
    self.total_time = data['duration'][()][0]
    self.experiment = _decode(data['experiment_identifier'][()][0])
    self.number = int(data['run_number'][()][0])
    self.merge_warnings = ''

    self.slit1_dist = 2600.0
    self.slit2_dist = 2019.0
    self.slit3_dist = 714.0
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
    """
    for k in [key, fallback_key]:
        if k is None:
            continue
        try:
            item = data['DASlogs/' + k]
            if 'average_value' in item:
                return float(item['average_value'][0])
            elif 'value' in item:
                val = item['value'][()]
                if val.size == 1:
                    return float(val[0])
                else:
                    return float(val.mean())
        except (KeyError, IndexError, ValueError):
            continue
    if default is not None:
        return default
    raise KeyError(f'DASlogs key {key} not found')


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
        assert abs(ds.dangle - (-0.007)) < 0.01  # thi
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
| Polarization states lost in .nxs.h5 format | `locate_file()` prefers `_histo.nxs` when available (preserves polarization); `.nxs.h5` loaded as unpolarized; event-level polarization filtering deferred to Phase 8 (future work) |
| Dead-time correction not applied | lr_reduction applies it but quicknxsv1 doesn't for _event.nxs either; defer to future work |
| Slit distances not in new format | Use known instrument constants (stable geometry) |
| Memory pressure from large event arrays | Events are discarded after binning; 3D histogram is same size as legacy |
| event_id pixel mapping varies by IDF version | Parse instrument XML dynamically; fall back to known constants |

## File Impact Summary

| File | Type of Change |
|---|---|
| `quicknxs/qreduce.py` | Major: new methods, format detection, helpers |
| `quicknxs/config/ref_m.py` | Minor: add `H5_BASE_SEARCH` |
| `quicknxs/config/ref_l.py` | Minor: add `H5_BASE_SEARCH` |
| `tests/` (new test file) | New: integration tests for .nxs.h5 loading |
| `Makefile` | Minor: add test targets |

## Data Files for Testing

| File | Instrument | Format | Events | Purpose |
|---|---|---|---|---|
| `/SNS/REF_M/IPTS-9801/nexus/REF_M_29750.nxs.h5` | REF_M | .nxs.h5 | 19,195 | **Primary**: unpolarized, full metadata, has histo counterpart |
| `/SNS/REF_M/IPTS-9801/data/REF_M_29750_histo.nxs` | REF_M | histo | 19,166 | Reference for validating event-to-histo conversion |
| `/SNS/REF_M/IPTS-9801/nexus/REF_M_29742.nxs.h5` | REF_M | .nxs.h5 | 497,637 | Polarized run (3 states), has histo counterpart |
| `/SNS/REF_M/IPTS-9801/data/REF_M_29742_histo.nxs` | REF_M | histo | 497,635 | Reference: Off_Off(234k) + On_Off(263k) + unfiltered(63) |
| `/SNS/REF_M/IPTS-24338/nexus/REF_M_43568.nxs.h5` | REF_M | .nxs.h5 | 2,113,831 | High-count h5-only run (no histo), full metadata |
| `/SNS/REF_L/IPTS-36119/nexus/REF_L_220030.nxs.h5` | REF_L | .nxs.h5 | 85,387 | REF_L event loading |
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

## Future Work (out of scope for this plan)

### Generate buzhug database for REF_L

`/SNS/REF_L/shared/quicknxs_database/` does not currently exist. After this work
lands, it would be feasible to populate it from the 2,554 old `*_histo.nxs` files
(runs 70476–84693 in IPTS-7053). The existing `DatabaseHandler.add_record()` works
with any `NXSData` object:

```python
from quicknxs.database import DatabaseHandler
db = DatabaseHandler()
for run in range(70476, 84694):
    db.add_record(run)
```

This would enable the GUI's "Find Direct Beam" feature to work with REF_L data.

### Extend database to `.nxs.h5` files

Once `.nxs.h5` loading is implemented, the database could be extended to index modern
files. The format transition is clean (no overlap): REF_M histo ends at run 28832,
`.nxs.h5` starts at 29001. Both formats could coexist in the same database since
`add_record()` stores `file_path` which preserves the format distinction.

### Phase 8: Event-level polarization filtering for `.nxs.h5`

For polarized REF_M measurements in `.nxs.h5` format, events must be separated by
polarization state using the `DASlogs/PolarizerState` time-series. The approach:

1. Read `PolarizerState` values and timestamps from DASlogs
2. Read `bank1_events/event_time_zero` (pulse times) and `event_index` (event-to-pulse mapping)
3. For each event, determine which polarization state was active at that pulse time
4. Bin events separately per polarization state → separate MRDataset objects

This mirrors what the DAS histogramming does to produce the `entry-Off_Off` etc.
channels in `_histo.nxs` files. The `PolarizerState` log has ~188 entries per run
(state changes every ~few hundred pulses), so the time-correlation is efficient.

**Validation strategy**: Use the 70 overlapping runs in IPTS-9801 (29732–29801) that
have both polarized `_histo.nxs` and `.nxs.h5` files. Compare per-channel histograms
from event filtering against the pre-sorted histo data.

### Dead-time correction

The lr_reduction `binary_processing.py` applies a dead-time correction using the
Lambert W function on `bank_error_events`. quicknxsv1 does not apply dead-time
correction for existing event files either, so this is deferred. However, adding it
would improve accuracy for high-count-rate measurements.
