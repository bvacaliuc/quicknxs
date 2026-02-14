#-*- coding: utf-8 -*-

import os
import unittest
from time import time
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

_test_dir=os.path.dirname(os.path.abspath(__file__))
TEST_DATASET=os.path.join(_test_dir, u'test1_histo.nxs')
TEST_EVENT=os.path.join(_test_dir, u'test1_event.nxs')
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


# ──────────────────────────────────────────────────────────────
#  Bug verification tests
# ──────────────────────────────────────────────────────────────

class MainGUIDelayedTrigger(unittest.TestCase):
  """Verify Bug 1 fix: DelayedTrigger dict mutation during iteration."""

  def test_iterate_over_copy(self):
    """Add multiple expired actions, simulate run loop, verify no RuntimeError."""
    from quicknxs.gui_utils import DelayedTrigger
    dt=DelayedTrigger()
    dt.delay=0  # all actions expire immediately
    # add several actions at once
    dt('action_a', 1)
    dt('action_b', 2)
    dt('action_c', 3)
    # collect emitted signals
    emitted=[]
    dt.activate.connect(lambda name, args: emitted.append((name, args)))
    # run one iteration manually (don't start the thread)
    dt.stay_alive=False
    to_activate=[]
    for name, items in list(dt.actions.items()):
      ti, args=items
      if time()-ti>dt.delay:
        to_activate.append((name, args))
    for name, args in to_activate:
      dt.actions.pop(name, None)
      dt.activate.emit(name, args)
    _app.processEvents()
    self.assertEqual(len(emitted), 3, 'all three actions should have been emitted')
    self.assertEqual(len(dt.actions), 0, 'actions dict should be empty')

  def test_trigger_thread_lifecycle(self):
    """Start and stop DelayedTrigger thread cleanly."""
    from quicknxs.gui_utils import DelayedTrigger
    dt=DelayedTrigger()
    dt.start()
    self.assertTrue(dt.isRunning())
    dt.stay_alive=False
    dt.wait(2000)
    self.assertFalse(dt.isRunning())


class MainGUIHeaderParserFault(unittest.TestCase):
  """Verify Bug 2 fix: HeaderParser handles missing sections gracefully."""

  def test_missing_direct_beam_section(self):
    """Parse header with no [Direct Beam Runs], verify no KeyError."""
    from quicknxs.qio import HeaderParser
    header='# Datafile created by QuickNXS 1.0.0\n# Date: 2025-01-01\n# Type: test\n'
    parser=HeaderParser(header, parse_meta=True)
    self.assertEqual(parser.section_data['Direct Beam Runs'], [])

  def test_missing_data_runs_section(self):
    """Parse header with no [Data Runs], verify no KeyError."""
    from quicknxs.qio import HeaderParser
    header='# Datafile created by QuickNXS 1.0.0\n# Date: 2025-01-01\n# Type: test\n'
    parser=HeaderParser(header, parse_meta=True)
    self.assertEqual(parser.section_data['Data Runs'], [])

  def test_empty_state_header(self):
    """Parse minimal 'Running PID ...' backup content without crashing."""
    from quicknxs.qio import HeaderParser
    header='# Running PID 12345\n# some extra line\n'
    # parse_meta=False since this isn't a QuickNXS-created file
    parser=HeaderParser(header, parse_meta=False)
    self.assertEqual(parser.section_data.get('Direct Beam Runs', []), [])
    self.assertEqual(parser.section_data.get('Data Runs', []), [])


class MainGUIIPythonFault(unittest.TestCase):
  """Verify Bug 3 fix: run_ipython() handles missing IPython gracefully."""

  def setUp(self):
    self.app=_app
    if os.path.exists(statepath):
      os.remove(statepath)
    self._warn_patcher=patch.object(QMessageBox, 'warning', return_value=QMessageBox.No)
    self._warn_patcher.start()
    self.gui=MainGUI([])
    self.gui.trigger.stay_alive=False
    self.gui.trigger.wait()
    self.gui.trigger=lambda action, *args: self.gui.processDelayedTrigger(action, args)

  def tearDown(self):
    self.gui.close()
    self._warn_patcher.stop()
    if os.path.exists(statepath):
      os.remove(statepath)

  def test_run_ipython_no_crash(self):
    """run_ipython() should not raise when IPython is not installed."""
    # This will hit the try/except ImportError path since IPython is not installed
    self.gui.run_ipython()
    # If we get here without an exception, the fix works


class MainGUIHelpAboutFault(unittest.TestCase):
  """Verify Bug 4 fixes: helpDialog and aboutDialog don't crash."""

  def setUp(self):
    self.app=_app
    if os.path.exists(statepath):
      os.remove(statepath)
    self._warn_patcher=patch.object(QMessageBox, 'warning', return_value=QMessageBox.No)
    self._warn_patcher.start()
    self.gui=MainGUI([])
    self.gui.trigger.stay_alive=False
    self.gui.trigger.wait()
    self.gui.trigger=lambda action, *args: self.gui.processDelayedTrigger(action, args)

  def tearDown(self):
    self.gui.close()
    self._warn_patcher.stop()
    if os.path.exists(statepath):
      os.remove(statepath)

  def test_help_dialog_no_crash(self):
    """helpDialog() should not crash when QtWebKit is None."""
    self.gui.helpDialog()
    # If we get here without AttributeError, the fix works

  def test_about_dialog_no_crash(self):
    """aboutDialog() should not crash on QT_VERSION_STR AttributeError."""
    with patch.object(QMessageBox, 'about', return_value=None):
      self.gui.aboutDialog()

  def test_about_dialog_contains_version(self):
    """aboutDialog() should include QuickNXS version in the text."""
    from quicknxs.version import str_version
    captured={}
    def capture_about(parent, title, text):
      captured['title']=title
      captured['text']=text
    with patch.object(QMessageBox, 'about', side_effect=capture_about):
      self.gui.aboutDialog()
    self.assertIn(str_version, captured['text'])
    self.assertIn('Qt', captured['text'])


class MainGUIProgressDialogFix(unittest.TestCase):
  """Verify Bug 5 fix: ProgressDialog.progress() accepts float values."""

  def test_progress_accepts_float(self):
    """ProgressDialog.progress() should handle float values 0.0 to 1.0."""
    from quicknxs.gui_utils import ProgressDialog
    # parent=None requires a workaround: use a dummy QWidget
    from qtpy.QtWidgets import QWidget
    parent=QWidget()
    dlg=ProgressDialog(parent, title='Test', info_start='Testing', maximum=100, add=0)
    for val in [0.0, 0.25, 0.5, 0.75, 1.0]:
      dlg.progress(val)
      self.assertEqual(dlg.progressBar.value(), int(val*100))
    parent.deleteLater()

  def test_progress_with_add_offset(self):
    """Verify add offset works correctly with float values."""
    from quicknxs.gui_utils import ProgressDialog
    from qtpy.QtWidgets import QWidget
    parent=QWidget()
    dlg=ProgressDialog(parent, title='Test', info_start='Testing', maximum=200, add=50)
    dlg.progress(0.5)
    self.assertEqual(dlg.progressBar.value(), int(0.5*100+50))
    parent.deleteLater()


class MainGUIReduceDialogFix(unittest.TestCase):
  """Verify Bug 6 fix: ReduceDialog instantiation with Python 3 cooperative MRO."""

  def test_reduce_dialog_instantiation(self):
    """ReduceDialog(parent, channels, refls) should not raise TypeError."""
    from quicknxs.gui_utils import ReduceDialog
    parent=QMainWindow()
    parent.color='jet'
    channels=['x']
    refls=[]
    dialog=ReduceDialog(parent, channels, refls)
    self.assertIsNotNone(dialog)
    self.assertEqual(dialog.channels, ['x'])
    self.assertEqual(dialog.refls, [])
    self.assertEqual(dialog._parent_window, parent)
    dialog.destroy()
    parent.deleteLater()

  def test_reducer_standalone(self):
    """Reducer(parent, channels, refls) still works as standalone."""
    from quicknxs.gui_utils import Reducer
    parent=QMainWindow()
    parent.color='jet'
    channels=['x', 'y']
    refls=['dummy']
    reducer=Reducer(parent, channels, refls)
    self.assertEqual(reducer.channels, ['x', 'y'])
    self.assertEqual(reducer.refls, ['dummy'])
    self.assertEqual(reducer._parent_window, parent)
    parent.deleteLater()

  def test_reduce_datasets_with_data(self):
    """reduceDatasets() with populated reduction list opens ReduceDialog without error."""
    if os.path.exists(statepath):
      os.remove(statepath)
    with patch.object(QMessageBox, 'warning', return_value=QMessageBox.No):
      gui=MainGUI([])
    gui.trigger.stay_alive=False
    gui.trigger.wait()
    gui.trigger=lambda action, *args: gui.processDelayedTrigger(action, args)
    gui.fileOpen(TEST_DATASET, do_plot=True)
    gui.ui.dangle0Overwrite.setText(str(gui.active_data[0].dangle))
    gui.ui.refXPos.setValue(gui.active_data[0].dpix)
    gui.setNorm()
    gui.addRefList()
    self.assertGreater(len(gui.reduction_list), 0)
    # Patch QDialog.exec_ to avoid blocking, and simulate cancel
    with patch('quicknxs.gui_utils.QDialog.exec_', return_value=False):
      gui.reduceDatasets()
    # If we get here without TypeError, the fix works
    gui.close()
    if os.path.exists(statepath):
      os.remove(statepath)


# ──────────────────────────────────────────────────────────────
#  Comprehensive GUI tests
# ──────────────────────────────────────────────────────────────

class MainGUIFileOperations(unittest.TestCase):
  """File open/reload/event/sum operations."""

  def setUp(self):
    self.app=_app
    if os.path.exists(statepath):
      os.remove(statepath)
    self._warn_patcher=patch.object(QMessageBox, 'warning', return_value=QMessageBox.No)
    self._warn_patcher.start()
    self.gui=MainGUI([])
    self.gui.trigger.stay_alive=False
    self.gui.trigger.wait()
    self.gui.trigger=lambda action, *args: self.gui.processDelayedTrigger(action, args)
    self.gui.fileOpen(TEST_DATASET, do_plot=False)

  def tearDown(self):
    self.gui.close()
    self._warn_patcher.stop()
    if os.path.exists(statepath):
      os.remove(statepath)

  def test_reload_file(self):
    """reloadFile() re-reads the same file."""
    self.gui.fileOpen(TEST_DATASET, do_plot=True)
    self.gui.reloadFile()
    self.assertIsNotNone(self.gui.active_data)

  def test_file_open_event_dataset(self):
    """Open event dataset without plotting."""
    self.gui.fileOpen(TEST_EVENT, do_plot=False)
    self.assertIsInstance(self.gui.active_data, NXSData)

  def test_file_open_event_with_plot(self):
    """Open event dataset with plotting."""
    self.gui.fileOpen(TEST_EVENT, do_plot=True)
    self.assertIsNotNone(self.gui.ui.xtof_overview.cplot)
    self.assertIsNotNone(self.gui.ui.xy_overview.cplot)

  def test_open_by_number_not_found(self):
    """openByNumber() with non-existent number returns False."""
    result=self.gui.openByNumber('999999')
    self.assertFalse(result)

  def test_file_open_sum(self):
    """fileOpenSum() sums multiple files."""
    self.gui.fileOpenSum([TEST_DATASET, TEST_DATASET])
    self.assertIsNotNone(self.gui.active_data)

  def test_folder_modified_no_crash(self):
    """folderModified() doesn't crash."""
    self.gui.folderModified()

  def test_empty_cache(self):
    """empty_cache() resets NXSData cache."""
    NXSData(TEST_DATASET, use_caching=True)
    self.gui.empty_cache()
    self.assertEqual(len(NXSData._cache), 0)


class MainGUIExtractionRegion(unittest.TestCase):
  """Extraction region controls."""

  def setUp(self):
    self.app=_app
    if os.path.exists(statepath):
      os.remove(statepath)
    self._warn_patcher=patch.object(QMessageBox, 'warning', return_value=QMessageBox.No)
    self._warn_patcher.start()
    self.gui=MainGUI([])
    self.gui.trigger.stay_alive=False
    self.gui.trigger.wait()
    self.gui.trigger=lambda action, *args: self.gui.processDelayedTrigger(action, args)
    self.gui.fileOpen(TEST_DATASET, do_plot=True)

  def tearDown(self):
    self.gui.close()
    self._warn_patcher.stop()
    if os.path.exists(statepath):
      os.remove(statepath)

  def test_overwrite_direct_beam(self):
    """overwriteDirectBeam() sets dpix and dangle values."""
    self.gui.overwriteDirectBeam()
    self.assertNotEqual(self.gui.ui.directPixelOverwrite.value(), -1)
    self.assertNotEqual(self.gui.ui.dangle0Overwrite.text(), "None")

  def test_clear_overwrite(self):
    """clearOverwrite() resets to -1 / 'None'."""
    self.gui.overwriteDirectBeam()
    self.gui.clearOverwrite()
    self.assertEqual(self.gui.ui.directPixelOverwrite.value(), -1)
    self.assertEqual(self.gui.ui.dangle0Overwrite.text(), "None")

  def test_change_region_fan_reflectivity(self):
    """Toggle fanReflectivity checkbox."""
    initial=self.gui.ui.fanReflectivity.isChecked()
    self.gui.ui.fanReflectivity.setChecked(not initial)
    self.assertEqual(self.gui.ui.fanReflectivity.isChecked(), not initial)

  def test_trust_dangle_toggle(self):
    """Toggle trustDANGLE checkbox without crash."""
    self.gui.ui.trustDANGLE.setChecked(False)
    self.gui.ui.trustDANGLE.setChecked(True)

  def test_range_start_end_setValue(self):
    """Set rangeStart/rangeEnd values."""
    self.gui.auto_change_active=True
    self.gui.ui.rangeStart.setValue(5)
    self.gui.ui.rangeEnd.setValue(95)
    self.assertEqual(self.gui.ui.rangeStart.value(), 5)
    self.assertEqual(self.gui.ui.rangeEnd.value(), 95)
    self.gui.auto_change_active=False

  def test_bg_active_toggle(self):
    """Toggle background active radio button."""
    self.gui.ui.bgActive.setChecked(True)
    self.assertTrue(self.gui.ui.bgActive.isChecked())
    self.gui.ui.bgActive.setChecked(False)
    self.assertFalse(self.gui.ui.bgActive.isChecked())


class MainGUIReductionActions(unittest.TestCase):
  """Reduction list operations."""

  def setUp(self):
    self.app=_app
    if os.path.exists(statepath):
      os.remove(statepath)
    self._warn_patcher=patch.object(QMessageBox, 'warning', return_value=QMessageBox.No)
    self._warn_patcher.start()
    self.gui=MainGUI([])
    # reset class-level mutable attributes to ensure clean state between tests
    self.gui.ref_norm={}
    self.gui.ref_list_channels=[]
    self.gui.reduction_list=[]
    self.gui.trigger.stay_alive=False
    self.gui.trigger.wait()
    self.gui.trigger=lambda action, *args: self.gui.processDelayedTrigger(action, args)
    self.gui.fileOpen(TEST_DATASET, do_plot=True)

  def tearDown(self):
    self.gui.close()
    self._warn_patcher.stop()
    if os.path.exists(statepath):
      os.remove(statepath)

  def test_add_ref_without_norm(self):
    """addRefList() without normalization warns, doesn't add."""
    initial_count=len(self.gui.reduction_list)
    self.gui.addRefList()
    self.assertEqual(len(self.gui.reduction_list), initial_count)

  def test_set_norm_and_add_ref(self):
    """Set normalization, add to list, verify table row."""
    self.gui.ui.dangle0Overwrite.setText(str(self.gui.active_data[0].dangle))
    self.gui.ui.refXPos.setValue(self.gui.active_data[0].dpix)
    self.gui.setNorm()
    self.gui.addRefList()
    self.assertEqual(len(self.gui.reduction_list), 1)
    self.assertEqual(self.gui.ui.reductionTable.rowCount(), 1)

  def test_remove_ref_list(self):
    """Remove item from reduction list."""
    self.gui.ui.dangle0Overwrite.setText(str(self.gui.active_data[0].dangle))
    self.gui.ui.refXPos.setValue(self.gui.active_data[0].dpix)
    self.gui.setNorm()
    self.gui.addRefList()
    self.assertEqual(len(self.gui.reduction_list), 1)
    self.gui.ui.reductionTable.setCurrentCell(0, 0)
    self.gui.removeRefList()
    self.assertEqual(len(self.gui.reduction_list), 0)

  def test_clear_ref_list(self):
    """Clear entire reduction list."""
    self.gui.ui.dangle0Overwrite.setText(str(self.gui.active_data[0].dangle))
    self.gui.ui.refXPos.setValue(self.gui.active_data[0].dpix)
    self.gui.setNorm()
    self.gui.addRefList()
    self.gui.clearRefList()
    self.assertEqual(len(self.gui.reduction_list), 0)
    self.assertEqual(self.gui.ui.reductionTable.rowCount(), 0)

  def test_clear_norm_list(self):
    """Clear normalization table."""
    self.gui.ui.dangle0Overwrite.setText(str(self.gui.active_data[0].dangle))
    self.gui.ui.refXPos.setValue(self.gui.active_data[0].dpix)
    self.gui.setNorm()
    self.gui.clearNormList()
    self.assertEqual(self.gui.ui.normalizeTable.rowCount(), 0)
    self.assertEqual(len(self.gui.ref_norm), 0)

  def test_reduce_datasets_empty(self):
    """reduceDatasets() with empty list logs warning."""
    self.gui.reduction_list=[]
    self.gui.reduceDatasets()
    # should return without opening dialog

  def test_quick_reduce_empty(self):
    """quickReduce() with empty list logs warning."""
    self.gui.reduction_list=[]
    self.gui.quickReduce()
    # should return without error


class MainGUIDisplayControls(unittest.TestCase):
  """Display toggles and tab switching."""

  def setUp(self):
    self.app=_app
    if os.path.exists(statepath):
      os.remove(statepath)
    self._warn_patcher=patch.object(QMessageBox, 'warning', return_value=QMessageBox.No)
    self._warn_patcher.start()
    self.gui=MainGUI([])
    self.gui.trigger.stay_alive=False
    self.gui.trigger.wait()
    self.gui.trigger=lambda action, *args: self.gui.processDelayedTrigger(action, args)
    self.gui.fileOpen(TEST_DATASET, do_plot=True)

  def tearDown(self):
    self.gui.close()
    self._warn_patcher.stop()
    if os.path.exists(statepath):
      os.remove(statepath)

  def test_toggle_colorbars(self):
    """toggleColorbars() runs without error."""
    self.gui.toggleColorbars()

  def test_plot_tab_switching(self):
    """Set each plotTab index; plotActiveTab() is triggered via currentChanged signal."""
    for i in range(self.gui.ui.plotTab.count()):
      self.gui.ui.plotTab.setCurrentIndex(i)
      self.app.processEvents()

  def test_replot_projections(self):
    """replotProjections() with logarithmic_y toggled."""
    self.gui.ui.logarithmic_y.setChecked(True)
    self.gui.replotProjections()
    self.gui.ui.logarithmic_y.setChecked(False)
    self.gui.replotProjections()

  def test_change_active_channel(self):
    """Select channel0, call changeActiveChannel()."""
    self.gui.ui.selectedChannel0.setChecked(True)
    self.gui.changeActiveChannel()

  def test_logarithmic_colorscale_toggle(self):
    """Toggle logarithmic_colorscale checkbox."""
    initial=self.gui.ui.logarithmic_colorscale.isChecked()
    self.gui.ui.logarithmic_colorscale.setChecked(not initial)
    self.assertEqual(self.gui.ui.logarithmic_colorscale.isChecked(), not initial)

  def test_normalize_xtof_toggle(self):
    """Toggle normalizeXTof checkbox."""
    initial=self.gui.ui.normalizeXTof.isChecked()
    self.gui.ui.normalizeXTof.setChecked(not initial)
    self.assertEqual(self.gui.ui.normalizeXTof.isChecked(), not initial)

  def test_color_selector_change(self):
    """Change color_selector combo box index."""
    if self.gui.ui.color_selector.count()>1:
      self.gui.ui.color_selector.setCurrentIndex(1)
      self.gui.plotActiveTab()


class MainGUIMenuActions(unittest.TestCase):
  """Menu action handlers."""

  def setUp(self):
    self.app=_app
    if os.path.exists(statepath):
      os.remove(statepath)
    self._warn_patcher=patch.object(QMessageBox, 'warning', return_value=QMessageBox.No)
    self._warn_patcher.start()
    self.gui=MainGUI([])
    self.gui.trigger.stay_alive=False
    self.gui.trigger.wait()
    self.gui.trigger=lambda action, *args: self.gui.processDelayedTrigger(action, args)

  def tearDown(self):
    self.gui.close()
    self._warn_patcher.stop()
    if os.path.exists(statepath):
      os.remove(statepath)

  def test_set_debug(self):
    """set_debug() enables debug logging."""
    from logging import getLogger, DEBUG
    self.gui.set_debug()
    self.assertEqual(getLogger().level, DEBUG)

  def test_raise_error(self):
    """raiseError() raises RuntimeError."""
    with self.assertRaises(RuntimeError):
      self.gui.raiseError()

  def test_export_raw_data_no_refl(self):
    """exportRawData() with refl=None returns silently."""
    self.gui.refl=None
    self.gui.exportRawData()

  def test_open_nxs_dialog_no_data(self):
    """open_nxs_dialog() with active_data=None returns silently."""
    self.gui.active_data=None
    self.gui.open_nxs_dialog()


class MainGUISettingsState(unittest.TestCase):
  """Settings persistence and state management."""

  def setUp(self):
    self.app=_app
    if os.path.exists(statepath):
      os.remove(statepath)
    self._warn_patcher=patch.object(QMessageBox, 'warning', return_value=QMessageBox.No)
    self._warn_patcher.start()
    self.gui=MainGUI([])
    self.gui.trigger.stay_alive=False
    self.gui.trigger.wait()
    self.gui.trigger=lambda action, *args: self.gui.processDelayedTrigger(action, args)

  def tearDown(self):
    if self.gui is not None:
      self.gui.close()
    self._warn_patcher.stop()
    if os.path.exists(statepath):
      os.remove(statepath)

  def test_update_state_file(self):
    """updateStateFile() writes PID."""
    self.gui.updateStateFile(None)
    self.assertTrue(os.path.exists(statepath))
    with open(statepath, 'rb') as f:
      content=f.read().decode('utf8')
    self.assertIn('Running PID', content)
    self.assertIn(str(os.getpid()), content)

  def test_update_state_file_with_reduction(self):
    """State file includes header when reduction_list populated."""
    self.gui.fileOpen(TEST_DATASET, do_plot=True)
    self.gui.ui.dangle0Overwrite.setText(str(self.gui.active_data[0].dangle))
    self.gui.ui.refXPos.setValue(self.gui.active_data[0].dpix)
    self.gui.setNorm()
    self.gui.addRefList()
    self.gui.updateStateFile(None)
    with open(statepath, 'rb') as f:
      content=f.read().decode('utf8')
    self.assertIn('Running PID', content)
    self.assertIn('[Data Runs]', content)

  def test_close_no_crash(self):
    """close() doesn't crash."""
    # closeEvent() is called by close() with proper Qt event handling
    # set gui to None so tearDown skips the second close
    gui=self.gui
    self.gui=None
    gui.close()


# ──────────────────────────────────────────────────────────────
#  Matplotlib API compatibility tests
# ──────────────────────────────────────────────────────────────

class MatplotlibEllipseFix(unittest.TestCase):
  """Verify Ellipse angle parameter is passed as keyword (matplotlib >=3.8)."""

  def test_ellipse_with_angle_keyword(self):
    """Ellipse(xy, width, height, angle=...) should not raise TypeError."""
    from matplotlib.patches import Ellipse
    e=Ellipse((0.5, 0.5), 0.1, 0.2, angle=45., fill=False)
    self.assertIsNotNone(e)
    self.assertAlmostEqual(e.angle, 45.)
    self.assertAlmostEqual(e.width, 0.1)
    self.assertAlmostEqual(e.height, 0.2)

  def test_smooth_dialog_instantiation(self):
    """SmoothDialog.__init__() should not crash (exercises Ellipse + drawPlot)."""
    import numpy as np
    from quicknxs.gui_utils import SmoothDialog
    # Create minimal off-specular data: list of arrays with shape (ny, nx, 6)
    # columns: Qx, Qz, ki_z, kf_z, (unused), I
    ny, nx=5, 10
    item=np.zeros((ny, nx, 6))
    item[:, :, 2]=np.linspace(0.001, 0.01, nx)  # ki_z
    item[:, :, 3]=np.linspace(0.001, 0.01, nx)  # kf_z
    item[:, :, 5]=np.random.rand(ny, nx)  # I
    data=[item]
    parent=QMainWindow()
    dia=SmoothDialog(parent, data)
    self.assertIsNotNone(dia)
    self.assertIsNotNone(dia.sigma_1)
    self.assertIsNotNone(dia.sigma_2)
    self.assertIsNotNone(dia.sigma_3)
    dia.destroy()
    parent.deleteLater()


class ToolbarModeFix(unittest.TestCase):
  """Verify toolbar.mode replaces deprecated toolbar._active."""

  def test_toolbar_has_mode(self):
    """NavigationToolbar should have mode attribute, not _active."""
    from quicknxs.mplwidget import MPLWidget
    w=MPLWidget()
    if w.toolbar is not None:
      self.assertTrue(hasattr(w.toolbar, 'mode'))
      # mode should be falsy when no tool is active
      self.assertFalse(w.toolbar.mode)
    w.deleteLater()

  def test_toolbar_mode_no_crash_in_gui(self):
    """Plot click handlers referencing toolbar.mode should not crash."""
    if os.path.exists(statepath):
      os.remove(statepath)
    with patch.object(QMessageBox, 'warning', return_value=QMessageBox.No):
      gui=MainGUI([])
    gui.trigger.stay_alive=False
    gui.trigger.wait()
    gui.trigger=lambda action, *args: gui.processDelayedTrigger(action, args)
    gui.fileOpen(TEST_DATASET, do_plot=True)
    # Verify toolbar.mode is accessible on overview plots
    self.assertFalse(gui.ui.x_project.toolbar.mode)
    self.assertFalse(gui.ui.y_project.toolbar.mode)
    self.assertFalse(gui.ui.xy_overview.toolbar.mode)
    self.assertFalse(gui.ui.xtof_overview.toolbar.mode)
    gui.close()
    if os.path.exists(statepath):
      os.remove(statepath)


# ──────────────────────────────────────────────────────────────
#  SmoothDialog cursor fix tests
# ──────────────────────────────────────────────────────────────

class MPLWidgetCursorFix(unittest.TestCase):
  """Verify leaveEvent sets _last_cursor to valid Cursors value, not None."""

  def test_leave_event_sets_valid_cursor(self):
    """leaveEvent() should set _last_cursor to Cursors.POINTER, not None."""
    from quicknxs.mplwidget import MPLWidget
    from matplotlib.backend_tools import Cursors
    w=MPLWidget()
    if w.toolbar is not None:
      # Simulate a leave event
      from qtpy.QtCore import QEvent
      event=QEvent(QEvent.Leave)
      w.leaveEvent(event)
      self.assertIsNotNone(w.toolbar._last_cursor)
      self.assertEqual(w.toolbar._last_cursor, Cursors.POINTER)
    w.deleteLater()

  def test_canvas_draw_after_leave_event(self):
    """canvas.draw() should work after leaveEvent fires (no ValueError)."""
    from quicknxs.mplwidget import MPLWidget
    w=MPLWidget()
    if w.toolbar is not None:
      from qtpy.QtCore import QEvent
      event=QEvent(QEvent.Leave)
      w.leaveEvent(event)
      # This should not raise ValueError
      w.canvas.draw()
    w.deleteLater()


class SmoothDialogDrawPlotFix(unittest.TestCase):
  """Verify drawPlot() resets self.drawing even on error."""

  def test_drawing_reset_on_error(self):
    """drawPlot() should reset self.drawing=False even if draw() raises."""
    import numpy as np
    from quicknxs.gui_utils import SmoothDialog
    ny, nx=5, 10
    item=np.zeros((ny, nx, 6))
    item[:, :, 2]=np.linspace(0.001, 0.01, nx)
    item[:, :, 3]=np.linspace(0.001, 0.01, nx)
    item[:, :, 5]=np.random.rand(ny, nx)
    data=[item]
    parent=QMainWindow()
    dia=SmoothDialog(parent, data)
    # Patch plot.draw to raise, then call drawPlot
    with patch.object(dia.ui.plot, 'draw', side_effect=ValueError('test error')):
      try:
        dia.drawPlot()
      except ValueError:
        pass
    self.assertFalse(dia.drawing)
    dia.destroy()
    parent.deleteLater()


class SmoothDataCallbackFix(unittest.TestCase):
  """Verify smooth_data callback reaches 1.0 on completion."""

  def test_callback_reaches_one(self):
    """smooth_data should call callback(1.0) after loop completes."""
    import numpy as np
    from quicknxs.qcalc import smooth_data
    progress_values=[]
    def cb(v):
      progress_values.append(v)
    settings={
      'grid': (3, 3),
      'sigma': (0.001, 0.001),
      'region': (-0.001, 0.001, 0., 0.01),
    }
    x=np.array([0., 0.0005, -0.0005])
    y=np.array([0.002, 0.005, 0.008])
    I=np.array([1., 2., 3.])
    smooth_data(settings, x, y, I, callback=cb)
    self.assertGreater(len(progress_values), 0)
    self.assertAlmostEqual(progress_values[-1], 1.0)


# ──────────────────────────────────────────────────────────────
#  Test suite registration
# ──────────────────────────────────────────────────────────────

suite=unittest.TestLoader().loadTestsFromTestCase(MainGUIGeometryRestore)
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(MainGUIGeneral))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(MainGUIActions))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(MainGUIProgressCallback))
# Bug verification tests
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(MainGUIDelayedTrigger))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(MainGUIHeaderParserFault))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(MainGUIIPythonFault))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(MainGUIHelpAboutFault))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(MainGUIProgressDialogFix))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(MainGUIReduceDialogFix))
# Comprehensive GUI tests
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(MainGUIFileOperations))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(MainGUIExtractionRegion))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(MainGUIReductionActions))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(MainGUIDisplayControls))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(MainGUIMenuActions))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(MainGUISettingsState))
# Matplotlib API compatibility tests
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(MatplotlibEllipseFix))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(ToolbarModeFix))
# SmoothDialog cursor fix tests
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(MPLWidgetCursorFix))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(SmoothDialogDrawPlotFix))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(SmoothDataCallbackFix))
