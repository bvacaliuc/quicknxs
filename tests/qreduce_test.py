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


suite=unittest.TestLoader().loadTestsFromTestCase(GeneralClassTest)
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(DataConsistencyChecks))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(DataReductionTests))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(EventModeTests))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(LRDatasetTests))
