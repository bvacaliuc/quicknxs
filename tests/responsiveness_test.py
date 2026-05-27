#-*- coding: utf-8 -*-
"""Tests for the immediate-status / busy-scope responsiveness mechanism.

Covers the depth-counted busy scope on MainGUI, cursor balancing, exception
safety, and that the heavy handlers the user named (file open, OffSpec Preview
tab, Load Extraction) surface a message immediately and a uniform "Complete"
when they finish.
"""

import os
import unittest
from unittest.mock import patch

from qtpy.QtWidgets import QApplication, QMessageBox

from quicknxs.main_gui import MainGUI

_app = QApplication.instance() or QApplication([])

_test_dir = os.path.dirname(os.path.abspath(__file__))
TEST_DATASET = os.path.join(_test_dir, u'test1_histo.nxs')
statepath = os.path.join(os.path.expanduser('~/.quicknxs'), 'run_state.dat')


class BusyScopeTest(unittest.TestCase):
  def setUp(self):
    self.app = _app
    # Make sure no override cursor leaks in from a previous test.
    while QApplication.overrideCursor() is not None:
      QApplication.restoreOverrideCursor()
    if os.path.exists(statepath):
      os.remove(statepath)
    with patch.object(QMessageBox, 'warning', return_value=QMessageBox.No):
      self.gui = MainGUI([])
    # Run delayed triggers synchronously (no background thread).
    self.gui.trigger.stay_alive = False
    self.gui.trigger.wait()
    self.gui.trigger = lambda action, *args: self.gui.processDelayedTrigger(action, args)

  def tearDown(self):
    while QApplication.overrideCursor() is not None:
      QApplication.restoreOverrideCursor()
    self.gui.close()
    if os.path.exists(statepath):
      os.remove(statepath)

  # -- core mechanism --------------------------------------------------------
  def test_busy_shows_message_immediately_then_complete(self):
    self.assertEqual(self.gui._busy_depth, 0)
    with self.gui.busy(u'Doing X...'):
      self.assertEqual(self.gui._busy_depth, 1)
      self.assertEqual(self.gui.activity_indicator.text(), u'Doing X...')
    self.assertEqual(self.gui._busy_depth, 0)
    self.assertEqual(self.gui.activity_indicator.text(), u'Complete')

  def test_nested_scopes_signal_complete_once_at_outermost(self):
    with self.gui.busy(u'Outer...'):
      with self.gui.busy(u'Inner...'):
        self.assertEqual(self.gui._busy_depth, 2)
        self.assertEqual(self.gui.activity_indicator.text(), u'Inner...')
      # inner left -> depth back to 1, NOT complete yet
      self.assertEqual(self.gui._busy_depth, 1)
      self.assertNotEqual(self.gui.activity_indicator.text(), u'Complete')
    self.assertEqual(self.gui._busy_depth, 0)
    self.assertEqual(self.gui.activity_indicator.text(), u'Complete')

  def test_busy_releases_scope_and_cursor_on_exception(self):
    with self.assertRaises(ValueError):
      with self.gui.busy(u'Boom...'):
        raise ValueError('boom')
    self.assertEqual(self.gui._busy_depth, 0)
    self.assertIsNone(QApplication.overrideCursor())

  def test_wait_cursor_pushed_once_and_restored(self):
    self.assertIsNone(QApplication.overrideCursor())
    with self.gui.busy(u'x'):
      self.assertIsNotNone(QApplication.overrideCursor())
      with self.gui.busy(u'y'):
        self.assertIsNotNone(QApplication.overrideCursor())
      # still busy at depth 1 -> cursor remains
      self.assertIsNotNone(QApplication.overrideCursor())
    self.assertIsNone(QApplication.overrideCursor())

  def test_custom_done_message(self):
    with self.gui.busy(u'Working...', done=u'Saved'):
      pass
    self.assertEqual(self.gui.activity_indicator.text(), u'Saved')

  # -- handlers the user named ----------------------------------------------
  def test_fileopen_surfaces_complete_when_idle(self):
    self.gui.fileOpen(TEST_DATASET, do_plot=True)
    self.assertEqual(self.gui._busy_depth, 0)
    self.assertEqual(self.gui.activity_indicator.text(), u'Complete')
    self.assertIsNone(QApplication.overrideCursor())

  def test_offspec_tab_announces_before_rendering(self):
    self.gui.fileOpen(TEST_DATASET, do_plot=True)
    # Spy on plot_offspec to capture the status text *while* it runs.
    seen = {}

    def spy():
      seen['msg'] = self.gui.activity_indicator.text()
      seen['depth'] = self.gui._busy_depth

    self.gui.ui.plotTab.setCurrentIndex(3)
    with patch.object(self.gui, 'plot_offspec', side_effect=spy):
      self.gui.plotActiveTab()
    self.assertEqual(seen.get('msg'), u'Rendering off-specular preview...')
    self.assertGreaterEqual(seen.get('depth', 0), 1)
    # back to idle afterwards
    self.assertEqual(self.gui._busy_depth, 0)
    self.assertEqual(self.gui.activity_indicator.text(), u'Complete')

  # -- phase 2a: cursor classification + coalesced continuous status --------
  def test_busy_show_cursor_false_sets_no_cursor(self):
    with self.gui.busy(u'Opening dialog...', show_cursor=False):
      self.assertIsNone(QApplication.overrideCursor())
      self.assertEqual(self.gui._busy_depth, 1)
    self.assertIsNone(QApplication.overrideCursor())
    self.assertEqual(self.gui.activity_indicator.text(), u'Complete')

  def test_busy_show_cursor_true_sets_cursor(self):
    with self.gui.busy(u'Heavy work...', show_cursor=True):
      self.assertIsNotNone(QApplication.overrideCursor())
    self.assertIsNone(QApplication.overrideCursor())

  def test_activity_transient_is_coalesced_no_cursor_no_scope(self):
    self.gui._activity_transient(u'Adjusting region...')
    self.assertEqual(self.gui._busy_depth, 0)            # not a busy scope
    self.assertIsNone(QApplication.overrideCursor())     # no wait cursor
    self.assertTrue(self.gui.activity_indicator.is_settling())
    self.assertEqual(self.gui.activity_indicator.text(), u'Adjusting region...')
    self.assertNotEqual(self.gui.activity_indicator.text(), u'Complete')

  def test_changeRegionValues_uses_coalesced_status(self):
    self.gui.fileOpen(TEST_DATASET, do_plot=True)
    # plot_projections (during do_plot) set proj_lines, so the guard passes.
    self.gui.changeRegionValues()
    self.assertEqual(self.gui._busy_depth, 0)
    self.assertIsNone(QApplication.overrideCursor())
    self.assertTrue(self.gui.activity_indicator.is_settling())
    self.assertNotEqual(self.gui.activity_indicator.text(), u'Complete')

  def test_changeActiveChannel_surfaces_complete(self):
    self.gui.fileOpen(TEST_DATASET, do_plot=True)
    self.gui.changeActiveChannel()
    self.assertEqual(self.gui._busy_depth, 0)
    self.assertEqual(self.gui.activity_indicator.text(), u'Complete')
    self.assertIsNone(QApplication.overrideCursor())

  def test_reduceDatasets_opens_without_residual_cursor(self):
    self.gui.reduction_list = [object()]
    self.gui.ref_list_channels = ['x']
    with patch('quicknxs.main_gui.ReduceDialog') as MockDlg:
      MockDlg.return_value.exec_.return_value = 0
      self.gui.reduceDatasets()
    self.assertEqual(self.gui._busy_depth, 0)
    # dialog is interactive -> no wait cursor was pushed
    self.assertIsNone(QApplication.overrideCursor())
    self.assertEqual(self.gui.activity_indicator.text(), u'Complete')

  def test_loadextraction_announces_immediately(self):
    # Patch the file dialog to return our test .dat path is overkill; instead
    # verify the busy scope is entered before the (mocked) heavy work runs.
    seen = {}

    def fake_clear(*a, **k):
      seen['msg'] = self.gui.activity_indicator.text()
      seen['depth'] = self.gui._busy_depth
      # raise to abort the rest of loadExtraction cleanly
      raise RuntimeError('stop here')

    with patch.object(self.gui, 'clearRefList', side_effect=fake_clear):
      try:
        self.gui.loadExtraction(filename=u'/nonexistent/extraction.dat')
      except RuntimeError:
        pass
    self.assertEqual(seen.get('msg'), u'Loading extraction...')
    self.assertEqual(seen.get('depth'), 1)
    # scope released despite the exception
    self.assertEqual(self.gui._busy_depth, 0)
    self.assertIsNone(QApplication.overrideCursor())


if __name__ == '__main__':
  unittest.main()
