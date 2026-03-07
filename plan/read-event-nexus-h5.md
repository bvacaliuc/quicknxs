# Plan: Read Modern Event NeXus (.nxs.h5) Files in quicknxsv1

## Executive Summary

Upgrade quicknxsv1 to read the modern `*.nxs.h5` event-mode NeXus files (used since
~2018) in addition to the legacy `*_histo.nxs` format. Both REF_M (beamline 4A) and
REF_L (beamline 4B) instruments must be supported. The approach converts events into
the same 3D histogram `(x, y, tof)` that the existing code expects, so no downstream
changes to reduction, plotting, or export are required.

## Background

### Legacy format (`*_histo.nxs`)
- Pre-histogrammed 3D data at `bank1/data` with shape `(n_x, n_y, n_tof)`
- Projected 2D views: `data_x_y`, `data_x_time_of_flight`, `data_y_time_of_flight`
- Metadata at structured instrument paths (`instrument/bank1/DANGLE/value`, etc.)
- REF_M: multiple entries for polarization states (Off_Off, On_On, etc.)
- REF_L: single `entry/` (unpolarized)

### Modern format (`*.nxs.h5`)
- Raw events only: `bank1_events/event_id` + `event_time_offset` (both large arrays)
- Definition field: `NXsnsevent`
- **No pre-histogrammed data** — events must be binned into x/y/tof histograms
- **No structured instrument paths** — all metadata lives in `DASlogs/` with
  beamline-prefixed keys (e.g., `DASlogs/DANGLE/average_value`)
- Single `entry/` only — even for REF_M polarization (no separate Off_Off entries)
- Pixel ordering: `idfillbyfirst="y"` → `event_id = x_pixel * n_y + y_pixel`

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

```python
def locate_file(number, histogram=True, old_format=False, verbose=True):
    if verbose:
        info('Trying to locate file number %s...' % number)

    # Try legacy formats first (preferred for backward compatibility)
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

## Implementation Phases

### Phase 1: Core event reading (Changes 1-5)
**Agent team: 1 primary agent**

1. Add `_get_detector_dimensions()`, `_get_daslog_value()`, `_decode()` helpers
2. Add `MRDataset._collect_info_h5()` for REF_M
3. Add `LRDataset._collect_info_h5()` for REF_L
4. Add `MRDataset.from_event_h5()` class method
5. Add `LRDataset.from_event_h5()` class method (override if needed, or inherit)
6. Add format detection (`_is_event_h5`) in `_read_file()`
7. Route to `from_event_h5()` in `_read_file_MR()` and `_read_file_LR()`

**Tests:**
- Unit test: `_get_detector_dimensions()` with real `.nxs.h5` file
- Unit test: `_get_daslog_value()` with real `.nxs.h5` file
- Integration test: `NXSData('/SNS/REF_M/IPTS-16196/nexus/REF_M_29015.nxs.h5')` returns valid data
- Integration test: `NXSData('/SNS/REF_L/IPTS-36119/nexus/REF_L_220030.nxs.h5')` returns valid data
- Verify: `data.shape == (n_x, n_y, n_tof)` matches expectations
- Verify: `xydata`, `xtofdata` projections are correct
- Verify: metadata (angles, distances, proton charge) is correct

### Phase 2: File search and routing (Changes 6-9)
**Agent team: 1 agent (can run in parallel with Phase 1 tests)**

1. Update `locate_file()` to find `.nxs.h5` files
2. Add `H5_BASE_SEARCH` to config files
3. Update `_read_file_MR()` and `_read_file_LR()` channel detection
4. Fix `time_from_header()` for robustness

**Tests:**
- `locate_file(29015)` with REF_M instrument → finds `.nxs.h5`
- `locate_file(220030)` with REF_L instrument → finds `.nxs.h5`
- `locate_file(25899)` with REF_M instrument → still finds legacy `_histo.nxs`

### Phase 3: Event splitting support
**Agent team: 1 agent**

Port the `event_split_bins`/`event_split_index` logic from existing `from_event()`
to `from_event_h5()`. The event splitting data lives at the same paths in both
formats (`bank1_events/event_time_zero`, `bank1_events/event_index`).

**Tests:**
- Load with `event_split_bins=4, event_split_index=0` — verify subset
- Verify total counts across all splits sums to unsplit total

### Phase 4: Backward compatibility verification
**Agent team: 1 agent**

Run the full existing test suite to verify no regressions:
- `make test` passes
- Legacy `_histo.nxs` files still load correctly
- Legacy `_event.nxs` files still load correctly
- GUI can open both old and new files

### Phase 5: Makefile integration and documentation
**Agent team: 1 agent**

1. Add Makefile targets for testing with `.nxs.h5` files:
   ```makefile
   test-h5-load:  ## Load test with modern .nxs.h5 files
       pixi run python -c "from quicknxs.qreduce import NXSData; ..."
   ```
2. Update CLAUDE.md with new format documentation
3. Commit all changes

---

## Risk Analysis

| Risk | Mitigation |
|---|---|
| REF_M .nxs.h5 files have no LambdaRequest in DASlogs | Fall back to `BL4A:Det:TH:BL:Lambda`, then `BL4A:Chop:Gbl:Wavelength:Req`; early 2018 commissioning files (runs 29xxx) have NO wavelength/chopper data at all — use default 3.37 Å and warn |
| Polarization states lost in .nxs.h5 format | Document limitation; .nxs.h5 is treated as unpolarized |
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
| `/SNS/REF_M/IPTS-16196/nexus/REF_M_29015.nxs.h5` | REF_M | .nxs.h5 | 14,863 | REF_M event loading |
| `/SNS/REF_L/IPTS-36119/nexus/REF_L_220030.nxs.h5` | REF_L | .nxs.h5 | 85,387 | REF_L event loading |
| `/SNS/REF_M/IPTS-16196/0/25899/NeXus/REF_M_25899_histo.nxs` | REF_M | histo | N/A | Backward compat |
| `/SNS/REF_L/IPTS-7053/0/80836/NeXus/REF_L_80836_histo.nxs` | REF_L | histo | N/A | Backward compat |
| `/SNS/REF_M/IPTS-16196/nexus/REF_M_45600.nxs.h5` | REF_M | .nxs.h5 | 0 | REF_M with full metadata (LambdaRequest present) |

### Note on test data quality

- REF_M runs 29001-29016 are from early 2018 commissioning and **lack wavelength/chopper
  DASlogs entirely**. Run 29015 has 14,863 events but no LambdaRequest. These files will
  use default wavelength (3.37 Å) for TOF binning.
- REF_M runs 45593+ have full metadata including LambdaRequest, chopper speed, etc.
- REF_L runs 220030+ have full metadata.
- For production testing, prefer runs with full metadata. The early commissioning files
  are useful for testing graceful degradation only.
