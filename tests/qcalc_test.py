#-*- coding: utf-8 -*-

import unittest
from numpy import *
from quicknxs.qcalc import refine_gauss, get_scaling, get_xpos, get_yregion, \
                             get_total_reflection, smooth_data, DetectorTailCorrector
from quicknxs.qreduce import MRDataset, Reflectivity

class FitTest(unittest.TestCase):
  def setUp(self):
    self.x=linspace(-10, 10, 501)
    self.y=1e4*exp(-0.5*(self.x/2.)**2) # gaussian with sigma 2

  def test_absolute(self):
    # testing the absolute results
    res=refine_gauss(self.y, 200, 40, return_params=True)
    self.assertAlmostEqual(res[0], 1e4, places=10)
    self.assertAlmostEqual(res[1], 250., places=10)
    self.assertAlmostEqual(res[2], 50., places=10)

  def test_left_right(self):
    # testing different starting conditions far left and far right
    res1=refine_gauss(self.y, 50, 50, return_params=True)
    res2=refine_gauss(self.y, 450, 50, return_params=True)
    self.assertAlmostEqual(res1[0], res2[0], msg='I left vs. right', places=10)
    self.assertAlmostEqual(res1[1], res2[1], msg='x0 left vs. right', places=10)
    self.assertAlmostEqual(res1[2], res2[2], msg='sigma left vs. right', places=10)

class FakeData():
  def setUp(self):
    # create dummy data
    self.ds=MRDataset()
    self.ds.tof_edges=linspace(10000., 25000., 40)
    tof=(self.ds.tof_edges[1:]+self.ds.tof_edges[:-1])/2.
    self.ds.proton_charge=1e13
    self.ds.data=ones((304, 256, 39))*(tof[newaxis, newaxis, :])
    self.ds.data[:4]=0.
    self.ds.data[180:211]*=10.
    self.ds.data[:, :80]=0.
    self.ds.data[:,-80:]=0.
    self.ds.xydata=self.ds.data.sum(axis=2).transpose()
    self.ds.xtofdata=self.ds.data.sum(axis=1)
    self.ds.read_options=None
    # create two dummi reflectivities
    self.ref1=Reflectivity(self.ds, x_pos=200, dpix=210, tth=0., bg_pos=2, bg_width=4)
    self.ref2=Reflectivity(self.ds, x_pos=190, dpix=210, tth=0., bg_pos=2, bg_width=4)

class StitchTest(FakeData, unittest.TestCase):
  def test_linear(self):
    yscale, ignore, ignore=get_scaling(self.ref2, self.ref1, polynom=2)
    self.assertAlmostEqual(yscale, 1., places=3)
    self.ref2.R/=2
    yscale, ignore, ignore=get_scaling(self.ref2, self.ref1, polynom=2)
    self.assertAlmostEqual(yscale, 2., places=3)

  def test_gauss(self):
    yscale, ignore, ignore=get_scaling(self.ref2, self.ref1, polynom=0)
    self.assertAlmostEqual(yscale, 1., places=3)

  def test_wrong_call(self):
    self.assertRaises(ValueError, get_scaling, [0, 1, 2], [1, 2, 3])

  def test_degrees(self):
    yscale, ignore, ignore=get_scaling(self.ref2, self.ref1, polynom=2)
    for i in range(3, 8):
      yscale2, ignore, ignore=get_scaling(self.ref2, self.ref1, polynom=i)
      self.assertAlmostEqual(yscale, yscale2, places=3)
  
  def test_totref(self):
    self.ref1.R[20:]=100.
    self.ref1.R[:20]=0.1
    self.ref1.dR=ones_like(self.ref1.R)
    scale, npoints=get_total_reflection(self.ref1, return_npoints=True)
    self.assertEqual(scale, 1./100.)
    self.assertEqual(npoints, 20)

class PositionTest(FakeData, unittest.TestCase):
  def test_wrong_call(self):
    self.assertRaises(ValueError, get_xpos, [1, 2, 3])
    self.assertRaises(ValueError, get_yregion, [1, 2, 3])

  def test_xpos(self):
    self.ds.dpix=220.
    self.ds.dangle=self.ds.dangle0
    self.ds.sangle=0.5
    self.ds.xydata[:, 180:211]*=1.+5.*exp(-0.5*((arange(31)-15.25)/2.)**2) # reflected beam
    self.ds.xydata[:, 220:251]*=1.+1000.*exp(-0.5*((arange(31)-15.25)/2.)**2) # transmitted beam
    x_pos=get_xpos(self.ds)
    self.assertAlmostEqual(x_pos, 195.25, places=1)
  
  def test_ypos(self):
    y_pos, y_width, bg=get_yregion(self.ds)
    self.assertEqual(y_pos, 128.)
    self.assertEqual(y_width, 96.)
    self.assertEqual(bg, 0.)

class SmoothTest(unittest.TestCase):
  def setUp(self):
    self._progress=None
    self.x, self.y=meshgrid(arange(100), arange(100))
    self.I=(self.x-50.)**2+(self.y-50.)**2+random.randn(10000).reshape((100, 100))
    self.settings={
                   'grid': (20, 20),
                   'sigma': (3., 3.),
                   'region': (10, 90, 5 , 95),
                   }

  def test_smooth(self):
    Xout, Yout, Iout=smooth_data(self.settings, self.x, self.y, self.I, callback=self._cb_test)
    self.assertFalse(self._progress is None)
    self.assertEqual(Xout.min(), 10)
    self.assertEqual(Xout.max(), 90)
    self.assertEqual(Yout.min(), 5)
    self.assertEqual(Yout.max(), 95)
    self.assertEqual(Xout.shape, (20, 20))
    self.assertEqual(Yout.shape, (20, 20))
    self.assertEqual(Iout.shape, (20, 20))

  def test_smooth2(self):
    smooth_data(self.settings, self.x, self.y, self.I, callback=self._cb_test,
                axis_sigma_scaling=1)
    smooth_data(self.settings, self.x, self.y, self.I, callback=self._cb_test,
                axis_sigma_scaling=2)
    smooth_data(self.settings, self.x, self.y, self.I, callback=self._cb_test,
                axis_sigma_scaling=3)
    self.assertFalse(self._progress is None)

  def test_negative_y_region_no_nan(self):
    """When the smoothing grid extends below 0 (as it does for off-spec
    output that includes negative Qz), axis_sigma_scaling=2 used to
    produce NaN in those rows because ssigmayi went negative and exp()
    overflowed.  Regression: rows with yij ≤ 0 must be skipped cleanly
    and the rest of the grid must still be sensible."""
    import numpy as np
    xd = np.linspace(-0.1, 0.1, 2000)
    yd = np.linspace(0.0, 0.4, 2000)
    Id = np.ones(2000)
    settings = {'grid': (40, 40), 'sigma': (0.0005, 0.0005),
                'region': (-0.114, 0.086, -0.1, 0.376), 'sigmas': 3}
    _, Yo, Io = smooth_data(settings, xd, yd, Id, sigmas=3,
                            axis_sigma_scaling=2, xysigma0=0.4/3)
    self.assertEqual(np.isnan(Io).sum(), 0,
                     msg='y<0 rows must produce zeros, not NaN')
    # y<0 rows are skipped → all zero in those rows
    self.assertEqual(Io[Yo < 0].sum(), 0.0)
    # y>0 rows must have at least some nonzero output
    self.assertGreater((Io[Yo > 0] > 0).sum(), 0)

  def test_kdtree_matches_legacy_within_tolerance(self):
    """KDTree implementation should give the same answer as a direct
    point-by-point evaluation of the truncated gaussian kernel."""
    import numpy as np
    xd = np.linspace(0, 100, 500)
    yd = np.linspace(0, 100, 500)
    Id = (xd - 50)**2 + (yd - 50)**2
    settings = {'grid': (10, 10), 'sigma': (5., 5.),
                'region': (10, 90, 10, 90), 'sigmas': 3}
    _, _, Io = smooth_data(settings, xd, yd, Id)
    gx, gy = settings['grid']
    Iref = np.zeros((gy, gx))
    xs = np.linspace(*settings['region'][:2], gx)
    ys = np.linspace(*settings['region'][2:], gy)
    ssx = ssy = settings['sigma'][0]**2
    for i, yi in enumerate(ys):
      for j, xj in enumerate(xs):
        rij = (xd - xj)**2/ssx + (yd - yi)**2/ssy
        m = rij < settings['sigmas']**2
        if not m.any():
          continue
        w = np.exp(-0.5 * rij[m])
        Iref[i, j] = (w * Id[m]).sum() / w.sum()
    diff = np.abs(Io - Iref)
    self.assertLess(diff.max(), 1e-8,
                    msg=f'KDTree smoother disagrees with reference '
                        f'(max diff {diff.max()})')

  def _cb_test(self, progress):
    self._progress=progress

class DetectorCorrTest(FakeData, unittest.TestCase):
  def test_corr(self):
    c=DetectorTailCorrector(self.ds.xdata)
    ignore=c(self.ds.xtofdata)

suite=unittest.TestLoader().loadTestsFromTestCase(FitTest)
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(StitchTest))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(PositionTest))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(SmoothTest))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(DetectorCorrTest))
