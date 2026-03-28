#-*- coding: utf-8 -*-

import os
import warnings
import unittest
from math import pi
import numpy as np
from quicknxs import qreduce
from numpy.testing import assert_array_equal

TEST_DATASET=os.path.join(os.path.dirname(os.path.abspath(__file__)), u'test1_histo.nxs')
TEST_EVENT=os.path.join(os.path.dirname(os.path.abspath(__file__)), u'test1_event.nxs')
TEST_REFL=os.path.join(os.path.dirname(os.path.abspath(__file__)), u'test_refl_histo.nxs')

class GeneralClassTest(unittest.TestCase):

  def test_wrong_keyword(self):
    # make sure the classes don't accept a wrong keyword argument
    self.assertRaises(ValueError, qreduce.NXSData, '', blabli=12)
    self.assertRaises(ValueError, qreduce.NXSMultiData, [''], blabli=12)
    self.assertRaises(ValueError, qreduce.Reflectivity, None, blabli=12)
    self.assertRaises(ValueError, qreduce.OffSpecular, None, blabli=12)
    self.assertRaises(ValueError, qreduce.GISANS, None, blabli=12)

  def test_no_file(self):
    self.assertTrue(qreduce.NXSData('nonexisting') is None)

  def test_read_file(self):
    obj=qreduce.NXSData(TEST_DATASET)
    self.assertTrue(isinstance(obj, qreduce.NXSData), 'NXS file readout')
    self.assertEqual(obj.origin, TEST_DATASET, 'make sure right file name is saved')
    self._attr_check(obj, 'measurement_type')
    self.assertEqual(len(obj), 4)
    repr(obj)

  def test_read_file_event(self):
    obj=qreduce.NXSData(TEST_EVENT, bins=40)
    self.assertTrue(isinstance(obj, qreduce.NXSData), 'NXS file readout')
    self.assertEqual(obj.origin, TEST_EVENT, 'make sure right file name is saved')
    self._attr_check(obj, 'measurement_type')
    self.assertEqual(len(obj), 4)
    self.assertEqual(len(obj[0].tof), 40)

  def test_caching(self):
    obj=qreduce.NXSData(TEST_DATASET, use_caching=True, bins=40)
    obj2=qreduce.NXSData(TEST_DATASET, use_caching=True, bins=40)
    # make sure changing options triggers reload
    obj3=qreduce.NXSData(TEST_DATASET, use_caching=True, bins=50)
    self.assertTrue(obj is obj2)
    self.assertFalse(obj is obj3)
    # make sure non cached reads dont lead to the same object
    obj=qreduce.NXSData(TEST_DATASET, use_caching=False, bins=50)
    obj2=qreduce.NXSData(TEST_DATASET, use_caching=False, bins=50)
    self.assertFalse(obj is obj2)

  def test_callback(self):
    self._progress=None
    qreduce.NXSData(TEST_DATASET, use_caching=False, bins=40, callback=self._cbtest)
    self.assertFalse(self._progress is None)
    self._progress=None
    qreduce.NXSData(TEST_EVENT, use_caching=False, bins=40, callback=self._cbtest)
    self.assertFalse(self._progress is None)
    self._progress=None
    obj=qreduce.NXSMultiData([TEST_DATASET, TEST_DATASET], use_caching=False,
                             bins=40, callback=self._cbtest)
    self.assertFalse(self._progress is None)
    repr(obj)

  def _cbtest(self, progress):
    self._progress=progress

  def _attr_check(self, obj, attr, msg=None):
    result=getattr(obj, attr, None)
    self.assertFalse(result is None, msg=msg)

  def test_functions(self):
    qreduce.time_from_header(TEST_DATASET)

class DataConsistencyChecks(unittest.TestCase):

  def setUp(self):
    self.data=qreduce.NXSData(TEST_DATASET)
    self.assertFalse(self.data is None, 'setting up data object')

  def test_origin(self):
    self.assertEqual(self.data.origin, self.data[0].origin[0])

  def test_options(self):
    self.assertEqual(self.data._options, self.data[0].read_options)

  def test_itemize(self):
    item0=self.data[0]
    ch0=self.data._channel_names[0]
    cho0=self.data._channel_origin[0]
    self.assertTrue(item0 is self.data[ch0])
    self.assertTrue(item0 is self.data[cho0])
    self.assertRaises(KeyError, self.data.__getitem__, 'not_there')
    self.assertRaises(IndexError, self.data.__getitem__, 100)
    self.data[0]=item0
    self.data[ch0]=item0
    self.data[cho0]=item0
    self.assertRaises(KeyError, self.data.__setitem__, 'not_there', item0)
    self.data.numitems()
    for ignore in self.data:
      pass

  def test_data_shape(self):
    d=self.data[0]
    x, y, tof=d.x, d.y, d.tof
    self.assertEqual(d.xdata.shape, x.shape)
    self.assertEqual(d.ydata.shape, y.shape)
    self.assertEqual(d.tofdata.shape, tof.shape)

    self.assertEqual(d.xydata.shape, (y.shape[0], x.shape[0]))
    self.assertEqual(d.xtofdata.shape, (x.shape[0], tof.shape[0]))
    self.assertEqual(d.data.shape, (x.shape[0], y.shape[0], tof.shape[0]))

  def test_counts(self):
    d=self.data[0]
    # compare total counts attribute with all three arrays
    self.assertEqual(d.total_counts, d.xydata.sum())
    self.assertEqual(d.total_counts, d.xtofdata.sum())
    self.assertEqual(d.total_counts, d.data.sum())
    # compare sum over full data axes with combined arrays
    assert_array_equal(d.data.sum(axis=1), d.xtofdata, verbose=True)
    assert_array_equal(d.data.sum(axis=2), d.xydata.transpose(), verbose=True)

  def test_properies(self):
    d=self.data[0]

    assert_array_equal((d.tof_edges[:-1]+d.tof_edges[1:])/2., d.tof, verbose=True)
    v_n=d.dist_mod_det/d.tof*1e6 #m/s
    lamda_n=qreduce.H_OVER_M_NEUTRON/v_n*1e10 #A
    assert_array_equal(lamda_n, d.lamda, verbose=True)
    for item in ['lambda_center', 'number', 'experiment', 'merge_warnings',
                 'dpix', 'dangle', 'dangle0', 'sangle']:
      self.assertEqual(getattr(self.data, item), getattr(d, item),
                       msg='Wrong property lookup for "%s"'%item)
    self.assertEqual(self.data.nbytes, sum([d.nbytes for d in self.data]),
                     msg='Wrong property calculation for "nbytes"')
    qreduce.NXSData.get_cachesize()

  def test_addition(self):
    d=self.data[0]
    d2=d+d
    self.assertEqual(d.total_counts*2, d2.total_counts)
    assert_array_equal(d.data*2, d2.data, verbose=True)

  def test_multi(self):
    d=self.data[0]
    d2=qreduce.NXSMultiData([TEST_DATASET])[0]
    self.assertEqual(d.origin, d2.origin)
    self.assertEqual(d.total_counts, d2.total_counts)
    assert_array_equal(d.data, d2.data, verbose=True)

class EventModeTests(unittest.TestCase):
  def test_data(self):
    full_ds=qreduce.NXSData(TEST_EVENT, event_split_bins=None)
    self.assertEqual(full_ds[0].total_counts, full_ds[0].xydata.sum())
    full_ds=qreduce.NXSData(TEST_EVENT, event_split_bins=None, bin_type=1)
    self.assertEqual(full_ds[0].total_counts, full_ds[0].xydata.sum())

  def test_splitting(self):
    full_ds=qreduce.NXSData(TEST_EVENT, event_split_bins=None)
    split_ds=[]
    for i in range(4):
      split_ds.append(qreduce.NXSData(TEST_EVENT, event_split_bins=4,
                                      event_split_index=i))
    self.assertEqual(full_ds[0].total_counts,
                     sum([d[0].total_counts for d in split_ds]))
    self.assertEqual(full_ds[0].proton_charge,
                     sum([d[0].proton_charge for d in split_ds]))

  def not_test_direct_compare(self):
    histo=qreduce.NXSData(TEST_DATASET)
    evnt=qreduce.NXSData(TEST_EVENT, event_tof_overwrite=histo[0].tof_edges)
    assert_array_equal(evnt[0].data, histo[0].data, verbose=True)


class DataReductionTests(unittest.TestCase):
  def setUp(self):
    self.data=qreduce.NXSData(TEST_DATASET)
    self.assertFalse(self.data is None, 'setting up data object')

  def test_1reflectivity(self):
    res=qreduce.Reflectivity(self.data[0])
    self.assertTrue(isinstance(res, qreduce.Reflectivity))

  def test_2reflectivity_fan(self):
    res=qreduce.Reflectivity(self.data[0], x_pos=206., tth=0., dpix=206.)
    res2=qreduce.Reflectivity(self.data[0], extract_fan=True, normalization=res,
                              tth=0.5, dpix=206.)
    self.assertTrue(isinstance(res2, qreduce.Reflectivity))
    repr(res2)

  def test_metadata(self):
    d=self.data[0]
    res=qreduce.Reflectivity(d)
    self.assertEqual(res.read_options, d.read_options)
    self.assertEqual(res.origin, d.origin)
    repr(res)

  def test_shapes(self):
    res=qreduce.Reflectivity(self.data[0])
    res=qreduce.Reflectivity(self.data[0], normalization=res, tth=0.5, x_pos=206., dpix=206.)
    rshape=len(self.data[0].tof_edges)-1
    # as Q and R are calculated from tof/lamda/I etc., there is no need to test each one
    self.assertEqual(res.Q.shape[0], rshape)
    self.assertEqual(res.R.shape[0], rshape)
    self.assertEqual(res.dR.shape[0], rshape)
    self.assertEqual(res.dQ.shape[0], rshape)

  def test_self_normalization(self):
    res=qreduce.Reflectivity(self.data[0], x_pos=206.)
    res2=qreduce.Reflectivity(self.data[0], x_pos=206., tth=0., normalization=res, scale=0.5)
    assert_array_equal(res2.R[res.Rraw>0], 0.5, verbose=True)

  def test_background(self):
    res=qreduce.Reflectivity(self.data[0], x_pos=206., x_width=10.,
                                            bg_pos=206., bg_width=10.)
    assert_array_equal(res.R, 0., verbose=True)

  def test_background_advanced(self):
    res=qreduce.Reflectivity(self.data[0], x_pos=206., tth=0., dpix=206.)
    ignore=qreduce.Reflectivity(self.data[0], x_pos=206., x_width=10.,
                                normalization=res, bg_pos=206., bg_width=10.,
                                bg_tof_constant=True,
                                bg_poly_regions=[[(2., 100), (2., 120), (4., 120), (4., 100)]])


  def test_angle_calculation(self):
    res=qreduce.Reflectivity(self.data[0], x_pos=206., x_width=10.,
                                            bg_pos=206., bg_width=10.,
                                            tth=0., dpix=206.)
    self.assertEqual(res.ai, 0.)
    res=qreduce.Reflectivity(self.data[0], x_pos=206., x_width=10.,
                                            bg_pos=206., bg_width=10.,
                                            tth=1., dpix=206.)
    self.assertEqual(res.ai, 0.5/180.*pi)

  def test_offspec(self):
    res=qreduce.Reflectivity(self.data[0], x_pos=206., tth=0., dpix=206.)
    res2=qreduce.OffSpecular(self.data[0], normalization=res)
    self.assertTrue(isinstance(res2, qreduce.OffSpecular))
    repr(res2)

  def test_gisans(self):
    res=qreduce.Reflectivity(self.data[0], x_pos=206., tth=0., dpix=206.)
    res2=qreduce.GISANS(self.data[0], normalization=res)
    self.assertTrue(isinstance(res2, qreduce.GISANS))
    repr(res2)


class LRDatasetTests(unittest.TestCase):
  '''Tests for REF_L (Liquids Reflectometer) data loading.'''

  @classmethod
  def setUpClass(cls):
    '''Load the REF_L test file once for all tests (file is large: 304x256x2001).'''
    cls.lr_data=qreduce.NXSData(TEST_REFL, use_caching=False)

  def test_lr_nxsdata_load_histogram(self):
    '''Load a REF_L histogram file and verify it returns NXSData with one LRDataset channel.'''
    obj=self.lr_data
    self.assertIsNotNone(obj, 'REF_L NXS file readout should not be None')
    self.assertIsInstance(obj, qreduce.NXSData)
    self.assertEqual(len(obj), 1, 'REF_L unpolarized data should have 1 channel')
    self.assertIsInstance(obj[0], qreduce.LRDataset)
    self.assertEqual(obj.measurement_type, 'Unpolarized')

  def test_lr_instrument_detection(self):
    '''Verify beamline detection routes to correct Dataset class.'''
    mr=qreduce.NXSData(TEST_DATASET, use_caching=False)
    lr=self.lr_data
    self.assertIsInstance(mr[0], qreduce.MRDataset)
    self.assertIsInstance(lr[0], qreduce.LRDataset)
    # LRDataset is a subclass of MRDataset
    self.assertIsInstance(lr[0], qreduce.MRDataset)
    self.assertEqual(mr._beamline, '4A')
    self.assertEqual(lr._beamline, '4B')

  def test_lr_dataset_metadata(self):
    '''Verify LRDataset extracts correct metadata from REF_L file.'''
    d=self.lr_data[0]
    # REF_L uses TwoTheta/readback for detector angle
    self.assertIsInstance(d.dangle, (float, np.floating))
    self.assertGreaterEqual(d.dangle, 0.)
    # REF_L has no DANGLE0 offset
    self.assertEqual(d.dangle0, 0.)
    # REF_L uses Theta/readback for sample angle
    self.assertIsInstance(d.sangle, (float, np.floating))
    # Default dpix for LR is 151
    self.assertEqual(d.dpix, 151)
    # Lambda center from DASlogs
    self.assertGreater(d.lambda_center, 0.)
    # Distances should be positive and in reasonable range
    self.assertGreater(d.dist_sam_det, 0.)
    self.assertGreater(d.dist_mod_det, 0.)
    self.assertGreater(d.dist_mod_det, d.dist_sam_det)
    # Proton charge and counts
    self.assertGreater(d.proton_charge, 0.)
    self.assertGreater(d.total_counts, 0)
    # Experiment and run number
    self.assertGreater(d.number, 0)

  def test_lr_slit_widths(self):
    '''Verify REF_L slit widths are extracted from DASlogs.'''
    d=self.lr_data[0]
    # REF_L has 4 slits
    self.assertTrue(hasattr(d, 'slit1_width'))
    self.assertTrue(hasattr(d, 'slit2_width'))
    self.assertTrue(hasattr(d, 'slit3_width'))
    self.assertTrue(hasattr(d, 'slit4_width'))
    self.assertTrue(hasattr(d, 'slit4_dist'))
    # Slit widths should be numeric
    self.assertIsInstance(d.slit1_width, (float, np.floating))
    self.assertIsInstance(d.slit4_width, (float, np.floating))

  def test_lr_data_shapes(self):
    '''Verify LRDataset data array shapes are consistent.'''
    d=self.lr_data[0]
    x, y, tof=d.x, d.y, d.tof
    self.assertEqual(d.xdata.shape, x.shape)
    self.assertEqual(d.ydata.shape, y.shape)
    self.assertEqual(d.tofdata.shape, tof.shape)
    self.assertEqual(d.xydata.shape, (y.shape[0], x.shape[0]))
    self.assertEqual(d.xtofdata.shape, (x.shape[0], tof.shape[0]))
    self.assertEqual(d.data.shape, (x.shape[0], y.shape[0], tof.shape[0]))

  def test_lr_data_counts_consistency(self):
    '''Verify total counts match between arrays.'''
    d=self.lr_data[0]
    self.assertEqual(d.total_counts, d.xydata.sum())
    self.assertEqual(d.total_counts, d.xtofdata.sum())
    self.assertEqual(d.total_counts, d.data.sum())
    assert_array_equal(d.data.sum(axis=1), d.xtofdata, verbose=True)
    assert_array_equal(d.data.sum(axis=2), d.xydata.transpose(), verbose=True)

  def test_lr_reflectivity_extraction(self):
    '''Create a Reflectivity from LRDataset and verify output.'''
    d=self.lr_data[0]
    # REF_L histogram files may have first ToF edge at 0, causing divide-by-zero
    with warnings.catch_warnings():
      warnings.simplefilter('ignore', RuntimeWarning)
      res=qreduce.Reflectivity(d)
    self.assertIsInstance(res, qreduce.Reflectivity)
    # Shape should match ToF bins
    rshape=len(d.tof_edges)-1
    self.assertEqual(res.Q.shape[0], rshape)
    self.assertEqual(res.I.shape[0], rshape)
    # LRDataset has 4 slits, so Reflectivity should store all 4
    self.assertEqual(len(res.slits), 4)
    repr(res)

  def test_lr_reflectivity_with_normalization(self):
    '''Test normalized reflectivity extraction from LRDataset.'''
    d=self.lr_data[0]
    with warnings.catch_warnings():
      warnings.simplefilter('ignore', RuntimeWarning)
      norm=qreduce.Reflectivity(d, x_pos=float(d.dpix), tth=0., dpix=float(d.dpix))
      res=qreduce.Reflectivity(d, normalization=norm, tth=0.5, dpix=float(d.dpix))
    self.assertIsInstance(res, qreduce.Reflectivity)
    rshape=len(d.tof_edges)-1
    self.assertEqual(res.R.shape[0], rshape)
    self.assertEqual(res.dR.shape[0], rshape)

  def test_lr_properties(self):
    '''Verify NXSData property forwarding works for LRDataset.'''
    d=self.lr_data[0]
    for attr in ['lambda_center', 'number', 'experiment', 'merge_warnings',
                 'dpix', 'dangle', 'dangle0', 'sangle']:
      self.assertEqual(getattr(self.lr_data, attr), getattr(d, attr),
                       msg='Wrong property lookup for "%s"'%attr)

  def test_lr_repr(self):
    '''Verify LRDataset repr works.'''
    d=self.lr_data[0]
    r=repr(d)
    self.assertIn('LRDataset', r)
    repr(self.lr_data)

  def test_lr_get_xpos(self):
    '''Verify get_xpos accepts LRDataset (isinstance check, not strict type).'''
    from quicknxs.qcalc import get_xpos
    d=self.lr_data[0]
    result=get_xpos(d)
    self.assertIsInstance(result, float)

  def test_lr_get_yregion(self):
    '''Verify get_yregion accepts LRDataset.'''
    from quicknxs.qcalc import get_yregion
    d=self.lr_data[0]
    y_center, y_width, y_bg=get_yregion(d)
    self.assertIsInstance(y_center, float)
    self.assertGreater(y_width, 0)


class InstrumentConfigTests(unittest.TestCase):
  '''Tests that verify the config system works correctly for both instruments.'''

  def test_ref_l_config_no_crash(self):
    '''Verify that accessing a REF_M-only constant from ref_l config does not crash.'''
    from quicknxs import config
    original = config.instrument
    try:
      config.instrument = config.proxy.add_alias('ref_l', 'instrument')
      from quicknxs.qreduce import _get_instrument_config
      # ANALYZER_IN is REF_M-only; should return default, not crash
      result = _get_instrument_config('ANALYZER_IN', (0, 100))
      self.assertEqual(result, (0, 100))
    finally:
      config.instrument = config.proxy.add_alias('ref_m', 'instrument')

  def test_ref_l_config_poly_corr_none(self):
    '''Verify ref_l POLY_CORR_PARAMS is None.'''
    from quicknxs import config
    config.instrument = config.proxy.add_alias('ref_l', 'instrument')
    try:
      # Access directly through config.instrument (not qreduce.instrument
      # which is bound at import time)
      self.assertIsNone(config.instrument.POLY_CORR_PARAMS)
    finally:
      config.instrument = config.proxy.add_alias('ref_m', 'instrument')

  def test_ref_m_constants_accessible(self):
    '''Verify REF_M constants are accessible from instrument config.'''
    from quicknxs import config
    config.instrument = config.proxy.add_alias('ref_m', 'instrument')
    self.assertEqual(config.instrument.ANALYZER_IN, (0, 100))
    self.assertEqual(config.instrument.NEW_ANALYZER_IN, (-620, 150))
    self.assertIsNotNone(config.instrument.POLY_CORR_PARAMS)


# Data load verification tests — skip when SNS data is not available
REF_L_DATA_DIR = '/SNS/REF_L/IPTS-7053/data'
REF_M_DATA_DIR = '/SNS/REF_M/IPTS-16196/data'

@unittest.skipUnless(os.path.isdir(REF_L_DATA_DIR), 'REF_L data not available')
class DataLoadVerificationLR(unittest.TestCase):
  '''Verify loading of production REF_L data files.'''

  def _load_file(self, path):
    obj = qreduce.NXSData(path, use_caching=False)
    self.assertIsNotNone(obj, 'NXSData returned None for %s' % path)
    self.assertIsInstance(obj[0], qreduce.LRDataset)
    self.assertGreater(obj[0].total_counts, 0)
    return obj

  def test_lr_load_histo(self):
    '''Load a REF_L histogram file from production data.'''
    import glob
    files = sorted(glob.glob(os.path.join(REF_L_DATA_DIR, '*80836*histo*')))
    self.assertGreater(len(files), 0, 'No REF_L histo files found')
    self._load_file(files[0])

  def test_lr_load_multiple_histo(self):
    '''Load several REF_L histogram files to verify consistency.'''
    import glob
    # Use specific known-good run numbers to avoid globbing thousands of
    # sshfs entries and iterating through broken/empty early runs.
    run_ids = ['80836', '80837', '80838', '80839', '80840']
    files = []
    for rid in run_ids:
      matches = sorted(glob.glob(os.path.join(REF_L_DATA_DIR, '*%s*histo*' % rid)))
      if matches:
        files.append(matches[0])
    self.assertGreater(len(files), 0, 'No REF_L histo files found')
    for f in files:
      self._load_file(f)

  def test_lr_load_event(self):
    '''Load a REF_L event mode file.'''
    import glob
    # Use same known-good run number as histo test
    files = sorted(glob.glob(os.path.join(REF_L_DATA_DIR, '*80836*event*')))[:1]
    self.assertGreater(len(files), 0, 'No REF_L event files found')
    obj = qreduce.NXSData(files[0], use_caching=False, bins=40)
    self.assertIsNotNone(obj, 'NXSData returned None for event file')
    self.assertIsInstance(obj[0], qreduce.LRDataset)

@unittest.skipUnless(os.path.isdir(REF_M_DATA_DIR), 'REF_M data not available')
class DataLoadVerificationMR(unittest.TestCase):
  '''Verify loading of production REF_M data files.'''

  def _load_file(self, path):
    obj = qreduce.NXSData(path, use_caching=False)
    self.assertIsNotNone(obj, 'NXSData returned None for %s' % path)
    self.assertIsInstance(obj[0], qreduce.MRDataset)
    return obj

  def test_mr_load_histo(self):
    '''Load a REF_M histogram file from production data.'''
    import glob
    files = sorted(glob.glob(os.path.join(REF_M_DATA_DIR, '*_histo.nxs')))[:1]
    self.assertGreater(len(files), 0, 'No REF_M histo files found')
    self._load_file(files[0])

  def test_mr_load_multiple_histo(self):
    '''Load several REF_M histogram files to verify consistency.'''
    import glob
    files = sorted(glob.glob(os.path.join(REF_M_DATA_DIR, '*_histo.nxs')))[:5]
    self.assertGreater(len(files), 0, 'No REF_M histo files found')
    for f in files:
      self._load_file(f)


class LocateFileTests(unittest.TestCase):
  '''Tests for _find_file_in_ipts() and locate_file() parallel search.'''

  def setUp(self):
    import tempfile
    self.tmpdir = tempfile.mkdtemp()
    # Build a minimal fake SNS hierarchy:
    #   IPTS-100/nexus/REF_M_1001.nxs.h5
    #   IPTS-200/data/REF_M_2001_histo.nxs
    #   IPTS-200/data/REF_M_2001_event.nxs
    #   IPTS-300/  (empty IPTS, no relevant files)
    #   shared/    (non-IPTS dir, should be ignored)
    for ipts, subdir, fname in [
        ('IPTS-100', 'nexus', 'REF_M_1001.nxs.h5'),
        ('IPTS-200', 'data',  'REF_M_2001_histo.nxs'),
        ('IPTS-200', 'data',  'REF_M_2001_event.nxs'),
    ]:
      d = os.path.join(self.tmpdir, ipts, subdir)
      os.makedirs(d, exist_ok=True)
      open(os.path.join(d, fname), 'w').close()
    os.makedirs(os.path.join(self.tmpdir, 'IPTS-300'), exist_ok=True)
    os.makedirs(os.path.join(self.tmpdir, 'shared'), exist_ok=True)

  def tearDown(self):
    import shutil
    shutil.rmtree(self.tmpdir, ignore_errors=True)

  def test_find_h5_file(self):
    '''_find_file_in_ipts finds a .nxs.h5 file in the nexus subdir.'''
    result = qreduce._find_file_in_ipts(
        self.tmpdir, [('nexus', 'REF_M_1001.nxs.h5')])
    self.assertIsNotNone(result)
    self.assertTrue(result.endswith('REF_M_1001.nxs.h5'))

  def test_find_histo_file(self):
    '''_find_file_in_ipts finds a _histo.nxs file in the data subdir.'''
    result = qreduce._find_file_in_ipts(
        self.tmpdir, [('data', 'REF_M_2001_histo.nxs')])
    self.assertIsNotNone(result)
    self.assertTrue(result.endswith('REF_M_2001_histo.nxs'))

  def test_find_returns_none_when_not_found(self):
    '''_find_file_in_ipts returns None if no IPTS dir contains the file.'''
    result = qreduce._find_file_in_ipts(
        self.tmpdir, [('nexus', 'REF_M_9999.nxs.h5')])
    self.assertIsNone(result)

  def test_find_ignores_non_ipts_dirs(self):
    '''_find_file_in_ipts ignores directories not starting with IPTS.'''
    p = os.path.join(self.tmpdir, 'shared', 'nexus', 'REF_M_5000.nxs.h5')
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w').close()
    result = qreduce._find_file_in_ipts(
        self.tmpdir, [('nexus', 'REF_M_5000.nxs.h5')])
    self.assertIsNone(result)

  def test_locate_file_histogram_mode(self):
    '''locate_file() with histogram=True finds _histo.nxs.'''
    from quicknxs.config import instrument
    orig = instrument.data_base
    try:
      instrument.data_base = self.tmpdir
      result = qreduce.locate_file(2001, histogram=True)
    finally:
      instrument.data_base = orig
    self.assertIsNotNone(result)
    self.assertIn('histo', result)

  def test_locate_file_event_mode_finds_h5(self):
    '''locate_file() with histogram=False prefers .nxs.h5.'''
    from quicknxs.config import instrument
    orig = instrument.data_base
    try:
      instrument.data_base = self.tmpdir
      result = qreduce.locate_file(1001, histogram=False)
    finally:
      instrument.data_base = orig
    self.assertIsNotNone(result)
    self.assertIn('.nxs.h5', result)

  def test_locate_file_event_mode_falls_back_to_event_nxs(self):
    '''locate_file() in event mode falls back to _event.nxs if no .nxs.h5.'''
    from quicknxs.config import instrument
    orig = instrument.data_base
    try:
      instrument.data_base = self.tmpdir
      result = qreduce.locate_file(2001, histogram=False)
    finally:
      instrument.data_base = orig
    self.assertIsNotNone(result)
    self.assertIn('event', result)

  def test_locate_file_not_found_returns_none(self):
    '''locate_file() returns None when the run does not exist.'''
    from quicknxs.config import instrument
    orig = instrument.data_base
    try:
      instrument.data_base = self.tmpdir
      result = qreduce.locate_file(9999, histogram=False)
    finally:
      instrument.data_base = orig
    self.assertIsNone(result)


class ListdirTimeoutTests(unittest.TestCase):
  '''Tests for _listdir_with_timeout() — thread-isolated os.listdir with deadline.'''

  def test_returns_entries_on_success(self):
    '''_listdir_with_timeout returns directory entries for a real path.'''
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
      os.makedirs(os.path.join(tmpdir, 'IPTS-1'))
      os.makedirs(os.path.join(tmpdir, 'shared'))
      result = qreduce._listdir_with_timeout(tmpdir, timeout=5.0)
    self.assertIsNotNone(result)
    self.assertIn('IPTS-1', result)
    self.assertIn('shared', result)

  def test_returns_none_for_missing_path(self):
    '''_listdir_with_timeout returns None for a non-existent path.'''
    result = qreduce._listdir_with_timeout('/nonexistent/path/xyz_9999', timeout=5.0)
    self.assertIsNone(result)

  def test_returns_none_on_timeout(self):
    '''_listdir_with_timeout returns None when the call does not finish in time.'''
    import threading
    from unittest.mock import patch
    released = threading.Event()

    real_listdir = os.listdir
    def slow_listdir(path):
      released.wait()   # block indefinitely until test releases
      return real_listdir(path)

    with patch('os.listdir', side_effect=slow_listdir):
      result = qreduce._listdir_with_timeout('/tmp', timeout=0.05)

    released.set()       # unblock the stuck daemon thread
    self.assertIsNone(result)

  def test_find_file_returns_none_when_listdir_times_out(self):
    '''_find_file_in_ipts returns None gracefully when _listdir_with_timeout returns None.'''
    from unittest.mock import patch
    with patch('quicknxs.qreduce._listdir_with_timeout', return_value=None):
      result = qreduce._find_file_in_ipts('/SNS/REF_M', [('nexus', 'REF_M_99999.nxs.h5')])
    self.assertIsNone(result)


suite=unittest.TestLoader().loadTestsFromTestCase(GeneralClassTest)
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(DataConsistencyChecks))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(DataReductionTests))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(EventModeTests))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(LRDatasetTests))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(InstrumentConfigTests))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(LocateFileTests))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(ListdirTimeoutTests))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(DataLoadVerificationLR))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(DataLoadVerificationMR))
