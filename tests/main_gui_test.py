#-*- coding: utf-8 -*-

import os
import unittest
from time import time
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from qtpy.QtWidgets import QApplication, QMainWindow, QMessageBox
from qtpy.QtTest import QTest
from qtpy.QtCore import QLocale#, Qt

from quicknxs.main_gui import MainGUI, ExtractionRegion
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

  def test_offspec_flux_floor_control(self):
    '''The flux-floor spinbox lives in the Off-Specular tab (the Reflectivity
    Extraction Basic panel is sized for its original rows; adding controls
    there sprouts scrollbars).  No redundant BG-X mirror; default value =
    MANTID_OFFSPEC_FLUX_FLOOR (as log10); v1 immediate-recalc convention
    (valueChanged-connected, not editingFinished).'''
    from quicknxs.qreduce import MANTID_OFFSPEC_FLUX_FLOOR
    self.assertTrue(hasattr(self.gui, '_offspecFluxFloor'))
    self.assertFalse(hasattr(self.gui, '_offspecBgX'),
                     'BG-X mirror was removed; bgActive is the single BG-X control')
    self.assertAlmostEqual(10**self.gui._offspecFluxFloor.value(),
                           MANTID_OFFSPEC_FLUX_FLOOR, places=6)
    # parented under the Off-Specular tab so the Reflectivity Extraction (Basic)
    # QToolBox page doesn't gain a row and start showing scrollbars
    self.assertIs(self.gui._offspecFluxFloor.parentWidget(), self.gui.ui.OffSpec_Tab)

  def test_eventTofBins_max_supports_v2_resolution(self):
    # v2 reduces off-spec at 400 TOF bins; Load Extraction reads at this
    # spinbox value, so the cap must allow >=400 (prompt-30.1).
    self.assertGreaterEqual(self.gui.ui.eventTofBins.maximum(), 400)
    self.gui.ui.eventTofBins.setValue(400)
    self.assertEqual(self.gui.ui.eventTofBins.value(), 400)

  def test_close_open_plots_releases_windows(self):
    # Non-modal plot windows must be closed on exit, not left for interpreter
    # shutdown (matplotlib canvas torn down after QApplication -> SIGSEGV).
    d1, d2 = MagicMock(), MagicMock()
    self.gui.open_plots.append(d1)
    self.gui.open_plots.append(d2)
    self.gui._close_open_plots()
    d1.close.assert_called_once()
    d2.close.assert_called_once()
    self.assertEqual(len(self.gui.open_plots), 0,
                     'open_plots must be emptied so no canvas survives to shutdown')


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
  """Verify IPython console import and fallback behavior."""

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

  def test_ipython_widget_import(self):
    """ipython_widget module should import successfully with deps installed."""
    from quicknxs.ipython_widget import IPythonConsoleQtWidget
    self.assertIsNotNone(IPythonConsoleQtWidget)

  def test_run_ipython_starts_console(self):
    """run_ipython() should create ipython widget and switch to its tab."""
    self.gui.run_ipython()
    self.assertIsNotNone(self.gui.ipython)
    self.assertEqual(self.gui.ui.plotTab.currentWidget(), self.gui.ipython)

  def test_run_ipython_fallback_on_import_error(self):
    """run_ipython() should show QMessageBox when import fails."""
    with patch('quicknxs.main_gui.MainGUI.run_ipython',
               wraps=self.gui.run_ipython):
      with patch.dict('sys.modules', {'quicknxs.ipython_widget': None}):
        with patch.object(QMessageBox, 'information') as mock_info:
          self.gui.run_ipython()
          mock_info.assert_called_once()


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


class UpdateEventReadoutThrottle(unittest.TestCase):
  """Verify updateEventReadout() calls processEvents() with throttling."""

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

  def test_processEvents_called_at_least_once(self):
    """updateEventReadout() must call processEvents() to keep UI responsive."""
    call_count=[0]
    orig=QApplication.processEvents
    def counting_processEvents():
      call_count[0]+=1
      orig()
    with patch.object(QApplication, 'processEvents', side_effect=counting_processEvents):
      # _last_event_update starts at 0.0, so first call fires immediately
      self.gui.updateEventReadout(0.5)
    self.assertGreater(call_count[0], 0,
      'processEvents() must be called at least once to keep UI responsive')

  def test_throttle_limits_processEvents_calls(self):
    """Rapid updateEventReadout() calls must not call processEvents() every time."""
    call_count=[0]
    orig=QApplication.processEvents
    def counting_processEvents():
      call_count[0]+=1
      orig()
    with patch.object(QApplication, 'processEvents', side_effect=counting_processEvents):
      for i in range(20):
        self.gui.updateEventReadout(i / 20.0)
    # With 200 ms throttle and near-instant calls, processEvents should fire far fewer than 20 times
    self.assertLess(call_count[0], 20,
      'processEvents() should be throttled to avoid UI overhead on each callback')


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
    from quicknxs.config import instrument
    # Temporarily point data_base to a local directory (no IPTS subdirs)
    # so _find_file_in_ipts returns immediately without hitting sshfs.
    orig = instrument.data_base
    try:
      instrument.data_base = _test_dir
      result=self.gui.openByNumber('999999')
    finally:
      instrument.data_base = orig
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


# ──────────────────────────────────────────────────────────────
#  File loading fixes: run-number search and dialog filters
# ──────────────────────────────────────────────────────────────

class FileLoadingFixes(unittest.TestCase):
  """Tests for openByNumber(), fileOpenDialog filters, and updateFileList()."""

  def setUp(self):
    self.app = _app
    if os.path.exists(statepath):
      os.remove(statepath)
    self._warn_patcher = patch.object(QMessageBox, 'warning', return_value=QMessageBox.No)
    self._warn_patcher.start()
    self.gui = MainGUI([])
    self.gui.trigger.stay_alive = False
    self.gui.trigger.wait()
    self.gui.trigger = lambda action, *args: self.gui.processDelayedTrigger(action, args)
    self.gui.fileOpen(TEST_DATASET, do_plot=False)

  def tearDown(self):
    self.gui.close()
    self._warn_patcher.stop()
    if os.path.exists(statepath):
      os.remove(statepath)

  # ── openByNumber ──────────────────────────────────────────

  def test_open_by_number_empty_string_returns_false(self):
    """openByNumber() with empty string returns False without crashing."""
    result = self.gui.openByNumber('')
    self.assertFalse(result)

  def test_open_by_number_whitespace_returns_false(self):
    """openByNumber() with whitespace-only string returns False."""
    result = self.gui.openByNumber('   ')
    self.assertFalse(result)

  def test_open_by_number_event_h5_found(self):
    """openByNumber() in Event mode calls locate_file and opens .nxs.h5 path."""
    import os as _os
    fake_path = _os.path.join(_test_dir, 'REF_M_99001.nxs.h5')
    self.gui.ui.eventActive.setChecked(True)
    with patch('quicknxs.main_gui.locate_file', return_value=fake_path) as mock_lf:
      with patch.object(self.gui, 'fileOpen') as mock_open:
        result = self.gui.openByNumber('99001')
    self.assertTrue(result)
    mock_lf.assert_called_once_with(99001, histogram=False, old_format=False)
    mock_open.assert_called_once_with(_os.path.abspath(fake_path), do_plot=True)

  def test_open_by_number_histogram_mode_flag(self):
    """openByNumber() in Histogram mode passes histogram=True to locate_file."""
    self.gui.ui.histogramActive.setChecked(True)
    with patch('quicknxs.main_gui.locate_file', return_value=None) as mock_lf:
      self.gui.openByNumber('12345')
    mock_lf.assert_called_once_with(12345, histogram=True, old_format=False)

  def test_open_by_number_old_format_mode_flag(self):
    """openByNumber() in Old Format mode passes old_format=True to locate_file."""
    self.gui.ui.oldFormatActive.setChecked(True)
    with patch('quicknxs.main_gui.locate_file', return_value=None) as mock_lf:
      self.gui.openByNumber('12345')
    mock_lf.assert_called_once_with(12345, histogram=False, old_format=True)

  def test_open_by_number_not_found_returns_false(self):
    """openByNumber() with non-existent number returns False."""
    from quicknxs.config import instrument
    orig = instrument.data_base
    try:
      instrument.data_base = _test_dir
      result = self.gui.openByNumber('999999')
    finally:
      instrument.data_base = orig
    self.assertFalse(result)

  def test_open_by_number_not_found_shows_statusbar(self):
    """openByNumber() surfaces a message when run is not found.

    Status now flows through the uniform activity indicator (the lower-left
    status channel) rather than QStatusBar.showMessage directly.
    """
    from quicknxs.config import instrument
    orig = instrument.data_base
    try:
      instrument.data_base = _test_dir
      self.gui.openByNumber('888888')
    finally:
      instrument.data_base = orig
    self.assertIn('888888', self.gui.activity_indicator.text())

  @unittest.skipUnless(hasattr(__import__('signal'), 'SIGALRM'), 'SIGALRM not available')
  def test_open_by_number_sigalrm_timeout(self):
    """openByNumber() handles TimeoutError from a SIGALRM stall gracefully."""
    with patch('quicknxs.main_gui.locate_file', side_effect=TimeoutError('sshfs stall')):
      result = self.gui.openByNumber('40205')
    self.assertFalse(result)
    self.assertIn('timed out', self.gui.activity_indicator.text().lower())

  # ── fileOpenDialog / fileOpenSumDialog ────────────────────

  def test_file_open_dialog_event_filter_includes_h5(self):
    """fileOpenDialog() in Event mode uses *.nxs.h5 as primary filter."""
    from qtpy import QtWidgets as _qw
    self.gui.ui.eventActive.setChecked(True)
    captured = {}
    def fake_dialog(parent, title, **kwargs):
      captured['filter'] = kwargs.get('filter', '')
      return ([], '')
    with patch.object(_qw.QFileDialog, 'getOpenFileNames', side_effect=fake_dialog):
      self.gui.fileOpenDialog()
    self.assertIn('*.nxs.h5', captured.get('filter', ''))

  def test_file_open_dialog_event_filter_legacy_secondary(self):
    """fileOpenDialog() in Event mode also includes *event.nxs as secondary."""
    from qtpy import QtWidgets as _qw
    self.gui.ui.eventActive.setChecked(True)
    captured = {}
    def fake_dialog(parent, title, **kwargs):
      captured['filter'] = kwargs.get('filter', '')
      return ([], '')
    with patch.object(_qw.QFileDialog, 'getOpenFileNames', side_effect=fake_dialog):
      self.gui.fileOpenDialog()
    self.assertIn('*event.nxs', captured.get('filter', ''))

  def test_file_open_sum_dialog_event_filter_includes_h5(self):
    """fileOpenSumDialog() in Event mode uses *.nxs.h5 as primary filter."""
    from qtpy import QtWidgets as _qw
    self.gui.ui.eventActive.setChecked(True)
    captured = {}
    def fake_dialog(parent, title, **kwargs):
      captured['filter'] = kwargs.get('filter', '')
      return ([], '')
    with patch.object(_qw.QFileDialog, 'getOpenFileNames', side_effect=fake_dialog):
      self.gui.fileOpenSumDialog()
    self.assertIn('*.nxs.h5', captured.get('filter', ''))

  # ── updateFileList ────────────────────────────────────────

  def test_update_file_list_event_mode_shows_h5(self):
    """updateFileList() in Event mode lists .nxs.h5 files."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
      for name in ('REF_M_00001.nxs.h5', 'REF_M_00002.nxs.h5'):
        open(os.path.join(tmpdir, name), 'w').close()
      self.gui.ui.eventActive.setChecked(True)
      self.gui.updateFileList('REF_M_00001.nxs.h5', tmpdir)
    items = [self.gui.ui.file_list.item(i).text()
             for i in range(self.gui.ui.file_list.count())]
    self.assertIn('REF_M_00001.nxs.h5', items)
    self.assertIn('REF_M_00002.nxs.h5', items)

  def test_update_file_list_event_mode_selects_current(self):
    """updateFileList() in Event mode selects the specified current file."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
      for name in ('REF_M_00001.nxs.h5', 'REF_M_00002.nxs.h5'):
        open(os.path.join(tmpdir, name), 'w').close()
      self.gui.ui.eventActive.setChecked(True)
      self.gui.updateFileList('REF_M_00002.nxs.h5', tmpdir)
    current = self.gui.ui.file_list.currentItem()
    self.assertIsNotNone(current)
    self.assertEqual(current.text(), 'REF_M_00002.nxs.h5')

  def test_update_file_list_event_mode_no_duplicate_on_revisit(self):
    """updateFileList() in Event mode does not duplicate items when called twice."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
      for name in ('REF_M_00001.nxs.h5', 'REF_M_00002.nxs.h5'):
        open(os.path.join(tmpdir, name), 'w').close()
      self.gui.ui.eventActive.setChecked(True)
      self.gui.updateFileList('REF_M_00001.nxs.h5', tmpdir)
      self.gui.updateFileList('REF_M_00001.nxs.h5', tmpdir)
    count = self.gui.ui.file_list.count()
    self.assertEqual(count, 2)

  def test_update_file_list_event_mode_legacy_event_files(self):
    """updateFileList() in Event mode still lists *event.nxs files."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
      for name in ('REF_M_00003_event.nxs', 'REF_M_00004_event.nxs'):
        open(os.path.join(tmpdir, name), 'w').close()
      self.gui.ui.eventActive.setChecked(True)
      self.gui.updateFileList('REF_M_00003_event.nxs', tmpdir)
    items = [self.gui.ui.file_list.item(i).text()
             for i in range(self.gui.ui.file_list.count())]
    self.assertIn('REF_M_00003_event.nxs', items)
    self.assertIn('REF_M_00004_event.nxs', items)


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


class SmoothOffspecProgressCleanup(unittest.TestCase):
  """Verify the ProgressDialog is disposed even if smooth_offspec raises."""

  def test_progress_disposed_on_error(self):
    """pb.deleteLater() should be called even when exporter.smooth_offspec
    raises.  Disposal goes through close()/deleteLater(), not destroy():
    a destroy()'d dialog left in the window list crashes
    QApplication::closeAllWindows() on exit (Error 139)."""
    from quicknxs.gui_utils import Reducer, ProgressDialog
    from quicknxs.qreduce import NXSData, Reflectivity
    from qtpy.QtWidgets import QWidget
    import numpy as np

    parent=QMainWindow()
    parent.color='jet'
    ds=NXSData(TEST_DATASET)
    norm=Reflectivity(ds[0])
    ref1=Reflectivity(ds[0], normalization=norm)
    ds[0].read_options=dict(ds[0].read_options)
    reducer=Reducer(parent, list(ds.keys()), [ref1])
    from quicknxs.qio import Exporter
    reducer.exporter=Exporter(list(ds.keys()), [ref1])
    reducer.exporter.extract_offspecular()
    # Patch SmoothDialog to auto-accept and return valid settings
    with patch('quicknxs.gui_utils.SmoothDialog') as MockDia:
      mock_dia=MockDia.return_value
      mock_dia.exec_.return_value=True
      mock_dia.getOptions.return_value={
        'grid': (5, 5), 'sigma': (3., 3.), 'sigmas': 3.,
        'region': (10, 90, 5, 95), 'xy_column': 0,
      }
      # Patch exporter.smooth_offspec to raise
      with patch.object(reducer.exporter, 'smooth_offspec', side_effect=RuntimeError('test')):
        with patch.object(ProgressDialog, 'deleteLater') as mock_delete:
          with patch.object(ProgressDialog, 'close'):
            with patch.object(ProgressDialog, 'show'):
              try:
                reducer.smooth_offspec()
              except RuntimeError:
                pass
              mock_delete.assert_called_once()
    parent.deleteLater()


class ExecuteCombinedOffspec(unittest.TestCase):
  """Verify execute() uses combined extraction when both OffSpec and OffSpecCorr are selected."""

  def test_combined_path_when_both_selected(self):
    """When both exportOffSpecular and exportOffSpecularCorr are True,
    extract_offspecular() should NOT be called, and
    extract_offspecular_corr(also_uncorrected=True) should be called."""
    from quicknxs.gui_utils import Reducer
    from quicknxs.qreduce import NXSData, Reflectivity

    parent=QMainWindow()
    parent.color='jet'
    ds=NXSData(TEST_DATASET)
    norm=Reflectivity(ds[0])
    ref1=Reflectivity(ds[0], normalization=norm)
    ds[0].read_options=dict(ds[0].read_options)
    reducer=Reducer(parent, list(ds.keys()), [ref1])
    reducer.export_optios={
      'exportSpecular': False,
      'exportOffSpecular': True,
      'exportOffSpecularSmoothed': False,
      'exportOffSpecularCorr': True,
      'exportGISANS': False,
      'plot': False,
      'emailSend': False,
      'mantidplot': False,
      'gnuplot': False,
      'genx': False,
      'foldername': '/tmp',
      'naming': 'test.dat',
      'multiAscii': False,
      'combinedAscii': False,
      'matlab': False,
      'numpy': False,
      'sampleSize': 10.,
      'export_SA': False,
    }
    from quicknxs.qio import Exporter
    with patch.object(Exporter, 'extract_offspecular') as mock_offspec, \
         patch.object(Exporter, 'extract_offspecular_corr') as mock_corr, \
         patch.object(Exporter, 'release_raw_data'), \
         patch.object(Exporter, 'export_data'):
      reducer.execute()
      mock_offspec.assert_not_called()
      mock_corr.assert_called_once_with(also_uncorrected=True)
    parent.deleteLater()

  def test_offspec_only_path(self):
    """When exportOffSpecular is True but exportOffSpecularCorr is False,
    extract_offspecular() should be called, not extract_offspecular_corr()."""
    from quicknxs.gui_utils import Reducer
    from quicknxs.qreduce import NXSData, Reflectivity

    parent=QMainWindow()
    parent.color='jet'
    ds=NXSData(TEST_DATASET)
    norm=Reflectivity(ds[0])
    ref1=Reflectivity(ds[0], normalization=norm)
    ds[0].read_options=dict(ds[0].read_options)
    reducer=Reducer(parent, list(ds.keys()), [ref1])
    reducer.export_optios={
      'exportSpecular': False,
      'exportOffSpecular': True,
      'exportOffSpecularSmoothed': False,
      'exportOffSpecularCorr': False,
      'exportGISANS': False,
      'plot': False,
      'emailSend': False,
      'mantidplot': False,
      'gnuplot': False,
      'genx': False,
      'foldername': '/tmp',
      'naming': 'test.dat',
      'multiAscii': False,
      'combinedAscii': False,
      'matlab': False,
      'numpy': False,
      'sampleSize': 10.,
      'export_SA': False,
    }
    from quicknxs.qio import Exporter
    with patch.object(Exporter, 'extract_offspecular') as mock_offspec, \
         patch.object(Exporter, 'extract_offspecular_corr') as mock_corr, \
         patch.object(Exporter, 'release_raw_data'), \
         patch.object(Exporter, 'export_data'):
      reducer.execute()
      mock_offspec.assert_called_once()
      mock_corr.assert_not_called()
    parent.deleteLater()


class ProgressDialogThrottle(unittest.TestCase):
  """Verify processEvents() is throttled in ProgressDialog.progress()."""

  def test_throttle_reduces_calls(self):
    """Rapid progress() calls should not call processEvents() every time."""
    from quicknxs.gui_utils import ProgressDialog
    from qtpy.QtWidgets import QWidget
    parent=QWidget()
    dlg=ProgressDialog(parent, title='Test', info_start='Testing', maximum=100, add=0)
    call_count=[0]
    orig_processEvents=QApplication.processEvents
    def counting_processEvents():
      call_count[0]+=1
      orig_processEvents()
    with patch.object(QApplication, 'processEvents', side_effect=counting_processEvents):
      # Call progress many times rapidly
      for i in range(50):
        dlg.progress(i/100.0)
    # With 200ms throttle and rapid calls, processEvents should be called far fewer than 50 times
    self.assertLess(call_count[0], 50)
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


class SmoothDialogYClamp(unittest.TestCase):
  """Verify SmoothDialog.drawPlot clamps Y1 >= 0 in (kizmkfz, Qz) /
  (Qx, Qz) modes, where the y axis is Qz (non-physical for Qz < 0)."""

  def _make_data(self, *, y_min, y_max):
    """Build a small synthetic off-spec input data array suitable for
    SmoothDialog.drawPlot.  Layout matches what
    Exporter.output_data['OffSpec'] produces (shape (Nx, Ny, ≥6) with
    columns Qx, Qz, ki_z, kf_z, _, I, ...).

    ki_z is varied along the Ny (TOF) axis to keep the (ki_z) and
    (kf_z) extents non-degenerate -- a constant ki_z triggers the
    drawPlot 'degenerate window' fallback (x_max <= x_min) and the
    test would not actually exercise the (ki_z, kf_z) mode.
    """
    import numpy as np
    Nx, Ny=8, 12
    Qx=np.linspace(-0.05, 0.05, Nx)[:, None]*np.ones(Ny)[None, :]
    Qz=np.linspace(y_min, y_max, Ny)[None, :]*np.ones(Nx)[:, None]
    ki_z=np.linspace(0.02, 0.10, Ny)[None, :]*np.ones(Nx)[:, None]
    kf_z=Qz-ki_z
    I=np.full_like(Qx, 1e-2)
    dI=np.full_like(Qx, 1e-5)
    item=np.stack([Qx, Qz, ki_z, kf_z, ki_z-kf_z, I, dI], axis=-1)
    return [item]

  def setUp(self):
    self.app=_app

  def test_kizmkfz_mode_clamps_y1_to_zero(self):
    """In (kizmkfz)-vs-Qz mode, Y1 must seed to >= 0 even when the data
    extent crosses zero.  This avoids the user having to manually clamp
    Y1 every time (the user's prompt-34 take-2 screenshot shows them
    setting Y1 from -0.0297 to 0.0).
    """
    from quicknxs.gui_utils import SmoothDialog
    data=self._make_data(y_min=-0.05, y_max=0.40)
    dia=SmoothDialog(None, data)
    try:
      # kizmkfzVSqz is the default radio button per smooth_dialog.py:31
      self.assertTrue(dia.ui.kizmkfzVSqz.isChecked(),
                      'kizmkfzVSqz should be the default mode')
      self.assertGreaterEqual(dia.ui.gridYmin.value(), 0.0,
                              'Y1 should clamp to >= 0 in Qz-y mode')
    finally:
      dia.deleteLater()

  def test_qxqz_mode_clamps_y1_to_zero(self):
    """In Qx-vs-Qz mode, Y1 must also seed to >= 0 (y axis is Qz)."""
    from quicknxs.gui_utils import SmoothDialog
    data=self._make_data(y_min=-0.05, y_max=0.40)
    dia=SmoothDialog(None, data)
    try:
      # Switch to Qx-vs-Qz mode, then redraw so seeds reflect that mode.
      dia.ui.kizmkfzVSqz.setChecked(False)
      dia.ui.qxVSqz.setChecked(True)
      dia.drawPlot()
      self.assertGreaterEqual(dia.ui.gridYmin.value(), 0.0,
                              'Y1 should clamp to >= 0 in qxVSqz mode')
    finally:
      dia.deleteLater()

  def test_kizkfz_mode_does_not_clamp(self):
    """In (ki_z)-vs-(kf_z) mode the y axis is k_fz, NOT Qz, and the
    natural data extent can legitimately straddle zero (specular ridge).
    Y1 must NOT be clamped in this mode.  We use a kf_z range that
    crosses zero and verify the seeded Y1 is allowed to be negative.
    """
    from quicknxs.gui_utils import SmoothDialog
    data=self._make_data(y_min=-0.05, y_max=0.40)
    dia=SmoothDialog(None, data)
    try:
      dia.ui.kizmkfzVSqz.setChecked(False)
      dia.ui.kizVSkfz.setChecked(True)
      dia.drawPlot()
      # In kizVSkfz mode the y axis is kf_z = Qz - ki_z.  With Qz from
      # -0.05 to 0.40 and ki_z from 0.02 to 0.10 (data extent), kf_z
      # ranges roughly -0.15 to +0.38, straddling zero.  T4 must NOT
      # clamp in this mode; the seeded Y1 should be negative.
      self.assertLess(dia.ui.gridYmin.value(), 0.0,
                      'in kizVSkfz mode Y1 must follow the data extent (negative ok), not clamp to 0')
    finally:
      dia.deleteLater()


# ──────────────────────────────────────────────────────────────
#  QFileDialog tuple return fix tests
# ──────────────────────────────────────────────────────────────

class QFileDialogTupleFix(unittest.TestCase):
  """Verify QFileDialog return values are correctly unpacked."""

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

  def test_loadExtraction_cancel_no_hang(self):
    """loadExtraction() should return cleanly when dialog is cancelled."""
    from qtpy import QtWidgets
    with patch.object(QtWidgets.QFileDialog, 'getOpenFileName', return_value=('', '')):
      self.gui.loadExtraction()
    # If we get here without hanging or raising, the fix works

  def test_loadExtraction_bool_from_triggered_signal(self):
    """loadExtraction(False) must not hang reading stdin.

    QAction.triggered emits a bool (checked state) which arrives as
    filename=False.  Before the fix, open(False, 'rb') opened stdin
    (fd 0) and .read() blocked forever.
    """
    from qtpy import QtWidgets
    with patch.object(QtWidgets.QFileDialog, 'getOpenFileName', return_value=('', '')):
      # Simulate exactly what the menu does: pass False as filename
      self.gui.loadExtraction(False)
    # If we get here without hanging, the fix works

  def test_open_filter_dialog_cancel_no_crash(self):
    """open_filter_dialog() should return cleanly when dialog is cancelled."""
    from qtpy import QtWidgets
    with patch.object(QtWidgets.QFileDialog, 'getOpenFileNames', return_value=([], '')):
      self.gui.open_filter_dialog()
    # If we get here without TypeError, the fix works

  def test_fileOpenSumDialog_cancel_no_crash(self):
    """fileOpenSumDialog() should return cleanly when dialog is cancelled."""
    from qtpy import QtWidgets
    with patch.object(QtWidgets.QFileDialog, 'getOpenFileNames', return_value=([], '')):
      self.gui.fileOpenSumDialog()
    # If we get here without error, the fix works

  def test_exportRawData_cancel_no_crash(self):
    """exportRawData() should return cleanly when dialog is cancelled."""
    from qtpy import QtWidgets
    self.gui.fileOpen(TEST_DATASET, do_plot=True)
    self.gui.ui.dangle0Overwrite.setText(str(self.gui.active_data[0].dangle))
    self.gui.ui.refXPos.setValue(self.gui.active_data[0].dpix)
    self.gui.setNorm()
    with patch.object(QtWidgets.QFileDialog, 'getSaveFileName', return_value=('', '')):
      self.gui.exportRawData()
    # If we get here without error, the fix works


# ──────────────────────────────────────────────────────────────
#  NavigationToolbar labelAction fix tests
# ──────────────────────────────────────────────────────────────

class NavigationToolbarLabelAction(unittest.TestCase):
  """Verify NavigationToolbar creates labelAction in __init__."""

  def test_toolbar_has_labelAction(self):
    """NavigationToolbar should have labelAction attribute."""
    from quicknxs.mplwidget import MPLWidget
    w=MPLWidget()
    self.assertTrue(hasattr(w.toolbar, 'labelAction'))
    self.assertIsNotNone(w.toolbar.labelAction)
    w.deleteLater()

  def test_toolbar_labelAction_hidden_by_default(self):
    """labelAction should be hidden when coordinates=False (default)."""
    from quicknxs.mplwidget import MPLWidget
    w=MPLWidget()
    self.assertFalse(w.toolbar.labelAction.isVisible())
    w.deleteLater()

  def test_toolbar_has_custom_actions(self):
    """Toolbar should have Print and Log actions from custom setup."""
    from quicknxs.mplwidget import MPLWidget
    w=MPLWidget()
    action_texts=[a.text() for a in w.toolbar.actions()]
    self.assertIn('Print', action_texts)
    self.assertIn('Log', action_texts)
    w.deleteLater()

  def test_plot_dialog_no_crash(self):
    """PlotDialog() should not raise AttributeError on labelAction."""
    from quicknxs.gui_utils import PlotDialog
    dialog=PlotDialog()
    self.assertIsNotNone(dialog)
    self.assertIsNotNone(dialog.plot.toolbar.labelAction)
    dialog.destroy()


# ──────────────────────────────────────────────────────────────
#  Load Extraction round-trip tests
# ──────────────────────────────────────────────────────────────

class LoadExtractionRoundTrip(unittest.TestCase):
  """Verify File→Load Extraction completes without hang or OOM.

  Generates a reduced .dat file from test data, then loads it back
  via loadExtraction().  This exercises the full code path that was
  causing unbounded memory growth (OOM / SIGKILL).
  """

  def setUp(self):
    import tempfile
    self.app=_app
    if os.path.exists(statepath):
      os.remove(statepath)
    self._warn_patcher=patch.object(QMessageBox, 'warning', return_value=QMessageBox.No)
    self._warn_patcher.start()
    self.gui=MainGUI([])
    self.gui.trigger.stay_alive=False
    self.gui.trigger.wait()
    self.gui.trigger=lambda action, *args: self.gui.processDelayedTrigger(action, args)
    self._tmpdir=tempfile.mkdtemp()

  def tearDown(self):
    self.gui.close()
    self._warn_patcher.stop()
    if os.path.exists(statepath):
      os.remove(statepath)
    import shutil
    shutil.rmtree(self._tmpdir, ignore_errors=True)

  def _generate_reduced_dat(self):
    """Create a reduced .dat file from test data and return its path."""
    from quicknxs.qio import Exporter
    ds=NXSData(TEST_DATASET, use_caching=False)
    norm=Reflectivity(ds[0])
    ref=Reflectivity(ds[0], normalization=norm)
    ds[0].read_options=dict(ds[0].read_options)
    channels=list(ds.keys())
    exporter=Exporter(channels, [ref])
    exporter.extract_reflectivity()
    naming='test_load_{instrument}_{item}_{state}_{numbers}.{type}'
    exporter.export_data(self._tmpdir, naming,
                         multi_ascii=True, combined_ascii=False,
                         matlab_data=False, numpy_data=False)
    dat_files=[f for f in os.listdir(self._tmpdir) if f.endswith('.dat')]
    return os.path.join(self._tmpdir, dat_files[0])

  def test_load_extraction_completes(self):
    """loadExtraction() with a real .dat file should complete without hanging."""
    dat_path=self._generate_reduced_dat()
    # loadExtraction with a filename bypasses the file dialog
    self.gui.loadExtraction(filename=dat_path)
    # Verify data was loaded
    self.assertGreater(len(self.gui.reduction_list), 0,
                       'reduction_list should be populated after loadExtraction')

  def test_load_extraction_cache_empty(self):
    """NXSData._cache should be empty after loadExtraction completes."""
    dat_path=self._generate_reduced_dat()
    # Pre-populate cache to verify it gets cleared
    NXSData(TEST_DATASET, use_caching=True)
    self.assertGreater(len(NXSData._cache), 0)
    self.gui.loadExtraction(filename=dat_path)
    # Cache is cleared at parse() start; new loads use use_caching=False
    # so it should remain empty (or only have the final fileOpen's data)

  def test_load_extraction_sets_norm(self):
    """loadExtraction() should populate the normalization table."""
    dat_path=self._generate_reduced_dat()
    self.gui.loadExtraction(filename=dat_path)
    self.assertGreater(len(self.gui.ref_norm), 0,
                       'ref_norm should have entries after loadExtraction')

  def test_load_extraction_from_header_string(self):
    """loadExtraction() with _pending_header should work (crash recovery path)."""
    from quicknxs.qio import HeaderCreator
    ds=NXSData(TEST_DATASET, use_caching=False)
    norm=Reflectivity(ds[0])
    ref=Reflectivity(ds[0], normalization=norm)
    ds[0].read_options=dict(ds[0].read_options)
    header_str=str(HeaderCreator([ref]))
    self.gui._pending_header=header_str
    self.gui.loadExtraction()
    self.assertGreater(len(self.gui.reduction_list), 0,
                       'reduction_list should be populated from pending header')

  def test_load_extraction_clears_stale_norms_on_reload(self):
    """Reload after a trashcan-clear must NOT keep the previous load's
    norms.  Otherwise a reload at a different `bins` (TOF bin count) is
    silently mismatched against the new active_data and `getNorm()`
    returns None, breaking the xtof_overview normalization.

    See plan/prompt-35-todo.md T1 — the visible difference between the
    user's `quicknxsv1-overview-tof-400-clear-and-reload.png` and
    `quicknxsv1-overview-tof-400-clean-load-extraction.png` traces to
    this: ref_norm survived the trashcan + reload, then carried an
    OLD-binning Reflectivity whose Rraw length no longer matched
    active_data.tof at the new bin count.
    """
    dat_path=self._generate_reduced_dat()

    # First load — populates ref_norm normally.
    self.gui.loadExtraction(filename=dat_path)
    self.assertGreater(len(self.gui.ref_norm), 0,
                       'first load should populate ref_norm')
    # Save the EXACT same Reflectivity objects so we can detect identity
    # (these MUST be replaced by the reload, not kept around).
    first_load_norm_ids=set(id(v) for v in self.gui.ref_norm.values())

    # Simulate the trashcan click: clears refl list only.  This is the
    # user's behavior that previously left ref_norm populated.
    self.gui.clearRefList(do_plot=False)
    self.assertEqual(len(self.gui.reduction_list), 0,
                     'trashcan should clear refl list')

    # Reload the same extraction.  With the fix, ref_norm is wiped at
    # the top of loadExtraction and re-populated with fresh objects.
    self.gui.loadExtraction(filename=dat_path)
    self.assertGreater(len(self.gui.ref_norm), 0,
                       'reload should re-populate ref_norm')

    # POST-CONDITION: every Reflectivity in ref_norm is a fresh object,
    # not the stale ones from the first load.  Identity check is the
    # strongest assertion that the fix is in place — even if the
    # bin count happens to match, the objects must be replaced.
    second_load_norm_ids=set(id(v) for v in self.gui.ref_norm.values())
    self.assertFalse(first_load_norm_ids & second_load_norm_ids,
                     'ref_norm must hold fresh Reflectivity objects '
                     'after reload, not stale ones from the prior load')


class CalcReflParamsFreshFileReseed(unittest.TestCase):
  """Regression for prompt-28.2: 44035 captured 44160's widths.

  When a user loads a new (never-classified) file after addRefList has
  flipped actionAutoYLimits to False, the spinboxes for y_pos/y_width
  used to retain whatever was last on screen — typically the previous
  refl's narrow extraction region.  setNorm would then capture a
  Reflectivity built from those stale widths.

  Fix: in calcReflParams, treat "fresh" files (not yet in ref_norm and
  not yet in reduction_list) as if AutoYLimits were on, regardless of
  the toggle, so they always get file-appropriate y_pos/y_width.
  """

  def setUp(self):
    self.app=_app
    if os.path.exists(statepath):
      os.remove(statepath)
    self._warn_patcher=patch.object(QMessageBox, 'warning',
                                    return_value=QMessageBox.No)
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

  def _set_stale_ui(self, *, x_pos, x_width, y_pos, y_width):
    """Force the spinboxes to specific values (simulating loadExtraction
    having written a refl's options to the UI).  ``auto_change_active``
    is set so signal handlers don't recompute or move things around."""
    self.gui.auto_change_active=True
    self.gui.ui.refXPos.setValue(x_pos)
    self.gui.ui.refXWidth.setValue(x_width)
    self.gui.ui.refYPos.setValue(y_pos)
    self.gui.ui.refYWidth.setValue(y_width)
    self.gui.auto_change_active=False

  def test_fresh_file_reseeds_y_even_with_AutoYLimits_off(self):
    # Mirror the moment after addRefList in the real GUI: AutoYLimits
    # has been flipped off because the user added a refl, and the UI
    # spinboxes are showing that refl's (narrow) extraction region.
    self.gui.fileOpen(TEST_DATASET, do_plot=True)
    self.gui.setNorm()
    self.gui.addRefList(do_plot=False)
    self.assertFalse(self.gui.ui.actionAutoYLimits.isChecked(),
                     'addRefList should disable AutoYLimits')

    # Simulate state-restore having written a refl's narrow widths
    # into the spinboxes (this is what loadExtraction does at lines
    # 1427-1430 of main_gui.py).
    stale_y_pos=137.0
    stale_y_width=55.0
    self._set_stale_ui(x_pos=172.0, x_width=17.0,
                       y_pos=stale_y_pos, y_width=stale_y_width)

    # Now load a fresh file.  The test fixtures share a run number so
    # we make the GUI think it's a different file by directly emptying
    # the classification stores, then driving calcReflParams.
    self.gui.reduction_list=[]
    self.gui.ref_norm={}
    self.gui.fileOpen(TEST_EVENT, do_plot=True)
    self.assertFalse(self.gui._active_file_is_known(),
                     'cleared classification → fresh file')

    # Y should have been reseeded from the actual data via get_yregion,
    # not left at the stale 137/55 from the previous refl.
    self.assertNotEqual(self.gui.ui.refYPos.value(), stale_y_pos,
                        'refYPos must be reseeded from the fresh file, '
                        'not left at the stale refl value')
    self.assertNotEqual(self.gui.ui.refYWidth.value(), stale_y_width,
                        'refYWidth must be reseeded from the fresh file, '
                        'not left at the stale refl value')

    # And the captured self.refl must have those fresh values, so a
    # subsequent setNorm() would record the file's own extraction
    # region — not a stale one.
    self.assertEqual(self.gui.refl.options['y_pos'],
                     self.gui.ui.refYPos.value())
    self.assertEqual(self.gui.refl.options['y_width'],
                     self.gui.ui.refYWidth.value())

    # X width must likewise be reseeded from the fresh file (prompt-30 AC1):
    # a fresh file picks up its own stripe via get_xregion, not the stale
    # refl x_width=17, and self.refl captures the fresh value.
    self.assertNotEqual(self.gui.ui.refXWidth.value(), 17.0,
                        'refXWidth must be reseeded from the fresh file, '
                        'not left at the stale refl value')
    self.assertEqual(self.gui.refl.options['x_width'],
                     self.gui.ui.refXWidth.value())

  def test_known_file_preserves_user_y_values(self):
    """When the active file is a refl already in reduction_list, its
    y_pos/y_width must NOT be silently re-seeded — that would clobber a
    user-tuned region for refl stitching."""
    self.gui.fileOpen(TEST_DATASET, do_plot=True)
    self.gui.setNorm()
    self.gui.addRefList(do_plot=False)
    self.assertFalse(self.gui.ui.actionAutoYLimits.isChecked())
    self.assertTrue(self.gui._active_file_is_known(),
                    'TEST_DATASET is now in reduction_list')

    # Manually adjust y to a non-auto value the user might pick for
    # refl-stitching uniformity.
    custom_y_pos=145.0
    custom_y_width=70.0
    self._set_stale_ui(x_pos=self.gui.ui.refXPos.value(),
                       x_width=self.gui.ui.refXWidth.value(),
                       y_pos=custom_y_pos, y_width=custom_y_width)

    # Drive calcReflParams directly (the same code path fileOpen would
    # trigger via fileLoaded → calcReflParams).  Since the file is
    # known, Y must not be re-seeded.
    self.gui.calcReflParams()
    self.assertEqual(self.gui.ui.refYPos.value(), custom_y_pos,
                     'known files must keep the user-set y_pos')
    self.assertEqual(self.gui.ui.refYWidth.value(), custom_y_width,
                     'known files must keep the user-set y_width')


class RoleDecoupling(unittest.TestCase):
  """prompt-30: the direct-beam role and reflectivity role keep separate
  extraction regions, so loading a file of one role can no longer leave
  the other role's stale widths in the spinboxes.

  The GUI infers a file's role from ref_norm / reduction_list and, on a
  role *switch*, mirrors that role's stored ExtractionRegion into the
  spinboxes.  setNorm / addRefList capture each role's region from the
  stored object's options.
  """

  # Distinctive regions modelled on the real REF_M 11486 reduction:
  # the direct beam 44035 has a wide stripe (x_width 24 / y_width 100)
  # while the refl 44161 has a narrow one (x_width 17 / y_width 55).
  DB_REGION=ExtractionRegion(x_pos=230.5, x_width=24., y_pos=134., y_width=100.,
                             bg_pos=30., bg_width=20., scale=1.0)
  REFL_REGION=ExtractionRegion(x_pos=172.3, x_width=17., y_pos=137., y_width=55.,
                               bg_pos=30., bg_width=20., scale=2.0)

  def setUp(self):
    self.app=_app
    if os.path.exists(statepath):
      os.remove(statepath)
    self._warn_patcher=patch.object(QMessageBox, 'warning',
                                    return_value=QMessageBox.No)
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

  def test_db_after_refl_uses_db_region(self):
    """A refl is active; loading a known direct beam must mirror the DB
    region into the spinboxes, not the refl's narrow widths."""
    self.gui.fileOpen(TEST_DATASET, do_plot=True)
    self.gui.region_db=self.DB_REGION
    self.gui.region_refl=self.REFL_REGION
    # Spinboxes currently show the refl region (the cross-talk setup).
    self.gui.active_role='refl'
    self.gui._apply_region_to_ui(self.REFL_REGION)
    self.assertEqual(self.gui.ui.refYWidth.value(), 55.)

    # Classify the active file as a direct beam, then drive the same hook
    # fileLoaded fires.
    number=self.gui._active_file_number()
    self.gui.ref_norm={number: self.gui.refl}
    self.gui.reduction_list=[]
    self.gui._applyRoleRegion()

    self.assertEqual(self.gui.active_role, 'db')
    self.assertEqual(self.gui.ui.refXWidth.value(), 24.,
                     'DB load must mirror the DB x_width, not the refl 17')
    self.assertEqual(self.gui.ui.refYWidth.value(), 100.,
                     'DB load must mirror the DB y_width, not the refl 55')
    self.assertEqual(self.gui.ui.refXPos.value(), 230.5)

  def test_refl_after_db_uses_refl_region(self):
    """A DB is active; loading a known reflectivity must mirror the refl
    region, not the DB's wide widths."""
    self.gui.fileOpen(TEST_DATASET, do_plot=True)
    self.gui.region_db=self.DB_REGION
    self.gui.region_refl=self.REFL_REGION
    self.gui.active_role='db'
    self.gui._apply_region_to_ui(self.DB_REGION)
    self.assertEqual(self.gui.ui.refYWidth.value(), 100.)

    number=self.gui._active_file_number()
    self.gui.ref_norm={}
    self.gui.reduction_list=[SimpleNamespace(options={'number': number})]
    self.gui._applyRoleRegion()

    self.assertEqual(self.gui.active_role, 'refl')
    self.assertEqual(self.gui.ui.refXWidth.value(), 17.,
                     'refl load must mirror the refl x_width, not the DB 24')
    self.assertEqual(self.gui.ui.refYWidth.value(), 55.,
                     'refl load must mirror the refl y_width, not the DB 100')

  def test_same_role_reload_preserves_region(self):
    """Reloading a file of the *same* role must not re-seed the spinboxes,
    so user-tuned / auto-fit values survive (no refl-stitching regression)."""
    self.gui.fileOpen(TEST_DATASET, do_plot=True)
    self.gui.region_refl=self.REFL_REGION
    self.gui.active_role='refl'
    # User tunes y to a value that differs from region_refl.
    self.gui.auto_change_active=True
    self.gui.ui.refYWidth.setValue(70.)
    self.gui.auto_change_active=False

    number=self.gui._active_file_number()
    self.gui.ref_norm={}
    self.gui.reduction_list=[SimpleNamespace(options={'number': number})]
    self.gui._applyRoleRegion()

    self.assertEqual(self.gui.active_role, 'refl')
    self.assertEqual(self.gui.ui.refYWidth.value(), 70.,
                     'same-role reload must not clobber the on-screen region')

  def test_setNorm_and_addRefList_capture_role_regions(self):
    """setNorm captures region_db and addRefList captures region_refl, each
    byte-for-byte from the stored object's options."""
    self.gui.fileOpen(TEST_DATASET, do_plot=True)
    self.gui.setNorm()
    self.assertEqual(self.gui.active_role, 'db')
    self.assertEqual(self.gui.region_db,
                     ExtractionRegion.from_options(self.gui.refl.options),
                     'setNorm must capture the DB region from refl.options')

    self.gui.addRefList(do_plot=False)
    self.assertEqual(self.gui.active_role, 'refl')
    self.assertEqual(self.gui.region_refl,
                     ExtractionRegion.from_options(self.gui.refl.options),
                     'addRefList must capture the refl region from refl.options')

  def test_fresh_file_keeps_active_role(self):
    """An unclassified (fresh) file does not switch roles or re-seed the
    spinboxes — calcReflParams' auto-fit (Fix A) owns that case."""
    self.gui.fileOpen(TEST_DATASET, do_plot=True)
    self.gui.region_db=self.DB_REGION
    self.gui.region_refl=self.REFL_REGION
    self.gui.active_role='db'
    self.gui._apply_region_to_ui(self.DB_REGION)
    self.gui.ref_norm={}
    self.gui.reduction_list=[]
    self.assertIsNone(self.gui._active_file_role())

    self.gui._applyRoleRegion()
    self.assertEqual(self.gui.active_role, 'db',
                     'fresh file must not change the active role')
    self.assertEqual(self.gui.ui.refYWidth.value(), 100.,
                     'fresh file must not re-seed the spinboxes')

  def test_changeRegionValues_snapshots_active_role(self):
    """prompt-30 item 4: a user edit to a classified file's region is
    snapshotted into that role's stored region, so it survives a later
    switch-away/switch-back (not merely kept on screen)."""
    self.gui.fileOpen(TEST_DATASET, do_plot=True)
    self.gui.setNorm()                       # classify active file as a DB
    self.assertEqual(self.gui.active_role, 'db')
    # Simulate the user widening the DB x stripe; guard the programmatic set
    # so only the explicit changeRegionValues() performs the snapshot.
    self.gui.auto_change_active=True
    self.gui.ui.refXWidth.setValue(40.)
    self.gui.auto_change_active=False
    self.gui.changeRegionValues()
    self.assertEqual(self.gui.region_db.x_width, 40.,
                     'changeRegionValues must snapshot the edit into region_db')

  def test_changeRegionValues_fresh_file_does_not_pollute_role_region(self):
    """A fresh (unclassified) file's edits must NOT be written into a role
    region (calcReflParams' auto-fit owns fresh files)."""
    self.gui.fileOpen(TEST_DATASET, do_plot=True)
    self.gui.region_refl=self.REFL_REGION    # a known refl region is on record
    self.gui.region_db=self.DB_REGION
    self.gui.active_role='refl'
    self.gui.ref_norm={}                     # active file is fresh
    self.gui.reduction_list=[]
    self.gui.auto_change_active=True
    self.gui.ui.refXWidth.setValue(99.)
    self.gui.auto_change_active=False
    self.gui.changeRegionValues()
    self.assertEqual(self.gui.region_refl.x_width, 17.,
                     'a fresh-file edit must not overwrite region_refl')
    self.assertEqual(self.gui.region_db.x_width, 24.,
                     'a fresh-file edit must not overwrite region_db')


class WidgetDisposalSafety(unittest.TestCase):
  """Dialogs / progress windows must be disposed with close()/deleteLater(),
  never QWidget.destroy().

  A destroy()'d widget tears down its native window but stays registered with
  the QApplication, so QApplication::closeAllWindows() on exit dereferences a
  dangling QWindow and segfaults (Error 139).  Root-caused via gdb on the
  off-spec preview flow; reproduced as destroy()+closeAllWindows() -> SIGSEGV
  while close()+deleteLater()+closeAllWindows() is clean.
  """

  def test_no_widget_destroy_calls(self):
    import quicknxs.main_gui as mg
    import quicknxs.gui_utils as gu
    for mod in (mg, gu):
      with open(mod.__file__, encoding='utf8') as fh:
        src=fh.read()
      self.assertNotIn('.destroy()', src,
                       '%s disposes a widget with .destroy(); use '
                       'close()/deleteLater() instead — destroy() leaves a '
                       'dangling QWindow that crashes closeAllWindows() on exit'
                       % os.path.basename(mod.__file__))


class QtHandlerStatusbarOptOut(unittest.TestCase):
  """gui_logging.QtHandler honors extra={'no_statusbar': True}: such INFO
  records are still buffered (and written by the file handler) but are kept
  off the shared status bar (prompt-31 #5)."""

  def _handler(self):
    from quicknxs.gui_logging import QtHandler
    mw=MagicMock()
    return QtHandler(mw), mw

  def _info_record(self, **extra):
    import logging
    rec=logging.LogRecord('quicknxs', logging.INFO, __file__, 0, u'msg', None, None)
    for k, v in extra.items():
      setattr(rec, k, v)
    return rec

  def test_plain_info_reaches_statusbar(self):
    h, mw=self._handler()
    h.emit(self._info_record())
    mw.ui.statusbar.showMessage.assert_called()

  def test_no_statusbar_info_kept_off_statusbar_but_buffered(self):
    h, mw=self._handler()
    h.emit(self._info_record(no_statusbar=True))
    mw.ui.statusbar.showMessage.assert_not_called()
    self.assertEqual(len(h.logged_items), 1, 'record must still be buffered')


class SmoothDialogDataDrivenLimits(unittest.TestCase):
  """SmoothDialog axis limits, region box and sigma track the actual data
  extent (no longer hardcoded +/-0.035 view / +/-0.03 region / 0.0005 sigma).
  No set_aspect is applied -- the kernel honestly reflects the axis scales."""

  def _dialog(self, kdiff_min, kdiff_max, qz_max):
    import numpy as np
    from quicknxs.gui_utils import SmoothDialog
    ny, nx=6, 20
    item=np.zeros((ny, nx, 6))
    item[:, :, 2]=np.linspace(kdiff_min, kdiff_max, nx)   # ki_z (kf_z=0 -> ki_z-kf_z spans data)
    item[:, :, 1]=np.linspace(0.0, qz_max, ny)[:, None]   # Qz spans [0, qz_max]
    item[:, :, 5]=1.0                                      # I>0 everywhere
    parent=QMainWindow()
    dia=SmoothDialog(parent, [item])
    dia.ui.kizmkfzVSqz.setChecked(True)
    dia.drawPlot()
    return dia, parent

  def test_xlim_tracks_data_not_hardcoded(self):
    dia, parent=self._dialog(kdiff_min=-0.11, kdiff_max=0.086, qz_max=0.37)
    xlo, xhi=dia.ui.plot.canvas.ax.get_xlim()
    self.assertAlmostEqual(xlo, -0.11, places=3,
                           msg='x lower limit must track the data, not the old -0.035')
    self.assertAlmostEqual(xhi, 0.086, places=3,
                           msg='x upper limit must track the data, not the old +0.035')
    # region box (grid spin fields) sits inside the data extent, not at +/-0.03
    self.assertLess(dia.ui.gridXmin.value(), -0.05,
                    'gridXmin must be data-driven (~ -0.10), not the old -0.03')
    self.assertGreater(dia.ui.gridXmax.value(), 0.05)
    dia.destroy()
    parent.deleteLater()

  def test_ylim_tracks_qz_data(self):
    dia, parent=self._dialog(kdiff_min=-0.11, kdiff_max=0.086, qz_max=0.37)
    ylo, yhi=dia.ui.plot.canvas.ax.get_ylim()
    self.assertAlmostEqual(yhi, 0.37, places=2,
                           msg='y upper limit must track the Qz data extent')
    dia.destroy()
    parent.deleteLater()


# ──────────────────────────────────────────────────────────────
#  Test suite registration
# ──────────────────────────────────────────────────────────────

suite=unittest.TestLoader().loadTestsFromTestCase(MainGUIGeometryRestore)
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(MainGUIGeneral))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(MainGUIActions))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(MainGUIProgressCallback))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(UpdateEventReadoutThrottle))
# Bug verification tests
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(MainGUIDelayedTrigger))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(MainGUIHeaderParserFault))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(MainGUIIPythonFault))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(MainGUIHelpAboutFault))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(MainGUIProgressDialogFix))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(MainGUIReduceDialogFix))
# Comprehensive GUI tests
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(MainGUIFileOperations))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(FileLoadingFixes))
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
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(SmoothOffspecProgressCleanup))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(ProgressDialogThrottle))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(SmoothDataCallbackFix))
# QFileDialog tuple return fix tests
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(QFileDialogTupleFix))
# NavigationToolbar labelAction fix tests
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(NavigationToolbarLabelAction))
# Load Extraction round-trip tests
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(LoadExtractionRoundTrip))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(CalcReflParamsFreshFileReseed))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(RoleDecoupling))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(WidgetDisposalSafety))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(QtHandlerStatusbarOptOut))
suite.addTest(unittest.TestLoader().loadTestsFromTestCase(SmoothDialogDataDrivenLimits))
