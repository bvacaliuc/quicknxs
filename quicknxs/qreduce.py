#-*- coding: utf-8 -*-
'''
Module for data readout and evaluation of the SNS Magnetism Reflectometer.
Can also be used stand alone for e.g. interactive processing
or scripts, therefore it is kept as only one file. The only dependencies
are numpy and the h5py module, which is an interface to the HDF5 file format
C-library, on which Nexus files are based.

The NXSData object reads a full .nxs file (histogram and event mode) and analysis
it's content for the channels that have been measured. It can be use as a list
or dictionary to access these channels as MRDataset objects.

The Relflectivity extracts a reflectiviy from a MRDataset object and
storing the result as well as some intermediate data in itself as attributes.
'''

import os
import zlib
import h5py
import base64
import traceback
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor, as_completed
from glob import glob
import builtins as _builtins
from numpy import *
from numpy.version import version as npversion
from platform import node
from time import time, strptime, mktime
from xml.dom import minidom
# ignore zero devision error
#seterr(invalid='ignore')

from logging import debug, info, warning as warn #@Reimport
from .config import instrument
from .decorators import log_call, log_input, log_both
from .ipython_tools import AttributePloter, StringRepr, NiceDict

### Parameters needed for some calculations.
H_OVER_M_NEUTRON=3.956034e-7 # h/m_n [m²/s]
DETECTOR_SENSITIVITY={}
# Reference SNS source pulse frequency (Hz). The wavelength bandwidth scales
# inversely with chopper speed: at half the chopper speed the frame period
# doubles and so does the usable bandwidth.
TOF_REFERENCE_FREQUENCY=60.0
# Default half-bandwidth (Å) around the central wavelength at the reference
# chopper speed.  Matches quicknxsv2's ``wl_bandwidth = 3.2 → half_width = 1.6``.
TOF_HALF_BANDWIDTH_60HZ=1.6
# Mantid's MagnetismReflectometryReduction (``get_tof_range``) crops to a
# *narrower* half-bandwidth (1.4 Å at 60 Hz) than v1's load band (1.6).  The
# off-spec normalization is cropped to this tighter, Mantid-matching band so the
# poorly-illuminated band edges -- where a single-count direct beam makes the
# 1/flux normalization blow up a spurious off-spec pixel -- are excluded.
MANTID_OFFSPEC_HALF_BANDWIDTH=1.4


def _compute_tof_range_us(dist_mod_det, lambda_center, chopper_speed=None,
                          half_bandwidth=TOF_HALF_BANDWIDTH_60HZ):
  '''Return the (tmin, tmax) time-of-flight window in microseconds.

  The neutron bandwidth at SNS is set by the chopper frequency.  At the
  reference frequency (60 Hz) the half-bandwidth around ``lambda_center`` is
  ``half_bandwidth`` Å.  Slower chopper speeds widen the bandwidth in inverse
  proportion (e.g. at 30 Hz the half-bandwidth doubles).  This mirrors the
  formula used by quicknxsv2 (``data_info.py:99``).
  '''
  if chopper_speed is None or chopper_speed <= 0:
    chopper_speed = TOF_REFERENCE_FREQUENCY
  scale = TOF_REFERENCE_FREQUENCY / float(chopper_speed)
  hb = half_bandwidth * scale
  tmin = dist_mod_det / H_OVER_M_NEUTRON * (lambda_center - hb) * 1e-4
  tmax = dist_mod_det / H_OVER_M_NEUTRON * (lambda_center + hb) * 1e-4
  return tmin, tmax


def _log_scalar(val):
  '''Return a scalar from a possibly multi-dimensional numpy array.

  DAS logs in modern ``.nxs.h5`` files occasionally store single-valued items
  as ``shape (1, 1)`` arrays (notably sample-environment strings).  Indexing
  with ``val[0]`` then yields a 1-D one-element array which cannot be used
  with ``%g`` formatting (it raises ``TypeError: only 0-dimensional arrays
  can be converted to Python scalars``).  ``.flat[0]`` always returns a true
  scalar regardless of the original shape.
  '''
  return val.flat[0]

# REF_M-specific constants (ANALYZER_IN, NEW_ANALYZER_IN, POLARIZER_IN,
# SUPERMIRROR_IN, POLY_CORR_PARAMS) live in config/ref_m.py and are
# accessed at point-of-use via the instrument config object.

def _get_instrument_config(name, default=None):
  '''Safely read an instrument config constant, returning default if missing.

  ConfigHolder raises KeyError (not AttributeError) for missing keys,
  so getattr()'s default parameter does not work. This helper catches both.
  '''
  try:
    return instrument[name]
  except KeyError:
    return default
# measurement type mapping of states
MAPPING_12FULL=(
                 (u'++ (0V)', u'entry-off_off_Ezero'),
                 (u'-- (0V)', u'entry-on_on_Ezero'),
                 (u'+- (0V)', u'entry-off_on_Ezero'),
                 (u'-+ (0V)', u'entry-on_off_Ezero'),
                 (u'++ (+V)', u'entry-off_off_Eplus'),
                 (u'-- (+V)', u'entry-on_on_Eplus'),
                 (u'+- (+V)', u'entry-off_on_Eplus'),
                 (u'-+ (+V)', u'entry-on_off_Eplus'),
                 (u'++ (-V)', u'entry-off_off_Eminus'),
                 (u'-- (-V)', u'entry-on_on_Eminus'),
                 (u'+- (-V)', u'entry-off_on_Eminus'),
                 (u'-+ (-V)', u'entry-on_off_Eminus'),
                 )
MAPPING_12HALF=(
                 (u'+ (0V)', u'entry-off_off_Ezero'),
                 (u'- (0V)', u'entry-on_off_Ezero'),
                 (u'+ (+V)', u'entry-off_off_Eplus'),
                 (u'- (+V)', u'entry-on_off_Eplus'),
                 (u'+ (-V)', u'entry-off_off_Eminus'),
                 (u'- (-V)', u'entry-on_off_Eminus'),
                 )
MAPPING_FULLPOL=(
                 (u'++', u'entry-Off_Off'),
                 (u'--', u'entry-On_On'),
                 (u'+-', u'entry-Off_On'),
                 (u'-+', u'entry-On_Off'),
                 )
MAPPING_HALFPOL=(
                 (u'+', u'entry-Off_Off'),
                 (u'-', u'entry-On_Off'),
                 )
MAPPING_UNPOL=(
               (u'x', u'entry-Off_Off'),
               )
MAPPING_EFIELD=(
                (u'0V', u'entry-Off_Off'),
                (u'+V', u'entry-On_Off'),
                (u'-V', u'entry-Off_On'),
                )

# don't save RAM by compression when on analysis cluster or mrac computer as they have plenty
USE_COMPRESSION=not ('biganalysis' in node() or 'mrac' in node())

# used for * imports
__all__=['NXSData', 'MRDataset', 'LRDataset', 'Reflectivity', 'OffSpecular', 'GISANS',
         'time_from_header', 'locate_file',
         '_get_detector_dimensions', '_get_daslog_value',
         '_read_instrument_settings', '_decode']

_bincount=bincount
def bincount(x, weights=None, minlength=None):
  if len(x)==0:
    if minlength:
      return zeros(minlength, dtype=int)
    else:
      return array([0], dtype=int)
  if npversion<'1.6.0':
    bins=_bincount(x, weights=weights)
    if minlength and len(bins)<minlength:
      bins.resize(minlength)
    return bins
  else:
    return _bincount(x, weights, minlength)

def _decode(value):
  """Decode bytes to string if needed."""
  if isinstance(value, bytes):
    return value.decode('utf-8')
  return str(value)


def _get_detector_dimensions(data):
  """
  Get detector pixel dimensions (n_x, n_y) from instrument XML in the file.
  Falls back to known defaults by instrument name.

  :param data: HDF5 group (entry) containing instrument XML
  :returns: tuple (n_x, n_y)
  """
  import re
  try:
    xml_raw=data['instrument/instrument_xml/data'][()][0]
    xml=xml_raw.decode('utf-8') if isinstance(xml_raw, bytes) else str(xml_raw)
    xp=re.search(r'xpixels="(\d+)"', xml)
    yp=re.search(r'ypixels="(\d+)"', xml)
    if xp and yp:
      return int(xp.group(1)), int(yp.group(1))
  except (KeyError, IndexError):
    pass

  # Fallback: detect from instrument name
  try:
    name_raw=data['instrument/name'][()][0]
    name=name_raw.decode('utf-8') if isinstance(name_raw, bytes) else str(name_raw)
    if name=='REF_L':
      return (256, 304)
    else:
      return (304, 256)
  except KeyError:
    return (304, 256)  # default to REF_M


_DASLOG_NO_DEFAULT=object()  # sentinel for "no default provided"

def _get_daslog_value(data, key, fallback_key=None, default=_DASLOG_NO_DEFAULT):
  """
  Read a value from DASlogs, trying average_value first, then value.
  Falls back to fallback_key if primary key is not found.

  :param data: HDF5 group (entry)
  :param key: primary DASlogs key name
  :param fallback_key: alternative key to try if primary is missing
  :param default: value to return if all keys fail (sentinel = raise KeyError)
  :returns: float value
  """
  for k in [key, fallback_key]:
    if k is None:
      continue
    try:
      item=data['DASlogs/'+k]
      if 'average_value' in item:
        val=float(item['average_value'][()][0])
        if k!=key:
          debug('DASlogs/%s missing, using fallback %s=%s'%(key, k, val))
        return val
      elif 'value' in item:
        arr=item['value'][()]
        if arr.size==0:
          continue  # empty array — try fallback
        val=float(arr[0]) if arr.size==1 else float(arr.mean())
        if k!=key:
          debug('DASlogs/%s missing, using fallback %s=%s'%(key, k, val))
        return val
    except (KeyError, IndexError, ValueError):
      continue
  if default is not _DASLOG_NO_DEFAULT:
    if default is not None:
      try:
        run=int(data['run_number'][()][0])
        warn('Run %s: DASlogs/%s not found, using default=%s'%(run, key, default))
      except (KeyError, IndexError):
        warn('DASlogs/%s not found, using default=%s'%(key, default))
    return default
  raise KeyError('DASlogs key %s not found'%key)


def _read_instrument_settings(instrument_name, data):
  """
  Read date-indexed instrument settings from settings.json.
  Uses the run's start_time to select the applicable configuration.

  :param instrument_name: 'ref_l' or 'ref_m'
  :param data: HDF5 group (entry) to read start_time from
  :returns: dict of instrument settings for the measurement date
  """
  import json
  import datetime as _datetime

  # Get measurement date from file
  start_time_raw=data['start_time'][()][0]
  start_time=start_time_raw.decode('utf-8') if isinstance(start_time_raw, bytes) else str(start_time_raw)
  # Parse date portion only (handle timezone offsets like -04:00)
  date_str=start_time.split('T')[0]
  timestamp=_datetime.date.fromisoformat(date_str)

  # Load settings file (co-located with config module)
  package_dir=os.path.dirname(os.path.abspath(__file__))
  settings_path=os.path.join(package_dir, 'config', '%s_settings.json'%instrument_name)

  settings_dict={}
  with open(settings_path, 'r') as fd:
    json_data=json.load(fd)
    for key in json_data:
      chosen_value=None
      chosen_from=None
      for item in json_data[key]:
        valid_from=_datetime.date.fromisoformat(item['from'])
        if valid_from<=timestamp:
          if chosen_from is None or valid_from>chosen_from:
            chosen_from=valid_from
            chosen_value=item['value']
      settings_dict[key]=chosen_value

  return settings_dict


class OptionsDocMeta(type):
  '''
  Metaclass to update docstring to dynamically include keyword arguments
  '''

  def __new__(cls, name, bases, dct):
    import builtins as _builtins
    _max = _builtins.max
    # overwrite the docstring
    docstring=dct['__doc__']
    docstring+='''
  The generator takes several keyword arguments to control the readout:'''
    opt_desc={}
    if 'DEFAULT_OPTIONS' in dct:
      opts=dct['DEFAULT_OPTIONS']
      if '_OPTIONS_DESCRTIPTION' in dct:
        opt_desc=dct['_OPTIONS_DESCRTIPTION']
    else:
      for base in bases:
        if hasattr(base, 'DEFAULT_OPTIONS'):
          opts=base.DEFAULT_OPTIONS
          if hasattr(base, '_OPTIONS_DESCRTIPTION'):
            opt_desc=base._OPTIONS_DESCRTIPTION
          break
    maxlen_key=3
    maxlen_val=7
    for key, value in sorted(opts.items()):
      maxlen_key=_max(maxlen_key, len("%s"%key))
      maxlen_val=_max(maxlen_val, len("%s"%value))
    maxlen_desc=80-maxlen_key-maxlen_val
    docline='\n      %%-%is  %%-%is  %%-%is'%(maxlen_key, maxlen_val, maxlen_desc)
    docstring+=docline%('='*maxlen_key, '='*maxlen_val, '='*maxlen_desc)
    docstring+=docline%('Key', 'Default', 'Description')
    docstring+=docline%('='*maxlen_key, '='*maxlen_val, '='*maxlen_desc)
    for key, value in sorted(opts.items()):
      desc=['']
      if key in opt_desc:
        desc=OptionsDocMeta.format_description(opt_desc[key], maxlen_desc)
      docstring+=docline%(key, value, desc[0])
      for desci in desc[1:]:
        docstring+=docline%('', '', desci)
    docstring+=docline%('='*maxlen_key, '='*maxlen_val, '='*maxlen_desc)+'\n      '
    dct['__doc__']=docstring

    return super(OptionsDocMeta, cls).__new__(cls, name, bases, dct)

  @staticmethod
  def format_description(description, maxlen):
    output=[description]
    while len(output[-1])>maxlen:
      lastitem=output.pop(-1)
      splitidx=lastitem[:maxlen].rfind(' ')
      output.append(lastitem[:splitidx])
      output.append(lastitem[splitidx+1:])
    return output


class NXSData(object, metaclass=OptionsDocMeta):
  '''
  Class for readout and evaluation of histogram and event mode .nxs files,
  which also stores the data to be accessed by attributes.

  The object can be used as a ordered dictionary or list of channels,
  where each channel is a MRDataset object.
  '''

  DEFAULT_OPTIONS=dict(bin_type=0, bins=40, use_caching=True, callback=None,
                       event_split_bins=None, event_split_index=0,
                       event_tof_overwrite=None)
  _OPTIONS_DESCRTIPTION=dict(
    bin_type="linear in ToF'/'1: linear in Q' - use linear or 1/x spacing for ToF channels in event mode",
    bins='Number of ToF bins for event mode',
    use_caching='If files should be cached for faster future readouts (last 20 files)',
    event_split_bins='Number of items, to split the events in time or None for no splitting',
    event_split_index='Index of the splitted item to be returned, when event_split_bin is not None',
    event_tof_overwrite='Optional array of ToF edges to be used instead of the ones created from bins and bin_type',
    callback='Function called to update e.g. a progress bar',
    )
  COUNT_THREASHOLD=0.01 #: Relative number of counts needed for a state to be interpreted as actual data
  MAX_CACHE=100 #: Number of datasets that are kept in the cache
  _cache=[]

  @log_both
  def __new__(cls, filename, **options):
    if type(filename) is int:
      fn=locate_file(filename)
      if fn is None:
        raise RuntimeError('No file found for index %i'%filename)
      filename=fn
    if filename.endswith('.xml') and cls is not XMLData:
      return XMLData(filename, **options)
    all_options=cls._get_all_options(options)
    filename=os.path.abspath(filename)
    cached_names=[item.origin for item in cls._cache]
    if all_options['use_caching'] and filename in cached_names:
      cache_index=cached_names.index(filename)
      cached_object=cls._cache[cache_index]
      compare_options=dict(all_options)
      compare_options['callback']=None
      if cached_object._options==compare_options:
        return cached_object
    # else
    self=object.__new__(cls)
    self._options=all_options
    # create empty attributes
    self._channel_names=[]
    self._channel_origin=[]
    self._channel_data=[]
    self.measurement_type=""
    self.origin=filename
    # process the file
    self._read_times=[]

    if not self._read_file(filename):
      return None
    if all_options['use_caching']:
      if filename in cached_names:
        cache_index=cached_names.index(filename)
        cls._cache.pop(cache_index)
      # make sure cache does not get bigger than MAX_CACHE items or 80% of available memory
      while len(cls._cache)>=cls.MAX_CACHE:
        cls._cache.pop(0)
      cls._cache.append(self)
    # remove callback function to make the object Pickleable
    self._options['callback']=None
    return self

  @classmethod
  def _get_all_options(cls, options):
    all_options=dict(cls.DEFAULT_OPTIONS)
    for key, value in options.items():
      if key not in all_options:
        raise ValueError("%s is not a known option parameter"%key)
      all_options[key]=value
    return all_options

  def _read_file(self, filename):
    '''
    Load data from a Nexus file.

    :param str filename: Path to file to read
    '''
    start=time()
    if self._options['callback']:
      self._options['callback'](0.)
    try:
      nxs=h5py.File(filename, mode='r')
    except IOError:
      warn('Could not read nxs file %s'%filename, exc_info=True)
      return False
    # Detect instrument beamline and file format
    first_entry=list(nxs.keys())[0]
    try:
      beamline_raw=nxs[first_entry]['instrument/beamline'][()][0]
      beamline=beamline_raw.decode('utf-8') if isinstance(beamline_raw, bytes) else str(beamline_raw)
    except KeyError:
      beamline='4A' # default to REF_M for files without beamline field
    self._beamline=beamline

    # Detect modern .nxs.h5 event format (NXsnsevent definition)
    self._is_event_h5=False
    try:
      def_raw=nxs[first_entry]['definition'][()][0]
      definition=def_raw.decode('utf-8') if isinstance(def_raw, bytes) else str(def_raw)
      if definition=='NXsnsevent':
        self._is_event_h5=True
    except KeyError:
      pass

    if beamline in ('4B', 'BL4B'):
      return self._read_file_LR(filename, nxs, start)
    else:
      return self._read_file_MR(filename, nxs, start)

  def _read_file_MR(self, filename, nxs, start):
    '''
    Load data from a REF_M (beamline 4A) Nexus file.
    Handles polarization state detection and channel mapping.

    :param str filename: Path to file to read
    :param h5py.File nxs: Open HDF5 file handle
    :param float start: Start time for performance tracking
    '''
    # Modern .nxs.h5 format: single entry, check for polarization
    if self._is_event_h5:
      # Check if polarized by examining SF1 log
      is_polarized=False
      entry_key=[ch for ch in nxs.keys() if ch.startswith('entry')]
      if entry_key and 'DASlogs/SF1' in nxs[entry_key[0]]:
        try:
          sf1_vals=nxs[entry_key[0]+'/DASlogs/SF1/value'][()]
          is_polarized=(len(unique(sf1_vals))>1)
        except KeyError:
          warn('SF1 log present but unreadable — treating as unpolarized')

      if is_polarized:
        return self._read_file_event_h5_polarized(filename, nxs, start)
      else:
        return self._read_file_event_h5(filename, nxs, start, MRDataset)

    # analyze channels
    channels=list(nxs.keys())
    debug('Channels in file: '+repr(channels))
    if channels==['entry'] and 'DASlogs' not in nxs[channels[0]]:
      # ancient file format with polarizations in different files
      nxs=self._get_ancient(filename)
      channels=sorted(nxs.keys())
      is_ancient=True
    else:
      is_ancient=False
    try:
      max_counts=max([nxs[channel][u'total_counts'][()][0] for channel in channels])
    except KeyError:
      warn('total_counts not defined in channels')
      return False
    for channel in list(channels):
      if nxs[channel][u'total_counts'][()][0]<(self.COUNT_THREASHOLD*max_counts):
        channels.remove(channel)
    if len(channels)==0:
      debug('No valid channels in file')
      return False
    try:
      ana=nxs[channels[0]]['instrument/analyzer/AnalyzerLift/value'][()][0]
      pol=nxs[channels[0]]['instrument/polarizer/PolLift/value'][()][0]
    except KeyError:
      ana=-1.e10
      pol=-1.e10

    try:
      ana_trans=nxs[channels[0]]['instrument/analyzer/AnalyzerTrans/value'][()][0]
    except KeyError:
      ana_trans=-1.e10

    try:
      smpt=nxs[channels[0]]['DASlogs/SMPolTrans/value'][()][0]
    except KeyError:
      smpt=0.

    # select the type of measurement that has been used
    # Skip the labels, since the conditions defining the polarizer/analyzer positions
    # have changed substantially since the DAS upgrade.
    start_time_str = nxs[channels[0]]['start_time'][()][0]
    if isinstance(start_time_str, bytes):
      start_time_str = start_time_str.decode('utf-8')
    assign_labels = True
    try:
        date_str = start_time_str.split('T')[0]
        parts_str = date_str.split('-')
        year_month_int = int("%s%s" % (parts_str[0], parts_str[1]))
        if year_month_int >= 201807:
            assign_labels = False
    except Exception:
        warn("Problem parsing start time: skipping labels")
        assign_labels = False

    self.measurement_type = ''
    mapping = []
    if assign_labels:
        if is_analyzer_in(ana, ana_trans, start_time_str): # is analyzer is in position
          if channels[0] in [m[1] for m in MAPPING_12FULL]:
            self.measurement_type='Polarization Analysis w/E-Field'
            mapping=list(MAPPING_12FULL)
          else:
            self.measurement_type='Polarization Analysis'
            mapping=list(MAPPING_FULLPOL)
        elif abs(pol-instrument.POLARIZER_IN[0])<instrument.POLARIZER_IN[1] or \
             abs(smpt-instrument.SUPERMIRROR_IN[0])<instrument.SUPERMIRROR_IN[1]:
          if channels[0] in [m[1] for m in MAPPING_12HALF]:
            self.measurement_type='Polarized w/E-Field'
            mapping=list(MAPPING_12HALF)
          else:
            self.measurement_type='Polarized'
            mapping=list(MAPPING_HALFPOL)
        elif 'DASlogs' in nxs[channels[0]] and \
              nxs[channels[0]]['DASlogs'].get('SP_HV_Minus') is not None and \
              channels!=[u'entry-Off_Off']: # is E-field cart connected and not only 0V measured
          self.measurement_type='Electric Field'
          mapping=list(MAPPING_EFIELD)
        elif len(channels)==1:
          self.measurement_type='Unpolarized'
          mapping=list(MAPPING_UNPOL)
        else:
          self.measurement_type='Unknown'
          mapping=[]

    # check that all channels have a mapping entry
    for channel in channels:
      if channel not in [m[1] for m in mapping]:
        mapping.append((channel.lstrip('entry-'), channel))

    # get runtime for event mode splitting
    total_duration=time_from_header('', nxs=nxs)

    progress=0.1
    if self._options['callback']:
      self._options['callback'](progress)
    self._read_times.append(time()-start)
    i=1
    empty_channels=[]
    for dest, channel in mapping:
      if channel not in channels:
        continue
      raw_data=nxs[channel]
      if filename.endswith('event.nxs') and not os.path.exists(filename.replace('_event', '')):
        data=MRDataset.from_event(raw_data, self._options,
                                  callback=self._options['callback'],
                                  callback_offset=progress,
                                  callback_scaling=0.9/len(channels),
                                  tof_overwrite=self._options['event_tof_overwrite'],
                                  total_duration=total_duration)
        if data is None:
          # no data in channel, don't add it
          empty_channels.append(dest)
          continue
      elif filename.endswith('histo.nxs'):
        data=MRDataset.from_histogram(raw_data, self._options)
      else:
        # old format file
        if filename.endswith('event.nxs'):
          warn('Event mode not implemented for old file format, please select histogram file.')
          return False
        data=MRDataset.from_old_format(raw_data, self._options)
      self._channel_data.append(data)
      self._channel_names.append(dest)
      self._channel_origin.append(channel)
      progress=0.1+0.9*float(i)/len(channels)
      if self._options['callback']:
        self._options['callback'](progress)
      i+=1
      self._read_times.append(time()-self._read_times[-1]-start)
    #print time()-start
    if not is_ancient:
      nxs.close()
    if empty_channels:
      warn('No counts for state %s'%(','.join(empty_channels)))
    return True

  def _read_file_LR(self, filename, nxs, start):
    '''
    Load data from a REF_L (beamline 4B) Nexus file.
    REF_L data is always unpolarized (single entry channel).

    :param str filename: Path to file to read
    :param h5py.File nxs: Open HDF5 file handle
    :param float start: Start time for performance tracking
    '''
    # Modern .nxs.h5 format
    if self._is_event_h5:
      return self._read_file_event_h5(filename, nxs, start, LRDataset)

    # REF_L files have a single 'entry' channel (unpolarized)
    channels=list(nxs.keys())
    debug('LR Channels in file: '+repr(channels))
    try:
      max_counts=max([nxs[channel][u'total_counts'][()][0] for channel in channels])
    except KeyError:
      warn('total_counts not defined in channels')
      return False
    for channel in list(channels):
      if nxs[channel][u'total_counts'][()][0]<(self.COUNT_THREASHOLD*max_counts):
        channels.remove(channel)
    if len(channels)==0:
      debug('No valid channels in file')
      return False

    self.measurement_type='Unpolarized'
    # map each entry to a channel name
    mapping=[]
    for channel in channels:
      dest=channel.lstrip('entry-') if channel!='entry' else 'x'
      mapping.append((dest, channel))

    # get runtime for event mode splitting
    total_duration=time_from_header('', nxs=nxs)

    progress=0.1
    if self._options['callback']:
      self._options['callback'](progress)
    self._read_times.append(time()-start)
    i=1
    empty_channels=[]
    for dest, channel in mapping:
      raw_data=nxs[channel]
      if filename.endswith('event.nxs'):
        data=LRDataset.from_event(raw_data, self._options,
                                  callback=self._options['callback'],
                                  callback_offset=progress,
                                  callback_scaling=0.9/len(channels),
                                  tof_overwrite=self._options['event_tof_overwrite'],
                                  total_duration=total_duration)
        if data is None:
          empty_channels.append(dest)
          continue
      else:
        data=LRDataset.from_histogram(raw_data, self._options)
      self._channel_data.append(data)
      self._channel_names.append(dest)
      self._channel_origin.append(channel)
      progress=0.1+0.9*float(i)/len(channels)
      if self._options['callback']:
        self._options['callback'](progress)
      i+=1
      self._read_times.append(time()-self._read_times[-1]-start)

    nxs.close()
    if empty_channels:
      warn('No counts for state %s'%(','.join(empty_channels)))
    return True

  def _read_file_event_h5(self, filename, nxs, start, dataset_cls):
    '''
    Load data from a modern .nxs.h5 event NeXus file (NXsnsevent format).
    Single entry, always treated as unpolarized.

    :param str filename: Path to file to read
    :param h5py.File nxs: Open HDF5 file handle
    :param float start: Start time for performance tracking
    :param type dataset_cls: MRDataset or LRDataset
    '''
    channels=[ch for ch in nxs.keys() if ch.startswith('entry')]
    debug('Event H5 channels in file: '+repr(channels))
    if len(channels)==0:
      debug('No entry channels in .nxs.h5 file')
      return False
    try:
      max_counts=max([nxs[channel][u'total_counts'][()][0] for channel in channels])
    except KeyError:
      warn('total_counts not defined in channels')
      return False
    for channel in list(channels):
      if nxs[channel][u'total_counts'][()][0]<(self.COUNT_THREASHOLD*max_counts):
        channels.remove(channel)
    if len(channels)==0:
      debug('No valid channels in .nxs.h5 file')
      return False

    self.measurement_type='Unpolarized'
    mapping=[(u'x', channels[0])]

    # get runtime for event mode splitting
    total_duration=time_from_header('', nxs=nxs)

    progress=0.1
    if self._options['callback']:
      self._options['callback'](progress)
    self._read_times.append(time()-start)
    i=1
    empty_channels=[]
    for dest, channel in mapping:
      raw_data=nxs[channel]
      data=dataset_cls.from_event_h5(raw_data, self._options,
                                     callback=self._options['callback'],
                                     callback_offset=progress,
                                     callback_scaling=0.9/len(channels),
                                     tof_overwrite=self._options['event_tof_overwrite'],
                                     total_duration=total_duration)
      if data is None:
        empty_channels.append(dest)
        continue
      self._channel_data.append(data)
      self._channel_names.append(dest)
      self._channel_origin.append(channel)
      progress=0.1+0.9*float(i)/len(channels)
      if self._options['callback']:
        self._options['callback'](progress)
      i+=1
      self._read_times.append(time()-self._read_times[-1]-start)

    nxs.close()
    if empty_channels:
      warn('No counts for state %s'%(','.join(empty_channels)))
    return True

  def _read_file_event_h5_polarized(self, filename, nxs, start):
    '''
    Load polarized data from a modern .nxs.h5 event NeXus file.
    Uses SF1/SF2 time-series to separate events into polarization channels.

    :param str filename: Path to file to read
    :param h5py.File nxs: Open HDF5 file handle
    :param float start: Start time for performance tracking
    '''
    entry_keys=[ch for ch in nxs.keys() if ch.startswith('entry')]
    if len(entry_keys)==0:
      debug('No entry channels in .nxs.h5 file')
      return False
    entry=nxs[entry_keys[0]]

    try:
      total_counts=entry['total_counts'][()][0]
    except KeyError:
      warn('total_counts not defined')
      return False
    if total_counts<1:
      debug('No counts in .nxs.h5 file')
      return False

    # Filter events by polarization state
    channels=_filter_events_by_polarization(entry)
    if channels is None or len(channels)==0:
      # Fall back to unpolarized loading
      debug('Polarization filtering failed — falling back to unpolarized')
      return self._read_file_event_h5(filename, nxs, start, MRDataset)

    # Determine measurement type from channel count
    if len(channels)==4:
      self.measurement_type='Polarization Analysis'
    elif len(channels)==2:
      self.measurement_type='Polarized'
    else:
      self.measurement_type='Unpolarized'

    progress=0.1
    if self._options['callback']:
      self._options['callback'](progress)
    self._read_times.append(time()-start)

    i=1
    empty_channels_list=[]
    for name, (ids, tofs, chan_pc) in sorted(channels.items()):
      data=MRDataset.from_event_h5_filtered(
        entry, ids, tofs, self._options,
        callback=self._options['callback'],
        callback_offset=progress,
        callback_scaling=0.9/len(channels),
        tof_overwrite=self._options['event_tof_overwrite'])
      if data is None:
        empty_channels_list.append(name)
        continue
      # Override the full-run charge set during load with this channel's
      # integrated charge so polarized normalization matches Mantid.
      if chan_pc is not None:
        data.proton_charge=chan_pc
      self._channel_data.append(data)
      self._channel_names.append(name)
      self._channel_origin.append(entry_keys[0])
      progress=0.1+0.9*float(i)/len(channels)
      if self._options['callback']:
        self._options['callback'](progress)
      i+=1
      self._read_times.append(time()-self._read_times[-1]-start)

    nxs.close()
    if empty_channels_list:
      warn('No counts for state %s'%(','.join(empty_channels_list)))
    return len(self._channel_data)>0

  def _get_ancient(self, filename):
    '''
    For the oldest file format, where polarization channels
    are in different .nxs files, this method reads all files
    and builds a dictionary of it.

    :param str filename: Path to file to read
    '''
    base_name=filename.rsplit("_p", 1)[0]
    files=glob(base_name+"*.nxs")
    nxs={}
    for name in files:
      key=name.split(base_name)[1][1:-4]
      item=h5py.File(name, mode='r')
      nxs[key]=item['entry']
    return nxs

  def __getitem__(self, item):
    if type(item) in [int, slice]:
      return self._channel_data[item]
    else:
      if item in self._channel_names:
        return self._channel_data[self._channel_names.index(item)]
      elif item in self._channel_origin:
        return self._channel_data[self._channel_origin.index(item)]
      else:
        raise KeyError("No such channel: %s"%str(item))

  def __setitem__(self, item, data):
    if isinstance(item, int):
      self._channel_data[item]=data
    else:
      if item in self._channel_names:
        self._channel_data[self._channel_names.index(item)]=data
      elif item in self._channel_origin:
        self._channel_data[self._channel_origin.index(item)]=data
      else:
        raise KeyError("No such channel: %s"%str(item))

  def __len__(self):
    return len(self._channel_data)

  def __repr__(self):
    output=self.__class__.__name__+'({'
    spacer0=" "*(len(output)-1)
    for key, value in self.items():
      output+="\n%s '%s': %s,"%(spacer0, key, repr(value))
    output=output[:-1]+'\n'+spacer0+'})'
    return output

  def _repr_html_(self):
    '''Object representation for IPython'''
    output='<h2>%s object:</h2>\n'%self.__class__.__name__
    output+='<table>\n'
    output+='\t<tr><td colspan="2" align="center">Object Data:</td></td>\n'
    output+='\t<tr><th>State</th><th>Data Object</th></td>\n'
    for key, value in self.items():
      output+='\t<tr>\n\t\t<td>\n\t\t\t<b>%s</b>\n\t\t</td>\n\t\t<td>\n\t\t\t'%key
      output+='%s\n'%value._repr_html_()
      output+='\t\t</td>\n\t</tr>\n'
    output+='</table>'
    return output

  def keys(self):
    return self._channel_names

  def values(self):
    return self._channel_data

  def items(self):
    return zip(self.keys(), self.values())

  def numitems(self):
    ''':returns: three items tuples of the channel index, name and data'''
    return zip(range(len(self.keys())), self.keys(), self.values())

  def __iter__(self):
    for item in self.values():
      yield item

  @classmethod
  def get_cachesize(cls):
    """
    Return the total amount of memory used by the cached datasets.
    """
    return sum([ds.nbytes for ds in cls._cache])

  def __nbytes(self): return sum([ds.nbytes for ds in self])
  nbytes=property(__nbytes, doc='size of the data stored in memory for all states of this file')


  # easy access properties common to all datasets
  def __lambda_center(self): return self[0].lambda_center
  def __number(self): return self[0].number
  def __experiment(self): return self[0].experiment
  def __merge_warnings(self): return self[0].merge_warnings
  def __dpix(self): return self[0].dpix
  def __dangle(self): return self[0].dangle
  def __dangle0(self): return self[0].dangle0
  def __sangle(self): return self[0].sangle
  lambda_center=property(__lambda_center, doc='first state lambda_center attribute')
  number=property(__number, doc='first state number attribute')
  experiment=property(__experiment, doc='first state experiment attribute')
  merge_warnings=property(__merge_warnings, doc='first state merge_warnings attribute')
  dpix=property(__dpix, doc='first state dpix attribute')
  dangle=property(__dangle, doc='first state dangle attribute')
  dangle0=property(__dangle0, doc='first state dangle0 attribute')
  sangle=property(__sangle, doc='first state sangle attribute')


class NXSMultiData(NXSData):
  '''
  Sum up data of several nxs files.
  '''
  _progress=0.
  _progress_items=1
  _callback=None

  def __new__(cls, filenames, **options):
    if not hasattr(filenames, '__iter__') or len(filenames)==0:
      raise ValueError('File names needs to be an iterable of length > 0')
    all_options=cls._get_all_options(options)
    all_options['callback']=None
    cached_names=[item.origin for item in cls._cache]
    if all_options['use_caching'] and filenames in cached_names:
      cache_index=cached_names.index(filenames)
      cached_object=cls._cache[cache_index]
      if cached_object._options==all_options:
        return cached_object

    options['use_caching']=False # caching would return NXSData type objects
    filenames.sort()
    if 'callback' in options and options['callback'] is not None:
      cls._callback=options['callback']
      cls._progress_items=len(filenames)
      cls._progress=0.
      options['callback']=cls._callback_sum
    self=NXSData.__new__(cls, filenames[0], **options)
    numbers=[self.number]
    for i, filename in enumerate(filenames[1:]):
      cls._progress=(i+1.)/cls._progress_items
      other=NXSData(filename, **options)
      if len(self._channel_data)!=len(other._channel_data):
        raise ValueError('Files can not be combined due to different number of states')
      self._add_data(other)
      numbers.append(other.number)
    self.origin=filenames
    self._options=all_options
    for item in self:
      item.read_options=all_options
    if all_options['use_caching']:
      if filenames in cached_names:
        cache_index=cached_names.index(filenames)
        cls._cache.pop(cache_index)
      # make sure cache does not get bigger than MAX_CACHE items or 80% of available memory
      while len(cls._cache)>=cls.MAX_CACHE:
        cls._cache.pop(0)
      cls._cache.append(self)
    return self

  def _add_data(self, other):
    '''
    Add the counts of all channels to this dataset channels
    and increase the proton charge equally.

    :type other: NXSData
    '''
    for key, value in self.items():
      value+=other[key]

  @classmethod
  def _callback_sum(cls, progress):
    cls._callback(cls._progress+progress/cls._progress_items)

class XMLData(NXSData):
  '''
  Load running experiment from a set of xml files. The metat data xml
  contains the instrument info and the filenames of the collected data.
  '''

  def _read_file(self, filename):
    start=time()
    if self._options['callback']:
      self._options['callback'](0.)
    try:
      xml=minidom.parse(filename)
    except Exception:
      debug('Could not read xml file %s'%filename, exc_info=True)
      return False
    finfo=xml.getElementsByTagName('Files')[0]
    channels=[]
    xmlfiles=[]
    path=os.path.dirname(filename)
    for item in finfo.getElementsByTagName('entry'):
      channels.append(item.getAttribute('name'))
      xmlfiles.append((os.path.join(path, item.getAttribute('xy_file')),
                       os.path.join(path, item.getAttribute('tofx_file'))))

    # collect meta information
    daslogs={}
    for item in xml.getElementsByTagName('DASLogs')[0].getElementsByTagName('item'):
      value=item.getAttribute('value')
      try:
        value=float(value)
      except ValueError:
        pass
      daslogs[item.getAttribute('name')]=value

    channel_counts=[]
    # check counts for each channel
    for xyfile, ignore in xmlfiles:
      xyxml=minidom.parse(xyfile)
      channel_counts.append(int(xyxml.getElementsByTagName('TotalCounts')[0].childNodes[0].data))
    max_counts=max(channel_counts)
    for i in reversed(range(len(channels))):
      counts=channel_counts[i]
      if counts<(self.COUNT_THREASHOLD*max_counts):
        channels.pop(i)
        xmlfiles.pop(i)
    if len(channels)==0:
      debug('No valid channels in file')
      return False
    ana=daslogs['AnalyzerLift']
    pol=daslogs['PolLift']
    try:
      smpt=daslogs['SMPolTrans']
    except KeyError:
      smpt=0.

    # select the type of measurement that has been used
    if abs(ana-instrument.ANALYZER_IN[0])<instrument.ANALYZER_IN[1]: # is analyzer is in position
      if channels[0] in [m[1] for m in MAPPING_12FULL]:
        self.measurement_type='Polarization Analysis w/E-Field'
        mapping=list(MAPPING_12FULL)
      else:
        self.measurement_type='Polarization Analysis'
        mapping=list(MAPPING_FULLPOL)
    elif abs(pol-instrument.POLARIZER_IN[0])<instrument.POLARIZER_IN[1] or \
         abs(smpt-instrument.SUPERMIRROR_IN[0])<instrument.SUPERMIRROR_IN[1]:
      if channels[0] in [m[1] for m in MAPPING_12HALF]:
        self.measurement_type='Polarized w/E-Field'
        mapping=list(MAPPING_12HALF)
      else:
        self.measurement_type='Polarized'
        mapping=list(MAPPING_HALFPOL)
    #elif 'SP_HV_Minus' in daslogs and \
    #      daslogs['SP_HV_Minus']!='None' and \
    #      channels!=[u'entry-Off_Off']: # is E-field cart connected and not only 0V measured
    #  self.measurement_type='Electric Field'
    #  mapping=list(MAPPING_EFIELD)
    elif len(channels)==1:
      self.measurement_type='Unpolarized'
      mapping=list(MAPPING_UNPOL)
    else:
      self.measurement_type='Unknown'
      mapping=[]
    # check that all channels have a mapping entry
    for channel in channels:
      if channel not in [m[1] for m in mapping]:
        mapping.append((channel.lstrip('entry-'), channel))

    progress=0.1
    if self._options['callback']:
      self._options['callback'](progress)
    self._read_times.append(time()-start)
    i=1
    empty_channels=[]
    for dest, channel in mapping:
      if channel not in channels:
        continue
      xyfile, tofxfile=xmlfiles[channels.index(channel)]
      data=MRDataset.from_xml(xyfile, tofxfile, daslogs, self._options,
                              callback=self._options['callback'],
                              callback_offset=progress,
                              callback_scaling=0.9/len(channels),
                              tof_overwrite=self._options['event_tof_overwrite'])
      data.origin=(os.path.abspath(filename), channel)

      if data is None:
        # no data in channel, don't add it
        empty_channels.append(dest)
        continue

      self._channel_data.append(data)
      self._channel_names.append(dest)
      self._channel_origin.append(channel)
      progress=0.1+0.9*float(i)/len(channels)
      if self._options['callback']:
        self._options['callback'](progress)
      i+=1
      self._read_times.append(time()-self._read_times[-1]-start)

    if empty_channels:
      warn('No counts for state %s'%(','.join(empty_channels)))

    return True

class MRDataset(object):
  '''
  Representation of one measurement channel of the reflectometer
  including meta data.
  '''
  proton_charge=1.e9 #: total proton charge on target [pC]
  total_counts=1 #: total counts on detector
  total_time=1 #: time counted in this channal
  tof_edges=None #: array of time of flight edges for the bins [µs]
  dangle=4. #: detector arm angle value in [°]
  dangle0=4. #: detector arm angle value of direct pixel measurement in [°]
  sangle=0.5 #: sample angle [°]
  mon_data=None #: array of monitor counts per ToF bin

  # for resolution calculation
  slit1_width=3. #: first slit width [mm]
  slit1_dist=2600. #: first slit to sample distance [mm]
  slit2_width=2. #: second slit width [mm]
  slit2_dist=2019. #: second slit to sample distance [mm]
  slit3_width=0.05 #: last slit width [mm]
  slit3_dist=714. #: last slit to sample distance [mm]

  ai=None #: incident angle
  dpix=150 #: pixel of direct beam position at dangle0
  lambda_center=3.37 #: central wavelength of measurement band [Å]
  xydata=None #: 2D array of intensity projected on X-Y
  xtofdata=None #: 2D array of intensity projected on X-ToF
  data=None #: 3D array of intensity in X, Y and ToF
  logs={} #: Log information of instrument parameters
  log_units={} #: Units of the parameters given in logs
  experiment='' #: Name of the experiment
  number=1 #: Index of the run
  merge_warnings=''
  dist_mod_det=21.2535 #: moderator to detector distance [m]
  dist_sam_det=2.55505 #: sample to detector distance [m]
  det_size_x=0.2128 #: horizontal size of detector [m]
  det_size_y=0.1792 #: vertical size of detector [m]
  from_event_mode=False #: was this dataset created from event mode nexus file

  _Q=None
  _I=None
  _dI=None
  _active_area_x=None #: active pixels for x direction
  _active_area_y=None #: active pixels for y direction

  def __init__(self):
    '''
    Initialize an empty dataset. To actually load a Nexus file channel
    use the class methods from_histogram or from_event.
    '''
    self.origin=('none', 'none')

  @classmethod
  @log_call
  def from_histogram(cls, data, read_options):
    '''
    Create object from a histogram Nexus file.
    '''
    output=cls()
    output.read_options=read_options
    try:
      output._collect_info(data)
    except KeyError:
      warn('Error while collecting metadata:\n\n'+traceback.format_exc())

    output.tof_edges=data['bank1/time_of_flight'][()]
    # the data arrays
    output.data=data['bank1/data'][()].astype(float) # 3D dataset
    output.xydata=data['bank1']['data_x_y'][()].transpose().astype(float) # 2D dataset
    output.xtofdata=data['bank1']['data_x_time_of_flight'][()].astype(float) # 2D dataset

    try:
      mon_tof_from=data['monitor1']['time_of_flight'][()].astype(float)*\
                                            output.dist_mod_det/output.dist_mod_mon
      mon_I_from=data['monitor1']['data'][()].astype(float)
      mod_data=histogram((mon_tof_from[:-1]+mon_tof_from[1:])/2., output.tof_edges,
                         weights=mon_I_from)[0]
      output.mon_data=mod_data
    except KeyError:
      output.mon_data=None
    return output

  @classmethod
  @log_call
  def from_old_format(cls, data, read_options):
    '''
    Create object from a histogram Nexus file.
    '''
    output=cls()
    output.read_options=read_options
    try:
      output._collect_info(data)
    except KeyError:
      warn('Error while collecting metadata:\n\n'+traceback.format_exc())

    # first ToF edge is 0, prevent that
    output.tof_edges=data['bank1/time_of_flight'][()][1:]
    # the data arrays
    output.data=data['bank1/data'][()].astype(float)[:, :, 1:] # 3D dataset
    output.xydata=output.data.sum(axis=2).transpose()
    output.xtofdata=output.data.sum(axis=1)
    return output

  @classmethod
  @log_call
  def from_event(cls, data, read_options,
                 callback=None, callback_offset=0., callback_scaling=1.,
                 total_duration=None,
                 tof_overwrite=None):
    '''
    Load data from a Nexus file containing event information.
    Creates 3D histogram with ither linear or 1/t spaced
    time of flight channels. The result has the same format as
    from the read_file function.
    '''
    output=cls()
    output.read_options=read_options
    output.from_event_mode=True
    bin_type=read_options['bin_type']
    bins=read_options['bins']
    try:
      output._collect_info(data)
    except KeyError:
      warn('Error while collecting metadata:\n\n'+traceback.format_exc())

    if tof_overwrite is None:
      lcenter=data['DASlogs/LambdaRequest/value'][()][0]
      # Chopper speed governs the wavelength bandwidth (30 Hz doubles it)
      chopper_speed=getattr(output, 'chopper_speed', None)
      if chopper_speed is None and 'DASlogs/SpeedRequest1' in data:
        chopper_speed=float(data['DASlogs/SpeedRequest1/value'][()][0])
      tmin, tmax=_compute_tof_range_us(output.dist_mod_det, lcenter, chopper_speed)
      if bin_type==0: # constant Δλ
        tof_edges=linspace(tmin, tmax, bins+1)
      elif bin_type==1: # constant ΔQ
        tof_edges=1./linspace(1./tmin, 1./tmax, bins+1)
      elif bin_type==2: # constant Δλ/λ
        tof_edges=tmin*(((tmax/tmin)**(1./bins))**arange(bins+1))
      else:
        raise ValueError('Unknown bin type %i'%bin_type)
    else:
      tof_edges=tof_overwrite

    # Histogram the data
    # create ToF edges for the binning and correlate pixel indices with pixel position
    tof_ids=array(data['bank1_events/event_id'][()], dtype=int)
    tof_time=data['bank1_events/event_time_offset'][()]
    # read the corresponding proton charge of each pulse
    tof_pc=data['DASlogs/proton_charge/value'][()]
    if read_options['event_split_bins']:
      split_bins=read_options['event_split_bins']
      split_index=read_options['event_split_index']
      # read the relative time in seconds from measurement start to event
      tof_real_time=data['bank1_events/event_time_zero'][()]
      tof_idx_to_id=data['bank1_events/event_index'][()]
      if total_duration is None:
        split_step=float(tof_real_time[-1]+0.01)/split_bins
      else:
        split_step=float(total_duration+0.01)/split_bins
      try:
        start_id, stop_id=where(((tof_real_time>=(split_index*split_step))&
                                 (tof_real_time<((split_index+1)*split_step))))[0][[0,-1]]
      except IndexError:
        debug('No pulses in selected range')
        return None

      if start_id==0:
        start_idx=0
      else:
        start_idx=tof_idx_to_id[start_id-1]
      stop_idx=tof_idx_to_id[stop_id]
      debug('Event split with %.1f<=t<%.1f yielding pulse/tof indices: [%i:%i]/[%i:%i]'
            %((split_index*split_step), ((split_index+1)*split_step),
              start_id, stop_id+1, start_idx, stop_idx)
            )
      tof_pc=tof_pc[start_id:stop_id+1]

      tof_ids=tof_ids[start_idx:stop_idx]
      tof_time=tof_time[start_idx:stop_idx]
      # correct the total count value for the number of neutrons in the selected range
      output.total_counts=tof_time.shape[0]
      if output.total_counts==0:
        debug('No counts in selected range')
        return None
    # calculate total proton charge in the selected area
    output.proton_charge=tof_pc.sum()
    dimension=data['bank1/data_x_y'].shape
    Ixyt=MRDataset.bin_events(tof_ids, tof_time, tof_edges, dimension,
                              callback, callback_offset, callback_scaling)

    # create projections for the 2D datasets
    Ixy=Ixyt.sum(axis=2)
    Ixt=Ixyt.sum(axis=1)
    # store the data
    output.tof_edges=tof_edges
    output.data=Ixyt.astype(float) # 3D dataset
    output.xydata=Ixy.transpose().astype(float) # 2D dataset
    output.xtofdata=Ixt.astype(float) # 2D dataset
    return output

  @classmethod
  @log_call
  def from_event_h5(cls, data, read_options,
                    callback=None, callback_offset=0., callback_scaling=1.,
                    total_duration=None, tof_overwrite=None):
    '''
    Load data from a modern .nxs.h5 event NeXus file (NXsnsevent format).
    Converts events into the same 3D histogram as from_histogram().

    :param h5py._hl.group.Group data: HDF5 entry group
    :param dict read_options: Options controlling binning
    '''
    output=cls()
    output.read_options=read_options
    output.from_event_mode=True
    bin_type=read_options['bin_type']
    bins=read_options['bins']

    # Collect metadata from DASlogs (not structured paths)
    try:
      output._collect_info_h5(data)
    except KeyError:
      warn('Error collecting metadata from .nxs.h5:\n\n'+traceback.format_exc())

    # Determine TOF edges
    if tof_overwrite is None:
      lcenter=output.lambda_center
      # Bandwidth depends on chopper speed (collected in _collect_info_h5)
      chopper_speed=getattr(output, 'chopper_speed', None)
      tmin, tmax=_compute_tof_range_us(output.dist_mod_det, lcenter, chopper_speed)
      if bin_type==0: # constant Δλ
        tof_edges=linspace(tmin, tmax, bins+1)
      elif bin_type==1: # constant ΔQ
        tof_edges=1./linspace(1./tmin, 1./tmax, bins+1)
      elif bin_type==2: # constant Δλ/λ
        tof_edges=tmin*(((tmax/tmin)**(1./bins))**arange(bins+1))
      else:
        raise ValueError('Unknown bin type %i'%bin_type)
    else:
      tof_edges=tof_overwrite

    # Read event data
    tof_ids=array(data['bank1_events/event_id'][()], dtype=int)
    tof_time=data['bank1_events/event_time_offset'][()]

    if len(tof_ids)==0:
      debug('No events in file')
      return None

    # Read proton charge
    tof_pc=data['DASlogs/proton_charge/value'][()]

    # Handle event splitting (same logic as from_event)
    if read_options['event_split_bins']:
      split_bins=read_options['event_split_bins']
      split_index=read_options['event_split_index']
      tof_real_time=data['bank1_events/event_time_zero'][()]
      tof_idx_to_id=data['bank1_events/event_index'][()]
      # Use the larger of total_duration and actual pulse time range to ensure
      # all pulses are covered (time_from_header may underestimate vs event_time_zero)
      effective_duration=tof_real_time[-1]
      if total_duration is not None:
        effective_duration=_builtins.max(effective_duration, total_duration)
      split_step=float(effective_duration+0.01)/split_bins
      try:
        start_id, stop_id=where(((tof_real_time>=(split_index*split_step))&
                                 (tof_real_time<((split_index+1)*split_step))))[0][[0,-1]]
      except IndexError:
        debug('No pulses in selected range')
        return None

      # NXevent_data convention: event_index[i] = first event for pulse i
      # (differs from old *_event.nxs where event_index[i] = cumulative count after pulse i)
      start_idx=tof_idx_to_id[start_id]
      if stop_id+1<len(tof_idx_to_id):
        stop_idx=tof_idx_to_id[stop_id+1]
      else:
        stop_idx=len(tof_ids)
      debug('Event split with %.1f<=t<%.1f yielding pulse/tof indices: [%i:%i]/[%i:%i]'
            %((split_index*split_step), ((split_index+1)*split_step),
              start_id, stop_id+1, start_idx, stop_idx)
            )
      tof_pc=tof_pc[start_id:stop_id+1]
      tof_ids=tof_ids[start_idx:stop_idx]
      tof_time=tof_time[start_idx:stop_idx]
      output.total_counts=tof_time.shape[0]
      if output.total_counts==0:
        debug('No counts in selected range')
        return None

    # Calculate total proton charge
    output.proton_charge=tof_pc.sum()

    # Detector dimensions from instrument XML or known constants
    n_x, n_y=_get_detector_dimensions(data)
    dimension=(n_x, n_y)

    # Bin events into 3D histogram using existing infrastructure
    Ixyt=MRDataset.bin_events(tof_ids, tof_time, tof_edges, dimension,
                              callback, callback_offset, callback_scaling)

    # Create projections
    Ixy=Ixyt.sum(axis=2)
    Ixt=Ixyt.sum(axis=1)

    # Store data
    output.tof_edges=tof_edges
    output.data=Ixyt.astype(float)
    output.xydata=Ixy.transpose().astype(float)
    output.xtofdata=Ixt.astype(float)
    return output

  @classmethod
  @log_call
  def from_event_h5_filtered(cls, data, event_ids, event_tofs, read_options,
                              callback=None, callback_offset=0., callback_scaling=1.,
                              tof_overwrite=None):
    '''
    Load data from pre-filtered events (polarization channel).
    Same as from_event_h5() but uses provided event arrays instead of
    reading from the file.

    :param h5py._hl.group.Group data: HDF5 entry group (for metadata)
    :param array event_ids: Pre-filtered pixel IDs for this channel
    :param array event_tofs: Pre-filtered TOF values for this channel
    :param dict read_options: Options controlling binning
    '''
    output=cls()
    output.read_options=read_options
    output.from_event_mode=True
    bin_type=read_options['bin_type']
    bins=read_options['bins']

    # Collect metadata from DASlogs
    try:
      output._collect_info_h5(data)
    except KeyError:
      warn('Error collecting metadata from .nxs.h5:\n\n'+traceback.format_exc())

    # Determine TOF edges
    if tof_overwrite is None:
      lcenter=output.lambda_center
      chopper_speed=getattr(output, 'chopper_speed', None)
      tmin, tmax=_compute_tof_range_us(output.dist_mod_det, lcenter, chopper_speed)
      if bin_type==0:
        tof_edges=linspace(tmin, tmax, bins+1)
      elif bin_type==1:
        tof_edges=1./linspace(1./tmin, 1./tmax, bins+1)
      elif bin_type==2:
        tof_edges=tmin*(((tmax/tmin)**(1./bins))**arange(bins+1))
      else:
        raise ValueError('Unknown bin type %i'%bin_type)
    else:
      tof_edges=tof_overwrite

    tof_ids=array(event_ids, dtype=int)
    tof_time=event_tofs

    if len(tof_ids)==0:
      debug('No events in filtered channel')
      return None

    output.total_counts=len(tof_ids)

    # Detector dimensions
    n_x, n_y=_get_detector_dimensions(data)
    dimension=(n_x, n_y)

    # Bin events into 3D histogram
    Ixyt=MRDataset.bin_events(tof_ids, tof_time, tof_edges, dimension,
                              callback, callback_offset, callback_scaling)

    # Create projections
    Ixy=Ixyt.sum(axis=2)
    Ixt=Ixyt.sum(axis=1)

    # Store data
    output.tof_edges=tof_edges
    output.data=Ixyt.astype(float)
    output.xydata=Ixy.transpose().astype(float)
    output.xtofdata=Ixt.astype(float)
    return output

  @classmethod
  @log_call
  def from_xml(cls, xyfile, tofxfile, daslogs,
               read_options, callback=None, callback_offset=0.,
               callback_scaling=1., tof_overwrite=None):
    '''
    Load data from a XML previe format created by PyDAS.
    Needs to rebin the data to be able to normalize it with a normal direct beam measurement.
    The 3D dataset is just a dummy, as it is not available in this format.
    '''
    output=cls()
    output.read_options=read_options
    output.from_event_mode=True
    bin_type=read_options['bin_type']
    bins=read_options['bins']

    try:
      xyxml=minidom.parse(xyfile)
    except Exception:
      warn('Could not parse xml file %s:'%xyfile, exc_info=True)
      return None

    output.total_time=float(xyxml.getElementsByTagName('TotalTime')[0].childNodes[0].data[:-4])
    output.total_counts=int(xyxml.getElementsByTagName('TotalCounts')[0].childNodes[0].data)
    output.proton_charge=float(xyxml.getElementsByTagName('TotalCharge')[0].childNodes[0].data)
    output.number=int(daslogs['run_number'])
    output.experiment='Live Data'

    output.logs=dict(daslogs)

    output.lambda_center=daslogs['lamda_center']
    output.sangle=daslogs['SANGLE']
    output.dangle=daslogs['DANGLE']
    output.dangle0=daslogs['DANGLE0']
    output.dpix=daslogs['DIRPIX']
    output.slit1_width=daslogs['S1HWidth']
    output.slit2_width=daslogs['S2HWidth']
    output.slit3_width=daslogs['S3HWidth']

    xydata=MRDataset._getxml_data(xyxml)
    try:
      tofxxml=minidom.parse(tofxfile)
    except Exception:
      warn('Could not parse xml file %s:'%tofxfile, exc_info=True)
      return None
    tofxdata=MRDataset._getxml_data(tofxxml).T

    output.xydata=xydata.T.astype(float)

    if tof_overwrite is None:
      lcenter=output.lambda_center
      # Live PyDAS data has SpeedRequest1 in daslogs (may be missing on some setups)
      chopper_speed=daslogs.get('SpeedRequest1', None) if isinstance(daslogs, dict) else None
      tmin, tmax=_compute_tof_range_us(output.dist_mod_det, lcenter, chopper_speed)
      if bin_type==0: # constant Δλ
        tof_edges=linspace(tmin, tmax, bins+1)
      elif bin_type==1: # constant ΔQ
        tof_edges=1./linspace(1./tmin, 1./tmax, bins+1)
      elif bin_type==2: # constant Δλ/λ
        tof_edges=tmin*(((tmax/tmin)**(1./bins))**arange(bins+1))
      else:
        raise ValueError('Unknown bin type %i'%bin_type)
    else:
      tof_edges=tof_overwrite

    tmin=float(tofxxml.getElementsByTagName('TOFMin')[0].childNodes[0].data[:-3])
    tstep=float(tofxxml.getElementsByTagName('TOFBinSize')[0].childNodes[0].data[:-3])
    tof_bins=arange(tmin, tmin+tstep*tofxdata.shape[1], tstep)

    newxtofdata=zeros((tofxdata.shape[0], tof_edges.shape[0]-1), dtype=float)
    for i, (tfrom, tto) in enumerate(zip(tof_edges[:-1], tof_edges[1:])):
      newxtofdata[:, i]=tofxdata[:, (tof_bins>=tfrom)&(tof_bins<tto)].sum(axis=1)

    output.xtofdata=newxtofdata
    yscale=zeros(xydata.shape[1])
    yscale[xydata.shape[1]//2]=1.
    output.data=output.xtofdata[:, newaxis, :]*yscale[newaxis, :, newaxis]
    output.tof_edges=tof_edges

    return output

  @staticmethod
  def bin_events(tof_ids, tof_time, tof_edges, dimension,
                 callback=None, callback_offset=0., callback_scaling=1.):
    '''
    Filter events outside the tof_edges region and calculate the binning with devide_bin.

    @return: 3D array of dimensions (x, y, tof)
    '''
    region=(tof_time>=tof_edges[0])&(tof_time<=tof_edges[-1])
    result=array(MRDataset.devide_bin(tof_ids[region], tof_time[region], tof_edges, dimension,
                                callback, callback_offset, callback_scaling/len(tof_edges)))
    return result.transpose((1, 2, 0))

  @staticmethod
  def devide_bin(tof_ids, tof_time, tof_edges, dimension,
                 callback=None, callback_offset=0., callback_scaling=1., cbidx=0):
    '''
    Use a divide and conquer strategy to bin the data. For the actual binning the
    numpy bincount function is used, as it is much faster then histogram for
    counting of integer values.

    :param tof_ids: Array of positional indices for each event
    :param tof_time: Array of time of flight for each event
    :param tof_edges: The edges of bins to be used for the histogram
    :param dimension: x,y pixel size of detector
    :keyword callback: Optional callback function for the progress
    :keyword callback_offset: Offset for calling the function
    :keyword callback_scaling: Factor to multiply the counting index when calling the function
    :keyword cbidx: Current counting index for this recursive call

    :return: 3D list of dimensions (tof, x, y)
    '''
    if len(tof_edges)==2:
      # deepest recursion reached, all items should be within the two ToF edges
      if callback is not None:
        callback(callback_offset+callback_scaling*cbidx)
      return [bincount(tof_ids, minlength=dimension[0]*dimension[1]).reshape(
                                                  dimension[0], dimension[1]).tolist()]
    # split all events into two time of flight regions
    split_idx=len(tof_edges)//2
    left_region=tof_time<tof_edges[split_idx]
    left_list=MRDataset.devide_bin(tof_ids[left_region], tof_time[left_region],
                              tof_edges[:split_idx+1], dimension,
                              callback, callback_offset, callback_scaling, cbidx)
    right_region=logical_not(left_region)
    right_list=MRDataset.devide_bin(tof_ids[right_region], tof_time[right_region],
                              tof_edges[split_idx:], dimension,
                              callback, callback_offset, callback_scaling, split_idx+cbidx)
    return left_list+right_list

  def _collect_info(self, data):
    '''
    Extract header information from the HDF5 file.

    :param h5py._hl.group.Group data:
    '''
    self.origin=(os.path.abspath(data.file.filename), data.name.lstrip('/'))
    self.logs=NiceDict()
    self.log_minmax=NiceDict()
    self.log_units=NiceDict()
    if 'DASlogs' in data:  # the old format does not include the DAS logs
      if 'proton_charge' in data['DASlogs']: # some intermediate format has DASlogs but no pc
        # get an array of all pulses to make it possible to correlate values with states
        stimes=data['DASlogs/proton_charge/time'][()]
        stimes=stimes[::10] # reduce the number of items to speed up the correlation
        # use only values that are not directly before or after a state change
        stimesl, stimesc, stimesr=stimes[:-2], stimes[1:-1], stimes[2:]
        stimes=stimesc[((stimesr-stimesc)<1.)&((stimesc-stimesl)<1.)]
      else:
        stimes=None
      for motor, item in data['DASlogs'].items():
        if motor in ['proton_charge', 'frequency', 'Veto_pulse']:
          continue
        try:
          if 'units' in item['value'].attrs:
            units_attr=item['value'].attrs['units']
            self.log_units[motor]=units_attr.decode('utf8') if isinstance(units_attr, bytes) else str(units_attr)
          else:
            self.log_units[motor]=u''
          val=item['value'][()]
          if val.shape[0]==1:
            # ``val`` may be (1,) or (1, 1) — .flat[0] always yields a true scalar.
            # Without this, %g formatting downstream raises TypeError for 1-element 1-D slices.
            scalar=_log_scalar(val)
            self.logs[motor]=scalar
            self.log_minmax[motor]=(scalar, scalar)
          else:
            if stimes is not None:
              vtime=item['time'][()]
              sidx=searchsorted(vtime, stimes, side='right')
              sidx=maximum(sidx-1, 0)
              val=val[sidx]
            if len(val)==0:
              self.logs[motor]=NaN
              self.log_minmax[motor]=(NaN, NaN)
            elif not issubdtype(val.dtype, number):
              # Non-numeric (string/bytes) time series — keep the first value as a scalar
              self.logs[motor]=_log_scalar(val)
              self.log_minmax[motor]=(_log_scalar(val), _log_scalar(val))
            else:
              self.logs[motor]=val.mean()
              self.log_minmax[motor]=(val.min(), val.max())
        except Exception:
          continue
      self.lambda_center=data['DASlogs/LambdaRequest/value'][()][0]
      # Chopper speed governs the wavelength bandwidth (Fault 1: 30 vs 60 Hz)
      if 'DASlogs/SpeedRequest1' in data:
        try:
          self.chopper_speed=float(data['DASlogs/SpeedRequest1/value'][()][0])
        except Exception:
          self.chopper_speed=TOF_REFERENCE_FREQUENCY
    self.dangle=data['instrument/bank1/DANGLE/value'][()][0]
    if 'instrument/bank1/DANGLE0' in data: # compatibility for ancient file format
      self.dangle0=data['instrument/bank1/DANGLE0/value'][()][0]
      self.dpix=data['instrument/bank1/DIRPIX/value'][()][0]
      self.slit1_width=data['instrument/aperture1/S1HWidth/value'][()][0]
      self.slit2_width=data['instrument/aperture2/S2HWidth/value'][()][0]
      self.slit3_width=data['instrument/aperture3/S3HWidth/value'][()][0]
    else:
      self.slit1_width=data['instrument/aperture1/RSlit1/value'][()][0]-\
                      data['instrument/aperture1/LSlit1/value'][()][0]
      self.slit2_width=data['instrument/aperture2/RSlit2/value'][()][0]-\
                      data['instrument/aperture2/LSlit2/value'][()][0]
      self.slit3_width=data['instrument/aperture3/RSlit3/value'][()][0]-\
                      data['instrument/aperture3/LSlit3/value'][()][0]
    self.slit1_dist=-data['instrument/aperture1/distance'][()][0]*1000.
    self.slit2_dist=-data['instrument/aperture2/distance'][()][0]*1000.
    self.slit3_dist=-data['instrument/aperture3/distance'][()][0]*1000.

    self.sangle=data['sample/SANGLE/value'][()][0]

    self.proton_charge=data['proton_charge'][()][0]
    self.total_counts=data['total_counts'][()][0]
    self.total_time=data['duration'][()][0]

    self.dist_sam_det=data['instrument/bank1/SampleDetDis/value'][()][0]*1e-3
    self.dist_mod_det=data['instrument/moderator/ModeratorSamDis/value'][()][0]*1e-3+self.dist_sam_det
    self.dist_mod_mon=data['instrument/moderator/ModeratorSamDis/value'][()][0]*1e-3-2.75
    self.det_size_x=data['instrument/bank1/origin/shape/size'][()][0]
    self.det_size_y=data['instrument/bank1/origin/shape/size'][()][1]

    self.experiment=str(data['experiment_identifier'][()][0])
    self.number=int(data['run_number'][()][0])
    self.merge_warnings=str(data['SNSproblem_log_geom/data'][()][0])

    detector_id_raw=data['instrument/SNSgeometry_file_name'][()][0]
    detector_id=detector_id_raw.decode('utf-8') if isinstance(detector_id_raw, bytes) else str(detector_id_raw)
    if detector_id in instrument.DETECTOR_REGION:
      self.active_area_x=instrument.DETECTOR_REGION[detector_id][0]
      self.active_area_y=instrument.DETECTOR_REGION[detector_id][1]

  def _collect_info_h5(self, data):
    '''
    Extract header information from a modern .nxs.h5 REF_M file.
    All metadata comes from DASlogs. Instrument geometry from settings.json.

    :param h5py._hl.group.Group data:
    '''
    self.origin=(os.path.abspath(data.file.filename), data.name.lstrip('/'))
    self.logs=NiceDict()
    self.log_minmax=NiceDict()
    self.log_units=NiceDict()

    # Read DASlogs (same loop as existing _collect_info)
    if 'DASlogs' in data:
      if 'proton_charge' in data['DASlogs']:
        stimes=data['DASlogs/proton_charge/time'][()]
        stimes=stimes[::10]
        stimesl, stimesc, stimesr=stimes[:-2], stimes[1:-1], stimes[2:]
        stimes=stimesc[((stimesr-stimesc)<1.)&((stimesc-stimesl)<1.)]
      else:
        stimes=None
      for motor, item in data['DASlogs'].items():
        if motor in ['proton_charge', 'frequency', 'Veto_pulse']:
          continue
        try:
          if 'units' in item['value'].attrs:
            units_attr=item['value'].attrs['units']
            self.log_units[motor]=units_attr.decode('utf8') if isinstance(units_attr, bytes) else str(units_attr)
          else:
            self.log_units[motor]=u''
          val=item['value'][()]
          if val.shape[0]==1:
            scalar=_log_scalar(val)
            self.logs[motor]=scalar
            self.log_minmax[motor]=(scalar, scalar)
          else:
            if stimes is not None:
              vtime=item['time'][()]
              sidx=searchsorted(vtime, stimes, side='right')
              sidx=maximum(sidx-1, 0)
              val=val[sidx]
            if len(val)==0:
              self.logs[motor]=NaN
              self.log_minmax[motor]=(NaN, NaN)
            elif not issubdtype(val.dtype, number):
              self.logs[motor]=_log_scalar(val)
              self.log_minmax[motor]=(_log_scalar(val), _log_scalar(val))
            else:
              self.logs[motor]=val.mean()
              self.log_minmax[motor]=(val.min(), val.max())
        except Exception:
          continue

    # Detector dimensions and pixel size from settings.json
    settings=_read_instrument_settings('ref_m', data)
    n_x=settings['number-of-x-pixels']
    n_y=settings['number-of-y-pixels']
    pixel_size_mm=settings['pixel-width']
    self.det_size_x=n_x*pixel_size_mm*1e-3  # mm to m
    self.det_size_y=n_y*pixel_size_mm*1e-3

    # REF_M angles from DASlogs (all with safe defaults)
    self.dangle=_get_daslog_value(data, 'DANGLE', default=0.0)
    self.dangle0=_get_daslog_value(data, 'DANGLE0', default=0.0)
    self.sangle=_get_daslog_value(data, 'SANGLE', default=0.0)
    self.dpix=_get_daslog_value(data, 'DIRPIX',
                    default=settings.get('default-direct-pixel', 150))

    # Wavelength (graceful degradation for early commissioning files)
    self.lambda_center=_get_daslog_value(data, 'LambdaRequest',
                            fallback_key='BL4A:Det:TH:BL:Lambda',
                            default=None)
    if self.lambda_center is None:
      warn('No LambdaRequest in DASlogs — early commissioning file; using 3.37 A')
      self.lambda_center=3.37

    # Chopper speed for wavelength range calculation
    self.chopper_speed=_get_daslog_value(data, 'SpeedRequest1', default=60.0)

    # Slit widths from DASlogs (readbacks may be 0; fall back to request values)
    self.slit1_width=_get_daslog_value(data, 'S1HWidth', default=0.0)
    if self.slit1_width==0.0:
      self.slit1_width=_get_daslog_value(data, 'S1HWidthRequest', default=0.0)
    self.slit2_width=_get_daslog_value(data, 'S2HWidth', default=0.0)
    if self.slit2_width==0.0:
      self.slit2_width=_get_daslog_value(data, 'S2HWidthRequest', default=0.0)
    self.slit3_width=_get_daslog_value(data, 'S3HWidth', default=0.0)
    if self.slit3_width==0.0:
      self.slit3_width=_get_daslog_value(data, 'S3HWidthRequest', default=0.0)

    # Distances from DASlogs (with safe defaults from settings.json)
    sdd_mm=_get_daslog_value(data, 'SampleDetDis', default=1830.0)
    mod_sam_mm=_get_daslog_value(data, 'ModeratorSamDis', default=16870.0)
    self.dist_sam_det=sdd_mm*1e-3
    self.dist_mod_det=mod_sam_mm*1e-3+self.dist_sam_det
    self.dist_mod_mon=mod_sam_mm*1e-3-2.75

    # Slit distances from settings.json (not in DASlogs)
    self.slit1_dist=settings.get('slit1-sample-distance', 2600.0)
    self.slit2_dist=settings.get('slit2-sample-distance', 2019.0)
    self.slit3_dist=settings.get('slit3-sample-distance', 714.0)

    # Standard metadata
    self.proton_charge=data['proton_charge'][()][0]
    self.total_counts=data['total_counts'][()][0]
    self.total_time=data['duration'][()][0]
    self.experiment=_decode(data['experiment_identifier'][()][0])
    self.number=int(data['run_number'][()][0])
    self.merge_warnings=''

  @staticmethod
  def _getxml_data(xml):
    data=xml.getElementsByTagName('Data')[0]
    rawdata=[item for item in data.childNodes if item.nodeType==minidom.CDATASection.nodeType][0]
    xdim=int(data.getAttribute('xdim'))
    ydim=int(data.getAttribute('ydim'))
    type_name=data.getAttribute('type')
    raw_bytes=rawdata.data.encode() if isinstance(rawdata.data, str) else rawdata.data
    Idata=frombuffer(base64.decodebytes(raw_bytes), dtype=type_name).reshape(xdim, ydim)
    return Idata

  def __repr__(self):
    if type(self.origin) is tuple:
      return "<%s '%s' counts: %i>"%(self.__class__.__name__,
                                     "%s/%s"%(os.path.basename(self.origin[0]), self.origin[1]),
                                     self.total_counts)
    else:
      return "<%s '%s' counts: %i>"%(self.__class__.__name__,
                                     "SUM"+repr(self.number),
                                     self.total_counts)

  def _repr_html_(self):
    '''Object representation for IPython'''
    output='<b>%s</b> Object:\n<table border="1">\n'%self.__class__.__name__
    output+='<tr><th>Attribute</th><th>Value</th></tr>\n'
    for attr in ['experiment', 'number', 'total_counts', 'proton_charge',
                 'sangle', 'dangle', 'dangle0', 'dpix']:
      output+='<tr><td>%s</td><td>%s</td></tr>\n'%(attr, str(getattr(self, attr)))
    if type(self.number) is list:
      for i, item in enumerate(self.origin):
        output+='<tr><td>origin[%i][0]</td><td>%s</td></tr>\n'%(i, item[0])
        output+='<tr><td>origin[%i][1]</td><td>%s</td></tr>\n'%(i, item[1])
    else:
      output+='<tr><td>origin[0]</td><td>%s</td></tr>\n'%self.origin[0]
      output+='<tr><td>origin[1]</td><td>%s</td></tr>\n'%self.origin[1]
    output+='</table>'
    return output

  def __iadd__(self, other):
    '''
    Add the data of one dataset to this dataset.
    '''
    self.data+=other.data
    self.xydata+=other.xydata
    self.xtofdata+=other.xtofdata
    self.total_counts+=other.total_counts
    self.proton_charge+=other.proton_charge
    if type(self.number) is list:
      self.number.append(other.number)
      self.origin.append(other.origin)
    else:
      self.number=[self.number, other.number]
      self.origin=[self.origin, other.origin]
    return self
    #self.origin.append(other.origin)

  def __add__(self, other):
    '''
    Add two datasets.
    '''
    output=deepcopy(self)
    output+=other
    return output

  if USE_COMPRESSION:
    # data compressed in memory properties, last dataset data is cached for better GUI response
    _data_zipped=None
    _data_dtype=float
    _data_shape=(0,)
    _cached_object=None
    _cached_data=None
    @property
    def data(self):
      if MRDataset._cached_object is self:
        return MRDataset._cached_data
      raw_bytes=zlib.decompress(self._data_zipped)
      data=frombuffer(raw_bytes, dtype=self._data_dtype).reshape(self._data_shape).copy()
      del raw_bytes
      MRDataset._cached_data=data
      MRDataset._cached_object=self
      return data
    @data.setter
    def data(self, data):
      self._data_zipped=zlib.compress(data.tobytes(), 1)
      self._data_dtype=data.dtype
      self._data_shape=data.shape
      MRDataset._cached_data=data
      MRDataset._cached_object=self

  ################## Properties for easy data access ##########################
  # return the size of the data stored in memory for this dataset
  @property
  def nbytes(self): return (len(self._data_zipped)+
                            self.xydata.nbytes+self.xtofdata.nbytes)
  @property
  def rawbytes(self): return (self.data.nbytes+self.xydata.nbytes+self.xtofdata.nbytes)

  if USE_COMPRESSION:
    @property
    def nbytes(self): return (len(self._data_zipped)+
                              self.xydata.nbytes+self.xtofdata.nbytes)
  else:
    nbytes=rawbytes

  @property
  def xdata(self): return self.xydata.mean(axis=0)

  @property
  def ydata(self): return self.xydata.mean(axis=1)

  @property
  def tofdata(self): return self.xtofdata.mean(axis=0)

  # coordinates corresponding to the data items
  @property
  def x(self): return arange(self.xydata.shape[1])

  @property
  def y(self): return arange(self.xydata.shape[0])

  @property
  def xy(self): return meshgrid(self.x, self.y)

  @property
  def tof(self): return (self.tof_edges[:-1]+self.tof_edges[1:])/2.

  @property
  def xtof(self): return meshgrid(self.tof, self.x)

  @property
  def lamda(self):
    v_n=self.dist_mod_det/self.tof*1e6 #m/s
    lamda_n=H_OVER_M_NEUTRON/v_n*1e10 #A
    return lamda_n

  @property
  def active_area_x(self):
    if self._active_area_x is None:
      return (0, self.xydata.shape[1])
    else:
      return self._active_area_x
  @active_area_x.setter
  def active_area_x(self, value):
    self._active_area_x=value

  @property
  def active_area_y(self):
    if self._active_area_y is None:
      return (0, self.xydata.shape[1])
    else:
      return self._active_area_y
  @active_area_y.setter
  def active_area_y(self, value):
    self._active_area_y=value

  def get_tth(self, dangle0=None, dpix=None):
    '''
    Return the tth values corresponding to each x-pixel.
    '''
    if dangle0 is None:
      dangle0=self.dangle0
    if dpix is None:
      dpix=self.dpix
    x=self.x
    grad_per_pixel=self.det_size_x/self.dist_sam_det/len(x)*180./pi
    tth0=(self.dangle-dangle0)-(x.shape[0]-dpix)*grad_per_pixel
    tth_range=x[::-1]*grad_per_pixel
    return tth0+tth_range

  def get_tthlamda(self, dangle0=None, dpix=None):
    '''
    Return tth and lamda values corresponding to x and tof.
    '''
    return meshgrid(self.lamda, self.get_tth(dangle0, dpix))

  tth=property(get_tth)
  tthlamda=property(get_tthlamda)

  @property
  def p(self):
    '''A attribute to quickly plot data in the qt console'''
    return AttributePloter(self, ['xdata', 'xydata', 'ydata', 'xtofdata', 'tofdata', 'data'])


class LRDataset(MRDataset):
  '''
  Representation of one measurement channel of the Liquids Reflectometer (REF_L).
  Inherits from MRDataset and overrides _collect_info() to read REF_L-specific
  HDF5 paths for metadata extraction.
  '''
  dpix=151 #: default direct beam pixel for REF_L

  def _collect_info(self, data):
    '''
    Extract header information from a REF_L HDF5 file.
    REF_L uses different NeXus paths for angles, distances, and slits
    compared to REF_M.

    :param h5py._hl.group.Group data:
    '''
    self.origin=(os.path.abspath(data.file.filename), data.name.lstrip('/'))
    self.logs=NiceDict()
    self.log_minmax=NiceDict()
    self.log_units=NiceDict()
    if 'DASlogs' in data:
      if 'proton_charge' in data['DASlogs']:
        stimes=data['DASlogs/proton_charge/time'][()]
        stimes=stimes[::10]
        stimesl, stimesc, stimesr=stimes[:-2], stimes[1:-1], stimes[2:]
        stimes=stimesc[((stimesr-stimesc)<1.)&((stimesc-stimesl)<1.)]
      else:
        stimes=None
      for motor, item in data['DASlogs'].items():
        if motor in ['proton_charge', 'frequency', 'Veto_pulse']:
          continue
        try:
          if 'units' in item['value'].attrs:
            units_attr=item['value'].attrs['units']
            self.log_units[motor]=units_attr.decode('utf8') if isinstance(units_attr, bytes) else str(units_attr)
          else:
            self.log_units[motor]=u''
          val=item['value'][()]
          if val.shape[0]==1:
            scalar=_log_scalar(val)
            self.logs[motor]=scalar
            self.log_minmax[motor]=(scalar, scalar)
          else:
            if stimes is not None:
              vtime=item['time'][()]
              sidx=searchsorted(vtime, stimes, side='right')
              sidx=maximum(sidx-1, 0)
              val=val[sidx]
            if len(val)==0:
              self.logs[motor]=NaN
              self.log_minmax[motor]=(NaN, NaN)
            elif not issubdtype(val.dtype, number):
              self.logs[motor]=_log_scalar(val)
              self.log_minmax[motor]=(_log_scalar(val), _log_scalar(val))
            else:
              self.logs[motor]=val.mean()
              self.log_minmax[motor]=(val.min(), val.max())
        except Exception:
          continue
      self.lambda_center=data['DASlogs/LambdaRequest/value'][()][0]

    # REF_L uses TwoTheta/readback for detector angle (not DANGLE)
    self.dangle=data['instrument/bank1/TwoTheta/readback'][()][0]
    self.dangle0=0. # REF_L has no DANGLE0 offset
    # REF_L uses Theta/readback for sample angle (not sample/SANGLE)
    self.sangle=data['instrument/bank1/Theta/readback'][()][0]

    self.proton_charge=data['proton_charge'][()][0]
    self.total_counts=data['total_counts'][()][0]
    self.total_time=data['duration'][()][0]

    # REF_L stores per-pixel distances; use mean for sample-detector distance
    self.dist_sam_det=data['instrument/bank1/distance'][()].mean()
    # REF_L moderator distance is negative (direction convention)
    self.dist_mod_det=-data['instrument/moderator/distance'][()][0]+self.dist_sam_det
    self.dist_mod_mon=self.dist_mod_det-2.75 # approximate monitor offset

    self.det_size_x=data['instrument/bank1/origin/shape/size'][()][0]
    self.det_size_y=data['instrument/bank1/origin/shape/size'][()][1]

    # REF_L slit widths are in DASlogs, not instrument/aperture paths
    try:
      self.slit1_width=data['DASlogs/S1HWidth/value'][()].mean()
    except KeyError:
      self.slit1_width=3.
    try:
      self.slit2_width=data['DASlogs/S2HWidth/value'][()].mean()
    except KeyError:
      self.slit2_width=2.
    try:
      self.slit3_width=data['DASlogs/S3HWidth/value'][()].mean()
    except KeyError:
      self.slit3_width=0.05
    try:
      self.slit4_width=data['DASlogs/S4HWidth/value'][()].mean()
    except KeyError:
      self.slit4_width=0.

    # REF_L slit distances from instrument/aperture (only 1 and 2 are reliably present)
    try:
      self.slit1_dist=-data['instrument/aperture1/distance'][()][0]*1000.
    except KeyError:
      self.slit1_dist=2600.
    try:
      self.slit2_dist=-data['instrument/aperture2/distance'][()][0]*1000.
    except KeyError:
      self.slit2_dist=2019.
    # Slit 3 and 4 distances may not be present in REF_L files
    try:
      self.slit3_dist=-data['instrument/aperture3/distance'][()][0]*1000.
    except KeyError:
      self.slit3_dist=714.
    try:
      self.slit4_dist=-data['instrument/aperture4/distance'][()][0]*1000.
    except KeyError:
      self.slit4_dist=500.

    self.experiment=str(data['experiment_identifier'][()][0])
    self.number=int(data['run_number'][()][0])
    try:
      self.merge_warnings=str(data['SNSproblem_log_geom/data'][()][0])
    except KeyError:
      self.merge_warnings=''

    # Active area from detector geometry file
    try:
      detector_id_raw=data['instrument/SNSgeometry_file_name'][()][0]
      detector_id=detector_id_raw.decode('utf-8') if isinstance(detector_id_raw, bytes) else str(detector_id_raw)
      if detector_id in instrument.DETECTOR_REGION:
        self.active_area_x=instrument.DETECTOR_REGION[detector_id][0]
        self.active_area_y=instrument.DETECTOR_REGION[detector_id][1]
    except KeyError:
      pass

  def _collect_info_h5(self, data):
    '''
    Extract header information from a modern .nxs.h5 REF_L file.
    Angles, wavelength, and slit widths from DASlogs.
    Distances and geometry from settings.json (date-indexed).

    :param h5py._hl.group.Group data:
    '''
    self.origin=(os.path.abspath(data.file.filename), data.name.lstrip('/'))
    self.logs=NiceDict()
    self.log_minmax=NiceDict()
    self.log_units=NiceDict()

    # Read DASlogs
    if 'DASlogs' in data:
      if 'proton_charge' in data['DASlogs']:
        stimes=data['DASlogs/proton_charge/time'][()]
        stimes=stimes[::10]
        stimesl, stimesc, stimesr=stimes[:-2], stimes[1:-1], stimes[2:]
        stimes=stimesc[((stimesr-stimesc)<1.)&((stimesc-stimesl)<1.)]
      else:
        stimes=None
      for motor, item in data['DASlogs'].items():
        if motor in ['proton_charge', 'frequency', 'Veto_pulse']:
          continue
        try:
          if 'units' in item['value'].attrs:
            units_attr=item['value'].attrs['units']
            self.log_units[motor]=units_attr.decode('utf8') if isinstance(units_attr, bytes) else str(units_attr)
          else:
            self.log_units[motor]=u''
          val=item['value'][()]
          if val.shape[0]==1:
            scalar=_log_scalar(val)
            self.logs[motor]=scalar
            self.log_minmax[motor]=(scalar, scalar)
          else:
            if stimes is not None:
              vtime=item['time'][()]
              sidx=searchsorted(vtime, stimes, side='right')
              sidx=maximum(sidx-1, 0)
              val=val[sidx]
            if len(val)==0:
              self.logs[motor]=NaN
              self.log_minmax[motor]=(NaN, NaN)
            elif not issubdtype(val.dtype, number):
              self.logs[motor]=_log_scalar(val)
              self.log_minmax[motor]=(_log_scalar(val), _log_scalar(val))
            else:
              self.logs[motor]=val.mean()
              self.log_minmax[motor]=(val.min(), val.max())
        except Exception:
          continue

    # REF_L raw motor angles (all three stored for diagnostics)
    self.thi=_get_daslog_value(data, 'BL4B:Mot:thi.RBV',
                  fallback_key='thi', default=0.0)
    self.ths=_get_daslog_value(data, 'BL4B:Mot:ths.RBV',
                  fallback_key='ths', default=0.0)
    self.tthd=_get_daslog_value(data, 'BL4B:Mot:tthd.RBV',
                   fallback_key='tthd', default=0.0)
    # Map to quicknxsv1 attribute names
    self.dangle=self.tthd    # detector arm two-theta
    self.sangle=self.ths     # sample angle
    self.dangle0=0.0         # REF_L has no DANGLE0 in DASlogs

    # Wavelength and frequency
    self.lambda_center=_get_daslog_value(data, 'BL4B:Det:TH:BL:Lambda',
                            fallback_key='LambdaRequest', default=None)
    if self.lambda_center is None:
      warn('No wavelength in DASlogs; using 3.37 A')
      self.lambda_center=3.37
    self.chopper_speed=_get_daslog_value(data, 'BL4B:Det:TH:BL:Frequency',
                            fallback_key='SpeedRequest1', default=60.0)

    # REF_L slit widths
    self.s1Y=_get_daslog_value(data, 'BL4B:Mot:s1:Y:Gap:Readback',
                  fallback_key='s1:Y:Gap', default=0.0)
    self.s1X=_get_daslog_value(data, 'BL4B:Mot:s1:X:Gap:Readback',
                  fallback_key='s1:X:Gap', default=0.0)
    self.siY=_get_daslog_value(data, 'BL4B:Mot:si:Y:Gap:Readback',
                  fallback_key='si:Y:Gap', default=0.0)
    self.siX=_get_daslog_value(data, 'BL4B:Mot:si:X:Gap:Readback',
                  fallback_key='si:X:Gap', default=0.0)
    self.xi=_get_daslog_value(data, 'BL4B:Mot:xi.RBV',
                 fallback_key='xi', default=0.0)
    # Map to quicknxsv1 slit attribute names
    self.slit1_width=self.s1Y
    self.slit2_width=self.siY

    # Distances and geometry from date-indexed settings.json
    settings=_read_instrument_settings('ref_l', data)
    self.dist_sam_det=settings['sample-det-distance']
    self.dist_mod_det=settings['source-det-distance']
    self.dist_mod_mon=self.dist_mod_det-2.75
    n_x=settings['number-of-x-pixels']
    n_y=settings['number-of-y-pixels']
    pixel_size_mm=settings['pixel-width']
    self.det_size_x=n_x*pixel_size_mm*1e-3
    self.det_size_y=n_y*pixel_size_mm*1e-3
    self.dpix=151
    self.xi_reference=settings.get('xi-reference', 445)
    self.s1_sample_distance=settings.get('s1-sample-distance', 1485)

    # Slit distances
    self.slit1_dist=self.s1_sample_distance
    self.slit2_dist=self.xi_reference-self.xi  # si distance derived from xi

    # Standard metadata
    self.proton_charge=data['proton_charge'][()][0]
    self.total_counts=data['total_counts'][()][0]
    self.total_time=data['duration'][()][0]
    self.experiment=_decode(data['experiment_identifier'][()][0])
    self.number=int(data['run_number'][()][0])
    self.merge_warnings=''

  @staticmethod
  def _apply_dead_time_correction(data, tof_edges, dead_time=4.2, paralyzable=True):
    '''
    Apply dead-time correction using bank_error_events (BL4B only).

    Gracefully returns unity correction when bank_error_events is absent,
    proton_charge has no non-zero pulses, or proton_charge log is missing.

    :param h5py._hl.group.Group data: HDF5 entry group
    :param array tof_edges: TOF bin edges in µs
    :param float dead_time: detector dead time in µs (default 4.2 for BL4B)
    :param bool paralyzable: if True, use Lambert W model (default for BL4B)
    :returns: array of correction factors, one per TOF bin
    '''
    from scipy.special import lambertw

    n_bins=len(tof_edges)-1
    unity=ones(n_bins)

    # Guard: skip if bank_error_events is absent
    if 'bank_error_events/event_time_offset' not in data:
      warn('No bank_error_events in file — skipping dead-time correction')
      return unity

    # Guard: skip if bank1_events is absent
    if 'bank1_events/event_time_offset' not in data:
      return unity

    e_offset=data['bank1_events/event_time_offset'][()]
    err_offset=data['bank_error_events/event_time_offset'][()]

    # Guard: skip if proton_charge is missing
    try:
      pc=data['DASlogs/proton_charge/value'][()]
    except KeyError:
      warn('No proton_charge in DASlogs — skipping dead-time correction')
      return unity

    n_pulses=count_nonzero(pc)
    if n_pulses==0:
      return unity

    # Histogram all detector triggers (good + error)
    counts, _=histogram(e_offset, bins=tof_edges)
    err_counts, _=histogram(err_offset, bins=tof_edges)
    total=(counts+err_counts).astype(float)

    # Rate per pulse per TOF bin
    tof_step=diff(tof_edges)
    rate=total/n_pulses

    # Apply correction model
    with errstate(divide='ignore', invalid='ignore'):
      if paralyzable:
        # Lambert W correction (paralyzable detector model)
        b=-real(lambertw(-rate*dead_time/tof_step))
        dtc=b/(rate*dead_time/tof_step)
      else:
        # Non-paralyzable model
        dtc=1.0/(1.0-rate*dead_time/tof_step)
      dtc=nan_to_num(dtc, nan=1.0, posinf=1.0, neginf=1.0)

    # Clamp to reasonable range
    dtc=clip(dtc, 1.0, 10.0)

    return dtc

  @classmethod
  @log_call
  def from_event_h5(cls, data, read_options,
                    callback=None, callback_offset=0., callback_scaling=1.,
                    total_duration=None, tof_overwrite=None):
    '''
    Load data from a modern .nxs.h5 event NeXus file for REF_L.
    Calls the parent MRDataset.from_event_h5() then applies dead-time correction.

    :param h5py._hl.group.Group data: HDF5 entry group
    :param dict read_options: Options controlling binning
    '''
    output=MRDataset.from_event_h5.__func__(cls, data, read_options,
                                            callback=callback,
                                            callback_offset=callback_offset,
                                            callback_scaling=callback_scaling,
                                            total_duration=total_duration,
                                            tof_overwrite=tof_overwrite)
    if output is None:
      return None

    # Apply dead-time correction (BL4B only)
    dtc=cls._apply_dead_time_correction(data, output.tof_edges)
    output.data=output.data*dtc[newaxis, newaxis, :]
    # Recompute projections
    output.xydata=output.data.sum(axis=2).transpose().astype(float)
    output.xtofdata=output.data.sum(axis=1).astype(float)
    return output


def _filter_events_by_polarization(data):
  '''
  Separate events into polarization channels using SF1 (polarizer) and
  SF2 (analyzer) time-series logs from DASlogs.

  :param h5py._hl.group.Group data: HDF5 entry group
  :returns: dict {cross_section_name: (event_ids, event_tofs, proton_charge)}
            or None. ``proton_charge`` is the charge integrated over that
            channel's pulses (None if the proton_charge log is unavailable).
  '''
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
      warn('%s missing — cannot filter events; treating as unpolarized'%required)
      return None

  # Read flipper state logs
  try:
    sf1_values=data['DASlogs/SF1/value'][()]
    sf1_times=data['DASlogs/SF1/time'][()]
  except KeyError:
    warn('DASlogs/SF1/value or SF1/time missing — treating as unpolarized')
    return None

  sf2_single=True
  sf2_values=None
  sf2_times=None
  if 'DASlogs/SF2' in data:
    try:
      sf2_values=data['DASlogs/SF2/value'][()]
      sf2_times=data['DASlogs/SF2/time'][()]
      sf2_single=(len(unique(sf2_values))==1)
    except KeyError:
      warn('DASlogs/SF2/value or SF2/time missing — assuming no analyzer')
      sf2_single=True

  # Read pulse and event data
  event_tz=data['bank1_events/event_time_zero'][()]
  event_idx=array(data['bank1_events/event_index'][()], dtype=int)
  event_id=data['bank1_events/event_id'][()]
  event_tof=data['bank1_events/event_time_offset'][()]

  # Assign each pulse to SF1 state
  pulse_sf1_idx=searchsorted(sf1_times, event_tz, side='right')-1
  pulse_sf1_idx=clip(pulse_sf1_idx, 0, len(sf1_values)-1)
  pulse_sf1=sf1_values[pulse_sf1_idx]

  if not sf2_single:
    pulse_sf2_idx=searchsorted(sf2_times, event_tz, side='right')-1
    pulse_sf2_idx=clip(pulse_sf2_idx, 0, len(sf2_values)-1)
    pulse_sf2=sf2_values[pulse_sf2_idx]
  else:
    pulse_sf2=zeros_like(pulse_sf1)

  # Apply veto filtering if veto logs are available
  veto_mask=ones(len(event_tz), dtype=bool)  # True = keep pulse
  for veto_key in ['DASlogs/SF1_Veto', 'DASlogs/SF2_Veto']:
    if veto_key in data:
      try:
        veto_vals=data[veto_key+'/value'][()]
        veto_times=data[veto_key+'/time'][()]
        veto_idx=searchsorted(veto_times, event_tz, side='right')-1
        veto_idx=clip(veto_idx, 0, len(veto_vals)-1)
        # Veto=1 means flipper is in transition — exclude these pulses
        veto_mask&=(veto_vals[veto_idx]==0)
      except KeyError:
        warn('%s/value or time missing — skipping veto filter'%veto_key)
    else:
      debug('%s not present — no veto filtering for this flipper'%veto_key)

  # Per-channel proton charge: integrate the proton_charge log over each
  # channel's pulses, matching Mantid MRFilterCrossSections which normalizes
  # every cross-section by the charge accrued while its SF-state was active.
  # Without this, each channel inherits the FULL-run charge and polarized
  # reflectivity comes out low by the channel's beam-time fraction (the long-
  # standing "v1-vs-Mantid deficit"; see plan/v1-vs-mantid-deficit-rootcause.md).
  pulse_pc=None
  try:
    pc_values=data['DASlogs/proton_charge/value'][()]
    pc_times=data['DASlogs/proton_charge/time'][()]
    pc_pidx=clip(searchsorted(pc_times, event_tz, side='right')-1, 0, len(pc_values)-1)
    pulse_pc=pc_values[pc_pidx]
  except KeyError:
    warn('DASlogs/proton_charge missing — per-channel charge unavailable; '
         'channels will inherit the full-run charge')

  # Combine SF1 and SF2 into cross-section labels
  state_names={(0, 0): 'Off_Off', (1, 0): 'On_Off',
               (0, 1): 'Off_On',  (1, 1): 'On_On'}

  channels={}
  for (s1, s2), name in state_names.items():
    mask=(pulse_sf1==s1)&(pulse_sf2==s2)&veto_mask
    state_pulses=where(mask)[0]
    if len(state_pulses)==0:
      continue
    # Charge integrated over this state's pulses (None -> caller keeps full run)
    chan_pc=float(pulse_pc[state_pulses].sum()) if pulse_pc is not None else None
    event_masks=[]
    for pi in state_pulses:
      ev_start=event_idx[pi]
      ev_end=event_idx[pi+1] if pi+1<len(event_idx) else len(event_id)
      if ev_start<ev_end:
        event_masks.append(arange(ev_start, ev_end))
    if event_masks:
      all_idx=concatenate(event_masks)
      channels[name]=(event_id[all_idx], event_tof[all_idx], chan_pc)

  if len(channels)==0:
    warn('Polarization filtering produced no channels — '
         'all events may be in veto periods; treating as unpolarized')
    return None

  return channels


def is_analyzer_in(position, trans_position, start_time_str):
    """
        Determine whether the analyzer is in.
        The analyzer position has changed in August 2017.
        Uses ANALYZER_IN and NEW_ANALYZER_IN from the instrument config (REF_M only).

        :param position: position of the analyzer lift
        :param trans_position: position of the analyzer translation
        :param start_time_str: time as a string
    """
    analyzer_in=instrument.ANALYZER_IN
    new_analyzer_in=instrument.NEW_ANALYZER_IN
    result=abs(position-analyzer_in[0])<analyzer_in[1]
    try:
        date_str = start_time_str.split('T')[0]
        parts_str = date_str.split('-')
        year_month_int = int("%s%s" % (parts_str[0], parts_str[1]))
        if year_month_int >= 201708:
            result=abs(trans_position-new_analyzer_in[0])<new_analyzer_in[1]
    except Exception:
        warn("Problem parsing start time: use more recent definition for analyzer position")
        result=abs(trans_position-new_analyzer_in[0])<new_analyzer_in[1]
    return result

def time_from_header(filename, nxs=None):
  '''
  Read just an nxs header to get the time of a measurement in seconds.

  :param str filename: Path to nxs file
  '''
  if nxs is None:
    try:
      nxs=h5py.File(filename, mode='r')
    except IOError:
      return None
    close=True
  else:
    close=False
  stime=1.e30
  etime=0.
  for item in nxs.values():
    if not isinstance(item, h5py.Group):
      continue
    if 'start_time' not in item or 'end_time' not in item:
      continue
    sstr=item['start_time'][()][0].decode()
    estr=item['end_time'][()][0].decode()
    if '.' in sstr:
      start_str, start_sub=sstr.split('.', 1)
      start_sub=start_sub.split('-')[0]
      start_time=mktime(strptime(start_str, '%Y-%m-%dT%H:%M:%S'))+float('.'+start_sub)
      end_str, end_sub=estr.split('.', 1)
      end_sub=start_sub.split('-')[0]
      end_time=mktime(strptime(end_str, '%Y-%m-%dT%H:%M:%S'))+float('.'+end_sub)
    else:
      start_str, start_sub=sstr.rsplit('-', 1)
      start_time=mktime(strptime(start_str, '%Y-%m-%dT%H:%M:%S'))
      end_str, end_sub=estr.rsplit('-', 1)
      end_time=mktime(strptime(end_str, '%Y-%m-%dT%H:%M:%S'))
    stime=_builtins.min(stime, start_time)
    etime=_builtins.max(etime, end_time)
  if close:
    nxs.close()
  return etime-stime

def _listdir_with_timeout(path, timeout=10.0):
    '''
    Call os.listdir(path) in a daemon thread and return the result within
    *timeout* seconds.  Returns None if the call does not complete in time or
    raises OSError (e.g. path does not exist).

    This is the safe replacement for a bare os.listdir() over sshfs.  When a
    FUSE mount is stale the kernel puts the calling process into D-state
    (uninterruptible sleep) so SIGALRM cannot interrupt it.  Running the call
    in a daemon thread lets the main thread proceed after the deadline while the
    stuck thread waits for FUSE to recover in the background.

    :param str path: Directory to list.
    :param float timeout: Wall-clock deadline in seconds (default 10.0).
    :returns: List of entry names, or None on timeout/error.
    '''
    import threading
    result = []
    error = []
    done = threading.Event()

    def _work():
        try:
            result.extend(os.listdir(path))
        except OSError as exc:
            error.append(exc)
        finally:
            done.set()

    t = threading.Thread(target=_work, daemon=True)
    t.start()
    if done.wait(timeout=timeout):
        return result if not error else None
    # Timed out — the daemon thread is stuck (likely D-state FUSE wait).
    # Return None and let the thread recover on its own.
    return None


def _find_file_in_ipts(data_base, candidates, timeout=30):
    '''
    Search for one or more candidate filenames across all IPTS directories in
    data_base using parallel os.path.isfile checks.

    On sshfs mounts a glob with a wildcard at the IPTS level must enumerate
    every directory, which can take over a minute.  Checking os.path.isfile
    for a specific filename in each IPTS takes ~0.2 s per call but runs in
    parallel so the whole search completes in 1–5 s regardless of how many
    IPTS directories exist.

    :param str data_base: Instrument root (e.g. '/SNS/REF_M').
    :param list candidates: Ordered list of (subdir, filename) tuples to check,
        e.g. [('nexus', 'REF_M_40205.nxs.h5'), ('data', 'REF_M_40205_histo.nxs')].
        The first tuple whose file exists in any IPTS dir wins.
    :param int timeout: Wall-clock timeout in seconds (default 30).
    :returns: Absolute path string or None.
    '''
    all_entries = _listdir_with_timeout(data_base, timeout=10.0)
    if not all_entries:
        return None
    ipts_dirs = [d for d in all_entries if d.startswith('IPTS')]
    if not ipts_dirs:
        return None

    # Sort descending by IPTS number so recently-allocated proposals (which hold
    # the newest run numbers) are checked first — the common case hits in batch 1.
    def _ipts_num(d):
        try:
            return int(d.split('-')[1])
        except (IndexError, ValueError):
            return 0
    ipts_dirs = sorted(ipts_dirs, key=_ipts_num, reverse=True)

    def check(ipts_dir):
        for subdir, filename in candidates:
            path = os.path.join(data_base, ipts_dir, subdir, filename)
            try:
                if os.path.isfile(path):
                    return path
            except OSError:
                pass
        return None

    # Limit to 4 concurrent workers: each os.path.isfile over rclone VFS opens
    # a new SFTP session via the SSH ControlMaster.  analysis.sns.gov enforces
    # MaxSessions (typically 10) per connection; 20 workers burst well past that
    # limit, causing "server unexpectedly closed connection" errors and password
    # prompts flooding the terminal.  4 workers stay safely within the limit.
    found = None
    with ThreadPoolExecutor(max_workers=4) as executor:
        futs = {executor.submit(check, d): d for d in ipts_dirs}
        try:
            for fut in as_completed(futs, timeout=timeout):
                res = fut.result()
                if res:
                    found = res
                    for f in futs:
                        f.cancel()
                    break
        except Exception:
            pass
    return found


def locate_file(number, histogram=True, old_format=False, verbose=True):
    '''
    Search the data folders for a specific file number.

    Uses parallel os.path.isfile checks across IPTS directories instead of a
    wildcard glob, which is prohibitively slow on sshfs mounts (>80 s for a
    single glob vs ~1–5 s for the parallel approach).

    :param int number: Run number
    :param bool histogram: If True, prefer *_histo.nxs (default True).
    :param bool old_format: If True, search the old NeXus directory layout.
    :param bool verbose: Log the search attempt (default True).
    :returns: Absolute path string or None.
    '''
    if verbose:
      info('Trying to locate file number %s...'%number)
    instr = instrument.NAME  # e.g. 'REF_M' or 'REF_L'

    if old_format:
      # Old layout: /SNS/REF_X/YYYY_N_BL_TYPE/NeXus/REF_X_NNNNN*.nxs
      # Still use glob for this rare case — the old directory tree is small
      search = glob(os.path.join(instrument.data_base,
                    instrument.OLD_BASE_SEARCH % (number, number) + u'.nxs'))
      return search[0] if search else None

    if histogram:
      candidates = [
          ('data',  u'%s_%s_histo.nxs' % (instr, number)),
          ('nexus', u'%s_%s.nxs.h5'    % (instr, number)),
      ]
    else:
      # Event mode: prefer modern .nxs.h5, fall back to legacy event.nxs
      candidates = [
          ('nexus', u'%s_%s.nxs.h5'    % (instr, number)),
          ('data',  u'%s_%s_event.nxs'  % (instr, number)),
      ]

    return _find_file_in_ipts(instrument.data_base, candidates)

class Reflectivity(object, metaclass=OptionsDocMeta):
  """
  Extraction of reflectivity from MRDatatset object storing all data
  and options used for the extraction process.
  """

  DEFAULT_OPTIONS=dict(
       x_pos=None,
       x_width=9,
       y_pos=102,
       y_width=204,
       bg_pos=80,
       bg_width=40,
       tth=None,
       dpix=None,
       scale=1.,
       sample_length=10.,
       extract_fan=False,
       subtract_background=True,
       normalization=None,
       bg_tof_constant=False,
       bg_poly_regions=None,
       bg_scale_xfit=False,
       bg_scale_factor=1.,
       sensitivity_correction=None,
       P0=0,
       PN=0,
       number='0',
       gisans_gridy=50,
       gisans_gridz=50,
       gisans_no_DP=True,
       )
  _OPTIONS_DESCRTIPTION=dict(
       x_pos='X-pixel position of the reflected beam on the detector',
       x_width='Pixel width of the area used to extract the intensity',
       y_pos='Y-pixel position of the are used to extract the intensity',
       y_width='Pixel width in Y-direction to be used to extract the intensity',
       bg_pos='X-pixel position of the background subtraction area (center)',
       bg_width='X-pixel width of the background subtraction area',
       tth='Two Theta of the detector arm',
       dpix='X-pixel position of the direct beam at tth=0',
       scale='Scaling factor for the reflectivity',
       sample_length='Length of the sample in mm, used to calculate the Q-resolution',
       extract_fan='Treat every x-pixel separately and join the data afterwards',
       subtract_background='Subtract the background-vs-TOF from the intensity (the v2/QuickNXS-4.x "BG X" toggle; default True). Set False to match a reference reduced with BG X off.',
       normalization='another Reflectivity object used for normalization',
       bg_tof_constant='treat background to be independent of wavelength for better statistics',
       bg_poly_regions='use polygon regions in x/λ to determine which points to use for the background',
       bg_scale_xfit='use a linear fit on x-axes projection to scale the background',
       bg_scale_factor='scale the background by this constant before subtraction',
       sensitivity_correction='Detector sensitivity correction to be used',
       P0='Number of points to remove from the low-Q side of the reflectivity',
       PN='Number of points to remove from the high-Q side of the reflectivity',
       number='Index of the origin dataset used for naming etc. when exported',
       gisans_gridy='When extracting GISANS data, this is the number of pixels in Qz',
       gisans_gridz='When extracting GISANS data, this is the number of pixels in Qy',
       gisans_no_DP='Remove the ToF bin which contains the direct pulse background',
       )

  @log_input
  def __init__(self, dataset, **options):
    all_options=dict(Reflectivity.DEFAULT_OPTIONS)
    for key, value in options.items():
      if key not in all_options:
        raise ValueError("%s is not a known option parameter"%key)
      all_options[key]=value
    self.options=all_options
    self.origin=dataset.origin
    self.read_options=dataset.read_options
    if self.options['x_pos'] is None:
      # if nor x_pos is given, use the value from the dataset
      rad_per_pixel=dataset.det_size_x/dataset.dist_sam_det/dataset.xydata.shape[1]
      self.options['x_pos']=dataset.dpix-dataset.sangle/180.*pi/rad_per_pixel
    if self.options['tth'] is None:
      self.options['tth']=dataset.dangle-dataset.dangle0
    if self.options['dpix'] is None:
      self.options['dpix']=dataset.dpix
    self.lambda_center=dataset.lambda_center
    self.slits=[(dataset.slit1_width, dataset.slit1_dist),
                (dataset.slit2_width, dataset.slit2_dist),
                (dataset.slit3_width, dataset.slit3_dist)]
    if hasattr(dataset, 'slit4_width'):
      self.slits.append((dataset.slit4_width, dataset.slit4_dist))

    if all_options['extract_fan'] and all_options['normalization'] is not None:
      self._calc_fan(dataset)
    else:
      self._calc_normal(dataset)

  def __repr__(self):
    if type(self.origin) is list:
      fnames='+'.join([os.path.basename(item[0]) for item in self.origin])
      output='<Reflectivity[%i] "%s/%s"'%(len(self.Q), fnames,
                                        self.origin[0][1])
    else:
      output='<Reflectivity[%i] "%s/%s"'%(len(self.Q), os.path.basename(self.origin[0]),
                                        self.origin[1])
    if self.options['normalization'] is None:
      output+=' NOT normalized'
    elif self.options['extract_fan']:
      output+=' FAN'
    output+='>'
    return output

  def _repr_html_(self):
    '''Object representation for IPython'''
    output='<b>%s</b> Object:\n<table border="1">\n'%self.__class__.__name__
    try:
      output+='<tr><td>#points</td><td>%i</td></tr>\n'%(len(self.Q))
    except AttributeError:
      output+='<tr><td>#points</td><td>%s</td></tr>\n'%(repr(self.Qz.shape))
    if type(self.origin) is list:
      output+='<tr><td>State</td><td>%s</td></tr>\n'%(self.origin[0][1])
      for i, item in enumerate(self.origin):
          output+='<tr><td>origin[%i]</td><td>%s</td></tr>\n'%(i, item[0])
    else:
      output+='<tr><td>State</td><td>%s</td></tr>\n'%(self.origin[1])
      output+='<tr><td>origin</td><td>%s</td></tr>\n'%(self.origin[0])
    output+='</table>See .info attribute for detailed description.\n'
    return output

  @property
  def info(self):
    output='<table border="1">\n'
    try:
      output+='<tr><td>#points</td><td>%i</td></tr>\n'%(len(self.Q))
    except AttributeError:
      output+='<tr><td>#points</td><td>%s</td></tr>\n'%(repr(self.Qz.shape))
    if type(self.origin) is list:
      output+='<tr><td>State</td><td>%s</td></tr>\n'%(self.origin[0][1])
      for i, item in enumerate(self.origin):
          output+='<tr><td>origin[%i]</td><td>%s</td></tr>\n'%(i, item[0])
    else:
      output+='<tr><td>State</td><td>%s</td></tr>\n'%(self.origin[1])
      output+='<tr><td>origin</td><td>%s</td></tr>\n'%(self.origin[0])
    output+='</table><table border="1">\n'
    output+='<tr><th>Option</th><th>Value</th></tr>\n'
    for key, value in sorted(self.options.items()):
      if key=='normalization' and value is not None:
        output+='<tr><td>%s</td><td>%s</td></tr>\n'%(key,
                                    value.origin[0])
      else:
        output+='<tr><td>%s</td><td>%s</td></tr>\n'%(key,
                                    repr(value).replace('<', '[').replace('>', ']'))
    output+='</table>'
    return StringRepr('self.options='+repr(self.options), output)


  @log_call
  def _correct_sensitivity(self, data):
    if self.options['sensitivity_correction'] in DETECTOR_SENSITIVITY:
      return data/DETECTOR_SENSITIVITY[self.options['sensitivity_correction']][:, :, newaxis]
    elif self.options['sensitivity_correction']=='polynomial':
      # use polynomial form to generate sensitivity map
      poly_params=_get_instrument_config('POLY_CORR_PARAMS')
      if poly_params is None:
        warn('No polynomial sensitivity correction parameters available for this instrument')
        return data
      X, Y=meshgrid(arange(data.shape[0]), arange(data.shape[1]))
      X, Y=X.T.astype(float), Y.T.astype(float)
      ax, ay, bx, by, c=poly_params
      Isens=ax*X**2+ay*Y**2+bx*X+by*Y+c
      Isens/=Isens.mean()
      DETECTOR_SENSITIVITY[self.options['sensitivity_correction']]=Isens
      return data/Isens[:, :, newaxis]
    else:
      raise NotImplementedError('sensitivity correction %s not known'%self.options['sensitivity_correction'])

  #############################################################################

  @log_call
  def _calc_normal(self, dataset):
    """
    Extract reflectivity from 3D dataset I(x,y,ToF).
    Uses a window in x and y to filter the 3D data and than sums all I values
    for each ToF channel. Qz is calculated using the x window center position
    together with the tth-bank and direct pixel values.
    Error is also calculated and all intermediate steps are stored in the object
    (scaled and unscaled intensity and background).

    :param quicknxs.qreduce.MRDataset dataset: The dataset to use for extraction
    """
    tof_edges=dataset.tof_edges
    data=dataset.data
    if self.options['sensitivity_correction'] is not None:
      data=self._correct_sensitivity(data)
    x_pos=self.options['x_pos']
    x_width=self.options['x_width']
    y_pos=self.options['y_pos']
    y_width=self.options['y_width']
    scale=1./dataset.proton_charge # scale by user factor

    # Get regions in pixels as integers
    reg=list(map(lambda item: int(round(item)),
            [x_pos-x_width/2., x_pos+x_width/2.+1,
             y_pos-y_width/2., y_pos+y_width/2.+1]))
    debug('Reflectivity region: %s'%str(reg))

    # get incident angle of reflected beam
    rad_per_pixel=dataset.det_size_x/dataset.dist_sam_det/dataset.xydata.shape[1]
    relpix=self.options['dpix']-x_pos
    tth=(self.options['tth']*pi/180.+relpix*rad_per_pixel)
    self.ai=tth/2.
    # calculate resolution from slits, sample size and incident angle
    dai=self.get_resolution()
    debug('alpha_i=%s+/-%s'%(self.ai, dai))

    self._calc_bg(dataset)

    # restrict the intensity and background data to the given regions
    Idata=data[reg[0]:reg[1], reg[2]:reg[3], :]
    # calculate region size for later use
    size_I=float((reg[3]-reg[2])*(reg[1]-reg[0]))
    # calculate ROI intensities and normalize by number of points
    self.Iraw=Idata.sum(axis=0).sum(axis=0)
    self.I=self.Iraw/(size_I/scale)
    self.dIraw=sqrt(self.Iraw)
    self.dI=self.dIraw/(size_I/scale)
    debug("Intensity scale is %s/%s=%s"%(scale, size_I, scale/size_I))

    v_edges=dataset.dist_mod_det/tof_edges*1e6 #m/s
    lamda_edges=H_OVER_M_NEUTRON/v_edges*1e10 #A
    # store the ToF as well for comparison etc.
    self.tof=(tof_edges[:-1]+tof_edges[1:])/2. # µs
    self.lamda=(lamda_edges[:-1]+lamda_edges[1:])/2.
    # resolution for lambda is digital range with equal probability
    # therefore it is the bin size divided by sqrt(12)
    self.dlamda=abs(lamda_edges[:-1]-lamda_edges[1:])/sqrt(12)

    # for reflectivity use Q as x
    self.Q=4.*pi/self.lamda*sin(self.ai)
    # error propagation from lambda and angular resolution
    self.dQ=4*pi*sqrt((self.dlamda/self.lamda**2*sin(self.ai))**2+
                      (cos(self.ai)*dai/self.lamda)**2)
    debug("Q=%s"%repr(self.Q))
    # finally scale reflectivity by the given factor and beam width
    if self.options['subtract_background']:
      self.Rraw=(self.I-self.BG) # used for normalization files
    else:
      self.Rraw=array(self.I) # BG X off: keep raw intensity
    self.dRraw=sqrt(self.dI**2+self.dBG**2)
    if self.ai>0.0002:
      sin_scale=0.005/sin(self.ai) # scale by beam-footprint
    else:
      sin_scale=1.
    self.R=sin_scale*self.options['scale']*self.Rraw
    self.dR=sin_scale*self.options['scale']*self.dRraw

    if self.options['normalization']:
      norm=self.options['normalization']
      debug("Performing normalization from %s"%norm)
      idxs=norm.Rraw>0.
      self.dR[idxs]=sqrt(
                   (self.dR[idxs]/norm.Rraw[idxs])**2+
                   (self.R[idxs]/norm.Rraw[idxs]**2*norm.dRraw[idxs])**2
                   )
      self.R[idxs]/=norm.Rraw[idxs]
      self.R[logical_not(idxs)]=0.
      self.dR[logical_not(idxs)]=0.

  @log_call
  def _calc_fan(self, dataset):
    """
    Extract reflectivity from 4D dataset (x,y,ToF,I).
    Uses a window in x and y to filter the 4D data
    and than sums all I values for each ToF channel.

    In contrast to calc_reflectivity this function assumes
    that a brought region reflected from a bend sample is
    analyzed, so each x line corresponds to different alpha i
    values.

    :param quicknxs.qreduce.MRDataset dataset: The dataset to use for extraction
    """
    tof_edges=dataset.tof_edges
    data=dataset.data
    if self.options['sensitivity_correction'] is not None:
      data=self._correct_sensitivity(data)
    x_pos=self.options['x_pos']
    x_width=self.options['x_width']
    y_pos=self.options['y_pos']
    y_width=self.options['y_width']
    scale=1./dataset.proton_charge # scale by user factor

    reg=list(map(lambda item: int(round(item)),
            [x_pos-x_width/2., x_pos+x_width/2.+1,
             y_pos-y_width/2., y_pos+y_width/2.+1]))
    debug('Reflectivity region: %s'%str(reg))

    rad_per_pixel=dataset.det_size_x/dataset.dist_sam_det/dataset.xydata.shape[1]
    Idata=data[reg[0]:reg[1], reg[2]:reg[3], :]
    x_region=arange(reg[0], reg[1])
    relpix=self.options['dpix']-x_region
    tth=(self.options['tth']*pi/180.+relpix*rad_per_pixel)
    ai=tth/2.
    self.ai=ai.mean()
    dai_rel=self.get_resolution()/self.ai
    debug("Intensity scale is %s"%(scale))
    debug('alpha_i=%s'%repr(ai))

    self._calc_bg(dataset)

    v_edges=dataset.dist_mod_det/tof_edges*1e6 #m/s
    lamda_edges=H_OVER_M_NEUTRON/v_edges*1e10 #A
    self.tof=(tof_edges[:-1]+tof_edges[1:])/2. # µs
    self.lamda=(lamda_edges[:-1]+lamda_edges[1:])/2.
    # resolution for lambda is digital range with equal probability
    # therefore it is the bin size divided by sqrt(12)
    self.dlamda=abs(lamda_edges[:-1]-lamda_edges[1:])/sqrt(12)

    # calculate ROI intensities and normalize by number of points
    # still keeping it as 2D dataset
    self.Iraw=Idata.sum(axis=1)
    I=self.Iraw/(reg[3]-reg[2])*scale  # noqa: E741
    self.dIraw=sqrt(self.Iraw)
    dI=self.dIraw/(reg[3]-reg[2])*scale
    # For comparison store intensity summed over whole area
    self.I=I.sum(axis=0)/(reg[1]-reg[0])
    self.dI=sqrt((dI**2).sum(axis=0))/(reg[1]-reg[0])

    R=(I-self.BG[newaxis, :])*self.options['scale']
    dR=sqrt(dI**2+(self.dBG**2)[newaxis, :])*self.options['scale']
    if self.ai>0.0002:
      sin_scale=0.005/sin(self.ai) # scale by beam-footprint
      R*=sin_scale
      dR*=sin_scale

    norm=self.options['normalization']
    normR=where(norm.Rraw>0, norm.Rraw, 1.)
    # normalize each line by the incident intensity including error propagation
    dR=sqrt((dR/normR[newaxis, :])**2+(R*(norm.dRraw/normR**2)[newaxis, :])**2)
    R/=normR[newaxis, :]
    # reduce ToF region to points with incident intensity

    # calculate Q for each point of R
    Qz_edges=4.*pi/lamda_edges*sin(ai)[:, newaxis]
    Qz_centers=(Qz_edges[:, :-1]+Qz_edges[:, 1:])/2.
    #dQz=abs(Qz_edges[:, :-1]-Qz_edges[:, 1:])/2. #sqrt(12) error due to binning

    # create the Q bins to combine all R lines to
    # uses the smallest and largest Q all lines have in common with
    # a step size which has one point of every line in it.
    #Qz_start=Qz_edges[0,-1]
    Qz_start=Qz_edges[0, where(norm.Rraw>0)[0][-1]]
    Qz_end=Qz_edges[-1, where(norm.Rraw>0)[0][0]]
    Q=[]
    dQ=[]
    Rsum=[]
    ddRsum=[]
    Qz_edges_first=Qz_edges[0]
    Qz_edges_last=Qz_edges[-1]
    lines=range(Qz_edges.shape[0])
    ddR=dR**2
    for Qz_bin_low in reversed(Qz_edges_first[(Qz_edges_first<=Qz_end)&(Qz_edges_first>=Qz_start)]):
      # create a bin where at least one point from every
      # line is present
      try:
        # at least one point at the end can't be made into a bin this way
        Qz_bin_high=Qz_edges_last[Qz_edges_last>=Qz_bin_low][-2]
      except IndexError:
        break
      Q.append((Qz_bin_high+Qz_bin_low)/2.)
      # error is calculated from the relative binning size and angle resolutions
      dQ_rel=(Qz_bin_high-Qz_bin_low)/sqrt(12.)/Q[-1]
      dQ.append(sqrt(dQ_rel**2+dai_rel**2)*Q[-1])
      Rsumi=[]
      ddRsumi=[]
      for line in lines:
        # each line is treated equally in weight but there can be more than
        # one point per line in the same bin, so these are averaged
        select=(Qz_centers[line]>=Qz_bin_low)&(Qz_centers[line]<=Qz_bin_high)
        Rselect=R[line, select]
        ddRselect=ddR[line, select]
        Rsumi.append(Rselect.sum()/len(Rselect))
        ddRsumi.append(ddRselect.sum()/len(Rselect)**2)
      Rsum.append(array(Rsumi).sum())
      ddRsum.append(array(ddRsumi).sum())

    # sort the lists according to the default order from normal readout
    # and store them as numpy arrays
    Q.reverse()
    dQ.reverse()
    Rsum.reverse()
    ddRsum.reverse()
    self.dQ=array(dQ)
    self.Q=array(Q)
    self.R=array(Rsum)/len(lines)
    self.dR=sqrt(array(ddRsum))/len(lines)

  @log_call
  def _calc_bg(self, dataset):
    '''
    Calculate the background intensity vs. ToF.
    Equal for normal and fan reflectivity extraction.

    :param quicknxs.qreduce.MRDataset dataset: The dataset to use for extraction
    '''
    data=dataset.data
    if self.options['sensitivity_correction'] is not None:
      data=self._correct_sensitivity(data)
    y_pos=self.options['y_pos']
    y_width=self.options['y_width']
    bg_pos=self.options['bg_pos']
    bg_width=self.options['bg_width']
    bg_poly=self.options['bg_poly_regions']
    scale=1./dataset.proton_charge # scale by user factor

    # Get regions in pixels as integers
    reg=list(map(lambda item: int(round(item)),
            [bg_pos-bg_width/2., bg_pos+bg_width/2.+1,
             y_pos-y_width/2., y_pos+y_width/2.+1 ]))
    debug('Background region: %s'%str(reg))


    if bg_poly:
      # create the background region from given polygons
      # for ToF channels without polygon region the normal positions are use
      import matplotlib
      x=dataset.x
      lamda=dataset.lamda
      X, Lamda=meshgrid(x, lamda)
      points=vstack([Lamda.flatten(), X.flatten()]).transpose()
      points_in_region=zeros(X.shape, dtype=bool).flatten()
      # matplotlib 1.2 deprecates nxutils and 1.3 removes it
      if matplotlib.__version__>='1.2':
        debug('Using matplotlib.path for polygon checking')
        from matplotlib.path import Path
        for poly in bg_poly:
          poly_path=Path(poly)
          points_in_region|=poly_path.contains_points(points)
      else:
        debug('Using matplotlib.nxutils for polygon checking')
        from matplotlib.nxutils import points_inside_poly #@UnresolvedImport
        for poly in bg_poly:
          points_in_region|=points_inside_poly(points, poly)
      points_in_region=points_in_region.reshape(X.shape)
      lamda_regions=unique(Lamda[points_in_region].flatten())
      # add missing lambda items from normal bg region
      for lamdai in lamda:
        if lamdai not in lamda_regions:
          points_in_region[:, reg[0]:reg[1]]|=(Lamda[:, reg[0]:reg[1]]==lamdai)
      points_in_region=points_in_region.astype(float)
      # sum over y
      bgydata=data[:, reg[2]:reg[3], :].sum(axis=1).transpose()
      # sum over x in the given region and devide by number of x-points used
      unscaled_bgdata=(bgydata*points_in_region).sum(axis=1)
      scaling_data=points_in_region.sum(axis=1)*float(reg[3]-reg[2])
      self.BGraw=unscaled_bgdata/scaling_data*scale
      self.dBGraw=sqrt(unscaled_bgdata)/scaling_data*scale
      debug("Background scale is %s"%(scale/scaling_data))
    else:
      # restrict the intensity and background data to the given regions
      bgdata=data[reg[0]:reg[1], reg[2]:reg[3], :]
      # calculate region size for later use
      size_BG=float((reg[3]-reg[2])*(reg[1]-reg[0]))
      # calculate ROI intensities and normalize by number of points
      self.BGraw=bgdata.sum(axis=0).sum(axis=0)
      self.dBGraw=sqrt(self.BGraw)/(size_BG/scale)
      self.BGraw/=size_BG/scale
      debug("Background scale is %s"%(scale/size_BG))
    if self.options['bg_tof_constant'] and self.options['normalization']:
      norm=self.options['normalization'].R
      reg=(self.dBGraw>0)&(norm>0)
      norm_BG=self.BGraw[reg]/norm[reg]
      norm_dBG=self.dBGraw[reg]/norm[reg]
      wmeanBG=(norm_BG/norm_dBG).sum()/(1./norm_dBG).sum()
      wmeandBG=sqrt(len(norm_BG))/(1./norm_dBG).sum()
      self.BG=wmeanBG*norm
      self.dBG=wmeandBG*norm
      # for the channels with fast neutron contribution just take the raw background
      fast_n_tof=[i*1.0e6/60. for i in range(3)]
      tof_edges=dataset.tof_edges
      for fnt in fast_n_tof:
        channel=where((tof_edges[1:]>=fnt)&(tof_edges[:-1]<=fnt))[0]
        if channel.size == 0:
          continue
        self.BG[channel]=self.BGraw[channel]
        self.dBG[channel]=self.dBGraw[channel]
    else:
      self.BG=self.BGraw.copy()
      self.dBG=self.dBGraw.copy()
    self.BG*=self.options['bg_scale_factor']
    self.dBG*=self.options['bg_scale_factor']

  def rescale(self, scaling):
    old_scale=self.options['scale']
    rescale=scaling/old_scale
    self.R*=rescale
    self.dR*=rescale
    self.options['scale']=scaling

  @log_call
  def get_resolution(self):
    '''
    Calculate the angular resolution given by all slits together with the sample size
    and return the smallest one.
    '''
    res=[]
    s_width=self.options['sample_length']*sin(self.ai)
    for width, dist in self.slits:
      # calculate the maximum opening angle dTheta
      if s_width>0.:
        dTheta=arctan((s_width/2.*(1.+width/s_width))/dist)*2.
      else:
        dTheta=arctan(width/2./dist)*2.
      # standard deviation for a uniform angle distribution is Δθ/√12
      res.append(dTheta*0.28867513)
    debug('Sample Size %.2f\tSample FP: %.5f\tResolutions for slits: %s'%(
                            self.options['sample_length'], s_width, res))
    return min(res)

class OffSpecular(Reflectivity):
  '''
  Calculate off-specular scattering similarly as done for reflectivity.
  '''

  @log_input
  def __init__(self, dataset, **options):
    all_options=dict(OffSpecular.DEFAULT_OPTIONS)
    for key, value in options.items():
      if key not in all_options:
        raise ValueError("%s is not a known option parameter"%key)
      all_options[key]=value
    self.options=all_options
    self.origin=dataset.origin
    self.read_options=dataset.read_options
    if self.options['x_pos'] is None:
      # if nor x_pos is given, use the value from the dataset
      rad_per_pixel=dataset.det_size_x/dataset.dist_sam_det/dataset.xydata.shape[1]
      self.options['x_pos']=dataset.dpix-dataset.sangle/180.*pi/rad_per_pixel
    if self.options['tth'] is None:
      self.options['tth']=dataset.dangle-dataset.dangle0
    if self.options['dpix'] is None:
      self.options['dpix']=dataset.dpix
    self.lambda_center=dataset.lambda_center
    self.slits=[(dataset.slit1_width, dataset.slit1_dist),
                (dataset.slit2_width, dataset.slit2_dist),
                (dataset.slit3_width, dataset.slit3_dist)]
    if hasattr(dataset, 'slit4_width'):
      self.slits.append((dataset.slit4_width, dataset.slit4_dist))

    self._calc_offspec(dataset)

  def __repr__(self):
    if type(self.origin) is list:
      fnames='+'.join([os.path.basename(item[0]) for item in self.origin])
      output='<OffSpecular[%i] "%s/%s"'%(len(self.Qz), fnames,
                                        self.origin[0][1])
    else:
      output='<OffSpecular[%i] "%s/%s"'%(len(self.Qz), os.path.basename(self.origin[0]),
                                        self.origin[1])
    if self.options['normalization'] is None:
      output+=' NOT normalized'
    output+='>'
    return output

  @log_call
  def _calc_offspec(self, dataset):
    """
    Extract off-specular scattering from 4D dataset (x,y,ToF,I).
    Uses a window in y to filter the 4D data
    and than sums all I values for each ToF and x channel.
    Qz,Qx,kiz,kfz is calculated using the x and ToF positions
    together with the tth-bank and direct pixel values.

    :param quicknxs.qreduce.MRDataset dataset: The dataset to use for extraction
    """
    tof_edges=dataset.tof_edges
    data=dataset.data
    if self.options['sensitivity_correction'] is not None:
      data=self._correct_sensitivity(data)
    x_pos=self.options['x_pos']
    x_width=self.options['x_width']
    y_pos=self.options['y_pos']
    y_width=self.options['y_width']
    scale=1./dataset.proton_charge # scale by user factor

    # Get regions in pixels as integers
    reg=list(map(lambda item: int(round(item)),
            [x_pos-x_width/2., x_pos+x_width/2.+1,
             y_pos-y_width/2., y_pos+y_width/2.+1]))
    debug('Off-Specular region: %s'%str(reg))

    rad_per_pixel=dataset.det_size_x/dataset.dist_sam_det/dataset.xydata.shape[1]
    xtth=self.options['dpix']-arange(data.shape[0])[dataset.active_area_x[0]:
                                                    dataset.active_area_x[1]]
    pix_offset_spec=self.options['dpix']-x_pos
    tth_spec=self.options['tth']*pi/180.+pix_offset_spec*rad_per_pixel
    af=self.options['tth']*pi/180.+xtth*rad_per_pixel-tth_spec/2.
    ai=ones_like(af)*tth_spec/2.
    self.ai=tth_spec/2.
    debug('alpha_i=%s'%self.ai)

    self._calc_bg(dataset)

    v_edges=dataset.dist_mod_det/tof_edges*1e6 #m/s
    lamda_edges=H_OVER_M_NEUTRON/v_edges*1e10 #A
    # store the ToF as well for comparison etc.
    self.tof=(tof_edges[:-1]+tof_edges[1:])/2. # µs
    self.lamda=(lamda_edges[:-1]+lamda_edges[1:])/2.
    # resolution for lambda is digital range with equal probability
    # therefore it is the bin size divided by sqrt(12)
    self.dlamda=abs(lamda_edges[:-1]-lamda_edges[1:])/sqrt(12)
    k=2.*pi/self.lamda

    # calculate reciprocal space, incident and outgoing perpendicular wave vectors
    self.Qz=k[newaxis, :]*(sin(af)+sin(ai))[:, newaxis]
    self.Qx=k[newaxis, :]*(cos(af)-cos(ai))[:, newaxis]
    self.ki_z=k[newaxis, :]*sin(ai)[:, newaxis]
    self.kf_z=k[newaxis, :]*sin(af)[:, newaxis]

    # calculate ROI intensities and normalize by number of points
    Idata=data[dataset.active_area_x[0]:dataset.active_area_x[1], reg[2]:reg[3], :]
    self.Iraw=Idata.sum(axis=1)
    self.dIraw=sqrt(self.Iraw)
    # normalize data by width in y and multiply scaling factor
    debug("Intensity scale is %s*%s=%s"%(scale/(reg[3]-reg[2]),
                                        self.options['scale'],
                                        self.options['scale']*scale/(reg[3]-reg[2])))
    self.I=self.Iraw/(reg[3]-reg[2])*scale
    self.dI=self.dIraw/(reg[3]-reg[2])*scale
    if self.options['subtract_background']:
      self.S=self.I-self.BG[newaxis, :]
    else:
      self.S=array(self.I)  # BG X off: keep raw intensity (matches v2 subtract_background=False)
    self.dS=sqrt(self.dI**2+(self.dBG**2)[newaxis, :])
    self.S*=self.options['scale']
    self.dS*=self.options['scale']

    if self.options['normalization']:
      norm=self.options['normalization']
      debug("Performing normalization from %s"%norm)
      # Normalize by the direct beam's RAW flux (norm.I), not the
      # background-subtracted norm.Rraw (= I - BG).  At a band edge the DB
      # signal approaches its own background, so Rraw collapses toward zero (a
      # tiny positive residual) and 1/Rraw blows up a spurious off-spec pixel,
      # while the raw flux I stays well-behaved.  Matches quicknxsv2
      # off_specular.py, which normalizes off-spec by raw direct-beam counts.
      idxs=norm.I>0.
      self.dS[:, idxs]=sqrt(
                   (self.dS[:, idxs]/norm.I[idxs][newaxis, :])**2+
                   (self.S[:, idxs]/norm.I[idxs][newaxis, :]**2*norm.dI[idxs][newaxis, :])**2
                   )
      self.S[:, idxs]/=norm.I[idxs][newaxis, :]
      self.S[:, logical_not(idxs)]=0.
      self.dS[:, logical_not(idxs)]=0.

    # Crop to Mantid MRR's usable wavelength band (get_tof_range): the chopper
    # half-bandwidth is MANTID_OFFSPEC_HALF_BANDWIDTH at the reference speed and
    # widens inversely with chopper speed.  v1's load band is wider (1.6), so its
    # low-flux edges -- where the direct-beam normalization is a single count and
    # 1/flux blows up a spurious off-spec pixel (the 44159 artifact) -- are
    # trimmed here for the off-spec, matching Mantid.
    cs=getattr(dataset, 'chopper_speed', None)
    scale=TOF_REFERENCE_FREQUENCY/float(cs) if cs else 1.
    hb=MANTID_OFFSPEC_HALF_BANDWIDTH*scale
    out_of_band=(self.lamda<dataset.lambda_center-hb)|(self.lamda>dataset.lambda_center+hb)
    self.S[:, out_of_band]=0.
    self.dS[:, out_of_band]=0.

class GISANS(Reflectivity):
  '''
  Calculate GISANS scattering from dataset.
  '''

  @log_input
  def __init__(self, dataset, **options):
    all_options=dict(OffSpecular.DEFAULT_OPTIONS)
    for key, value in options.items():
      if key not in all_options:
        raise ValueError("%s is not a known option parameter"%key)
      all_options[key]=value
    self.options=all_options
    self.origin=dataset.origin
    self.read_options=dataset.read_options
    if self.options['x_pos'] is None:
      # if nor x_pos is given, use the value from the dataset
      rad_per_pixel=dataset.det_size_x/dataset.dist_sam_det/dataset.xydata.shape[1]
      self.options['x_pos']=dataset.dpix-dataset.sangle/180.*pi/rad_per_pixel
    if self.options['tth'] is None:
      self.options['tth']=dataset.dangle-dataset.dangle0
    if self.options['dpix'] is None:
      self.options['dpix']=dataset.dpix
    self.lambda_center=dataset.lambda_center
    self.slits=[(dataset.slit1_width, dataset.slit1_dist),
                (dataset.slit2_width, dataset.slit2_dist),
                (dataset.slit3_width, dataset.slit3_dist)]
    if hasattr(dataset, 'slit4_width'):
      self.slits.append((dataset.slit4_width, dataset.slit4_dist))

    self._calc_gisans(dataset)

  def __repr__(self):
    if type(self.origin) is list:
      fnames='+'.join([os.path.basename(item[0]) for item in self.origin])
      output='<GISANS[%i,%i] "%s/%s"'%(self.Qz.shape[0], self.Qz.shape[1], fnames,
                                        self.origin[0][1])
    else:
      output='<GISANS[%i,%i] "%s/%s"'%(self.Qz.shape[0], self.Qz.shape[1],
                                       os.path.basename(self.origin[0]), self.origin[1])
    if self.options['normalization'] is None:
      output+=' NOT normalized'
    output+='>'
    return output

  @log_call
  def _calc_gisans(self, dataset):
    """
    :param quicknxs.qreduce.MRDataset dataset: The dataset to use for extraction
    """
    tof_edges=dataset.tof_edges
    data=dataset.data
    if self.options['sensitivity_correction'] is not None:
      data=self._correct_sensitivity(data)
    x_pos=self.options['x_pos']
    y_pos=self.options['y_pos']
    # create a nicer intensity scale by multiplying with the reflectiviy extraction region
    scale=self.options['scale']/dataset.proton_charge # scale by user factor

    rad_per_pixel=dataset.det_size_x/dataset.dist_sam_det/dataset.xydata.shape[1]
    xtth=self.options['dpix']-arange(data.shape[0])[dataset.active_area_x[0]:
                                                    dataset.active_area_x[1]]
    pix_offset_spec=self.options['dpix']-x_pos
    tth_spec=self.options['tth']*pi/180.+pix_offset_spec*rad_per_pixel
    af=self.options['tth']*pi/180.+xtth*rad_per_pixel-tth_spec/2.
    ai=ones_like(af)*tth_spec/2.
    phi=(arange(data.shape[1])[dataset.active_area_y[0]:
                               dataset.active_area_y[1]]-y_pos)*rad_per_pixel
    debug('alpha_i=%s'%(tth_spec/2.))

    v_edges=dataset.dist_mod_det/tof_edges*1e6 #m/s
    lamda_edges=H_OVER_M_NEUTRON/v_edges*1e10 #A
    # store the ToF as well for comparison etc.
    self.tof=(tof_edges[:-1]+tof_edges[1:])/2. # µs
    self.lamda=(lamda_edges[:-1]+lamda_edges[1:])/2.
    # resolution for lambda is digital range with equal probability
    # therefore it is the bin size divided by sqrt(12)
    self.dlamda=abs(lamda_edges[:-1]-lamda_edges[1:])/sqrt(12)
    k=2.*pi/self.lamda

    # calculate ROI intensities and normalize by number of points
    P0=len(self.tof)-self.options['P0']
    PN=self.options['PN']
    Idata=array(data[dataset.active_area_x[0]:dataset.active_area_x[1],
                     dataset.active_area_y[0]:dataset.active_area_y[1],
                     PN:P0])
    # calculate reciprocal space, incident and outgoing perpendicular wave vectors
    self.Qx=k[newaxis, newaxis, PN:P0]*(cos(phi)*cos(af)[:, newaxis]-cos(ai)[:, newaxis])[:, :, newaxis]
    self.Qy=k[newaxis, newaxis, PN:P0]*(sin(phi)*cos(af)[:, newaxis])[:, :, newaxis]
    self.pi=k[newaxis, newaxis, PN:P0]*((0*phi)+sin(ai)[:, newaxis])[:, :, newaxis]
    self.pf=k[newaxis, newaxis, PN:P0]*((0*phi)+sin(af)[:, newaxis])[:, :, newaxis]
    self.Qz=self.pi+self.pf

    # compute S and dS directly from Idata, avoiding redundant intermediate arrays
    self.S=Idata*scale
    self.dS=sqrt(Idata)*scale
    del Idata
    debug("Intensity scale is %s"%(scale))

    if self.options['normalization']:
      norm=self.options['normalization']
      debug("Performing normalization from %s"%norm)
      normR=norm.Rraw[PN:P0]
      normdR=norm.dRraw[PN:P0]
      idxs=normR>0.
      self.dS[:, :, idxs]=sqrt(
                   (self.dS[:, :, idxs]/normR[idxs][newaxis, newaxis, :])**2+
                   (self.S[:, :, idxs]/normR[idxs][newaxis, newaxis, :]**2*
                    normdR[idxs][newaxis, newaxis, :])**2
                   )
      self.S[:, :, idxs]/=normR[idxs][newaxis, newaxis, :]
      self.S[:, :, logical_not(idxs)]=0.
      self.dS[:, :, logical_not(idxs)]=0.

    if self.options['gisans_no_DP']:
      fast_n_tof=[i*1.0e6/60. for i in range(4)]
      tof_edges=dataset.tof_edges[PN:P0]
      fresult=(tof_edges[1:]<fast_n_tof[0])|(tof_edges[:-1]>fast_n_tof[0])
      for fnt in fast_n_tof[1:]:
        fresult&=(tof_edges[1:]<fnt)|(tof_edges[:-1]>fnt)
      fidx=where(fresult)[0]
      # apply filtering to remaining arrays
      self.S=self.S[:, :, fidx]
      self.dS=self.dS[:, :, fidx]
      self.Qx=self.Qx[:, :, fidx]
      self.Qy=self.Qy[:, :, fidx]
      self.Qz=self.Qz[:, :, fidx]
      self.pi=self.pi[:, :, fidx]
      self.pf=self.pf[:, :, fidx]

    # create grid
    self.SGrid, qy, qz=histogram2d(self.Qy.flatten(), self.Qz.flatten(),
                                   bins=(self.options['gisans_gridy'],
                                         self.options['gisans_gridz']),
                                   weights=self.S.flatten())
    npoints, ignore, ignore=histogram2d(self.Qy.flatten(), self.Qz.flatten(),
                                   bins=(self.options['gisans_gridy'],
                                         self.options['gisans_gridz']))
    self.SGrid[npoints>0]/=npoints[npoints>0]
    self.SGrid=self.SGrid.transpose()
    qy=(qy[:-1]+qy[1:])/2.
    qz=(qz[:-1]+qz[1:])/2.
    self.QyGrid, self.QzGrid=meshgrid(qy, qz)
