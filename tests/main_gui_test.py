#-*- coding: utf-8 -*-

import os
import unittest
from unittest.mock import patch
from qtpy.QtWidgets import QApplication, QMainWindow, QMessageBox
from qtpy.QtTest import QTest
from qtpy.QtCore import QLocale#, Qt

from quicknxs.main_gui import MainGUI
from quicknxs.qreduce import NXSData, Reflectivity

# Create a single QApplication instance for all tests
_app = QApplication.instance() or QApplication([])

dot=QLocale().decimalPoint()
if not isinstance(dot, str):
  dot=str(dot)

TEST_DATASET=os.path.join(os.path.dirname(os.path.abspath(__file__)), u'test1_histo.nxs')
statepath=os.path.join(os.path.expanduser('~/.quicknxs'), 'run_state.dat')

class MainGUIGeometryRestore(unittest.TestCase):
  """Test that legacy Python 2 str geometry/state values are handled correctly."""

  def test_str_geometry_encodes_to_bytes(self):
    """QByteArray should accept latin-1 encoded str from legacy config."""
    from qtpy.QtCore import QByteArray
    # Simulate a legacy Python 2 config value (str, not bytes)
    legacy_geometry = '\x01\xd9\xd0\xcb\x00\x01\x00\x00'
    # This is what the fix does:
    if isinstance(legacy_geometry, str):
      legacy_geometry = legacy_geometry.encode('latin-1')
    ba = QByteArray(legacy_geometry)
    self.assertIsInstance(ba, QByteArray)

  def test_bytes_geometry_works_directly(self):
    """QByteArray should accept bytes from Python 3 config."""
    from qtpy.QtCore import QByteArray
    py3_geometry = b'\x01\xd9\xd0\xcb\x00\x01\x00\x00'
    ba = QByteArray(py3_geometry)
    self.assertIsInstance(ba, QByteArray)


class MainGUIGeneral(unittest.TestCase):
  def setUp(self):
    self.app=_app
    if os.path.exists(statepath):
      os.remove(statepath)
    with patch.object(QMessageBox, 'warning', return_value=QMessageBox.No):
      self.gui=MainGUI([])
    # switch of delay triggering
    self.gui.trigger.stay_alive=False
    self.gui.trigger.wait()
    self.gui.trigger=lambda action, *args: self.gui.processDelayedTrigger(action, args)

  def tearDown(self):
    self.gui.close()
    if os.path.exists(statepath):
      os.remove(statepath)

  def test_1startup(self):
    self.assertTrue(isinstance(self.gui, QMainWindow))

  def test_2loadfile(self):
    self.gui.fileOpen(TEST_DATASET, do_plot=False)
    self.assertTrue(isinstance(self.gui.active_data, NXSData), 'dataset loaded')
    folder, basename=os.path.split(TEST_DATASET)
    self.assertEqual(self.gui.active_folder, folder)
    self.assertEqual(self.gui.active_file, basename)

  def test_2loadfile_plot(self):
    self.gui.fileOpen(TEST_DATASET, do_plot=True)
    self.assertFalse(self.gui.ui.xtof_overview.cplot is None, 'plot created')
    self.assertFalse(self.gui.ui.xy_overview.cplot is None, 'plot created')
    self.assertTrue(isinstance(self.gui.refl, Reflectivity))

  def test_3setxy(self):
    xstart=self.gui.ui.refXPos.value()
    ystart=self.gui.ui.refYPos.value()
    ywstart=self.gui.ui.refYWidth.value()
    self.gui.fileOpen(TEST_DATASET, do_plot=True)
    self.assertNotEqual(xstart, self.gui.ui.refXPos.value(), 'x-fitting')
    self.assertNotEqual(ystart, self.gui.ui.refYPos.value(), 'y-fitting')
    self.assertNotEqual(ywstart, self.gui.ui.refYWidth.value(), 'yw-fitting')


class MainGUIActions(unittest.TestCase):
  def setUp(self):
    self.app=_app
    if os.path.exists(statepath):
      os.remove(statepath)
    with patch.object(QMessageBox, 'warning', return_value=QMessageBox.No):
      self.gui=MainGUI([])
    # switch of delay triggering
    self.gui.trigger.stay_alive=False
    self.gui.trigger.wait()
    self.gui.trigger=lambda action, *args: self.gui.processDelayedTrigger(action, args)
    self.gui.fileOpen(TEST_DATASET, do_plot=True)

  def tearDown(self):
    self.gui.close()
    if os.path.exists(statepath):
      os.remove(statepath)

  def test_1normalization(self):
    self.gui.ui.dangle0Overwrite.setText(str(self.gui.active_data[0].dangle))
    self.gui.ui.refXPos.setValue(self.gui.active_data[0].dpix)
    # Call setNorm() directly; QAction.triggered(checked=False) in PySide6
    # overrides the do_plot=True default, preventing recalculation
    self.gui.setNorm()
    self.assertTrue((self.gui.refl.R[self.gui.refl.R>0]==1.).all(),
                    'reflectivity self normalized %s'%repr(self.gui.refl))

  def test_change(self):
    self.assertFalse(self.gui.auto_change_active)

    self.gui.auto_change_active=True
    self.gui.ui.refXPos.selectAll()
    QTest.keyClicks(self.gui.ui.refXPos, "200"+dot+"5")
    self.gui.ui.refXWidth.selectAll()
    QTest.keyClicks(self.gui.ui.refXWidth, "20")
    self.gui.ui.refYPos.selectAll()
    QTest.keyClicks(self.gui.ui.refYPos, "150")
    self.gui.ui.refYWidth.selectAll()
    QTest.keyClicks(self.gui.ui.refYWidth, "60")
    self.gui.ui.bgCenter.selectAll()
    QTest.keyClicks(self.gui.ui.bgCenter, "20")
    self.gui.ui.bgWidth.selectAll()
    QTest.keyClicks(self.gui.ui.bgWidth, "30")
    self.gui.ui.refScale.selectAll()
    QTest.keyClicks(self.gui.ui.refScale, "2")
    self.assertEqual(self.gui.ui.refXPos.value(), 200.5)
    self.assertEqual(self.gui.ui.refXWidth.value(), 20.)
    self.assertEqual(self.gui.ui.refYPos.value(), 150.)
    self.assertEqual(self.gui.ui.refYWidth.value(), 60.)
    self.assertEqual(self.gui.ui.bgCenter.value(), 20.)
    self.assertEqual(self.gui.ui.bgWidth.value(), 30.)
    self.assertEqual(self.gui.ui.refScale.value(), 2.)
    self.gui.auto_change_active=False

    # make sure reflectivity got extracted with new params
    # Call setNorm() directly; QAction.triggered(checked=False) in PySide6
    # overrides the do_plot=True default, preventing recalculation
    self.gui.setNorm()
    self.assertEqual(self.gui.refl.options['x_pos'], 200.5)
    self.assertEqual(self.gui.refl.options['x_width'], 20.)
    self.assertEqual(self.gui.refl.options['y_pos'], 150.)
    self.assertEqual(self.gui.refl.options['y_width'], 60.)
    self.assertEqual(self.gui.refl.options['bg_pos'], 20.)
    self.assertEqual(self.gui.refl.options['bg_width'], 30.)
    self.assertEqual(self.gui.refl.options['scale'], 100.)

class MainGUIProgressCallback(unittest.TestCase):
  """Test that updateEventReadout accepts float progress values (Qt5 compat)."""

  def setUp(self):
    self.app=_app
    if os.path.exists(statepath):
      os.remove(statepath)
    with patch.object(QMessageBox, 'warning', return_value=QMessageBox.No):
      self.gui=MainGUI([])
    self.gui.trigger.stay_alive=False
    self.gui.trigger.wait()
    self.gui.trigger=lambda action, *args: self.gui.processDelayedTrigger(action, args)

  def tearDown(self):
    self.gui.close()
    if os.path.exists(statepath):
      os.remove(statepath)

  def test_updateEventReadout_accepts_float(self):
    """setValue() requires int in Qt5; float progress values must be cast."""
    for progress in [0., 0.1, 0.5, 0.9, 1.0]:
      self.gui.updateEventReadout(progress)
      self.assertEqual(self.gui.eventProgress.value(), int(progress*100))

  def test_callback_through_nxsdata(self):
    """Verify the callback works end-to-end when reading a histogram file."""
    data=NXSData(TEST_DATASET, use_caching=False,
                 callback=self.gui.updateEventReadout)
    self.assertIsNotNone(data)
    # After a successful read the progress should be at 100%
    self.assertEqual(self.gui.eventProgress.value(), 100)


suite=unittest.TestLoader().loadTestsFromTestCase(MainGUIGeometryRestore)
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(MainGUIGeneral))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(MainGUIActions))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(MainGUIProgressCallback))
