#-*- coding: utf-8 -*-
"""Tests for quicknxs.activity_status.ActivityIndicator."""

import unittest

from qtpy.QtWidgets import QApplication, QStatusBar
from qtpy.QtTest import QTest

from quicknxs.activity_status import ActivityIndicator

# Single QApplication for all tests
_app = QApplication.instance() or QApplication([])


class ActivityIndicatorTest(unittest.TestCase):
  def setUp(self):
    self.statusbar = QStatusBar()
    # short, non-zero durations so the real-time test is fast
    self.ind = ActivityIndicator(self.statusbar, hold_ms=40, fade_ms=40)

  def tearDown(self):
    self.ind.clear()
    self.statusbar.deleteLater()

  def test_label_added_to_statusbar(self):
    # The indicator's label must live in the status bar so it is visible.
    self.assertIs(self.ind._label.parent(), self.statusbar)

  def test_show_busy_sets_text_no_fade(self):
    self.ind.show_busy(u'Loading run 12345...')
    self.assertEqual(self.ind.text(), u'Loading run 12345...')
    self.assertEqual(self.ind.opacity(), 1.0)
    self.assertFalse(self.ind.is_holding())
    self.assertFalse(self.ind.is_fading())

  def test_show_busy_clears_transient_statusbar_message(self):
    # A transient showMessage would otherwise hide our addWidget label.
    self.statusbar.showMessage(u'something transient')
    self.ind.show_busy(u'Working...')
    self.assertEqual(self.statusbar.currentMessage(), u'')

  def test_show_complete_holds_then_fades(self):
    self.ind.show_complete(u'Complete')
    self.assertEqual(self.ind.text(), u'Complete')
    self.assertEqual(self.ind.opacity(), 1.0)
    self.assertTrue(self.ind.is_holding())

  def test_show_complete_default_message(self):
    self.ind.show_complete()
    self.assertEqual(self.ind.text(), u'Complete')

  def test_busy_cancels_pending_complete(self):
    # A new action arriving during the Complete hold must cancel the fade.
    self.ind.show_complete(u'Complete')
    self.assertTrue(self.ind.is_holding())
    self.ind.show_busy(u'Next action...')
    self.assertFalse(self.ind.is_holding())
    self.assertFalse(self.ind.is_fading())
    self.assertEqual(self.ind.text(), u'Next action...')
    self.assertEqual(self.ind.opacity(), 1.0)

  def test_clear_empties_and_stops(self):
    self.ind.show_complete(u'Complete')
    self.ind.clear()
    self.assertEqual(self.ind.text(), u'')
    self.assertFalse(self.ind.is_holding())
    self.assertFalse(self.ind.is_fading())

  def test_fade_finished_resets_for_reuse(self):
    # After a fade completes the label is blank but opacity is restored to 1
    # so the next message is fully visible.
    self.ind.show_complete(u'Complete')
    self.ind._start_fade()
    self.ind._on_fade_finished()
    self.assertEqual(self.ind.text(), u'')
    self.assertEqual(self.ind.opacity(), 1.0)

  def test_zero_durations_clear_immediately(self):
    ind = ActivityIndicator(self.statusbar, hold_ms=0, fade_ms=0)
    ind.show_complete(u'Done')
    # hold_ms<=0 -> _start_fade, fade_ms<=0 -> _on_fade_finished synchronously
    self.assertEqual(ind.text(), u'')

  def test_realtime_complete_fades_to_blank(self):
    # End-to-end: drive the actual timer + animation through the event loop.
    self.ind.show_complete(u'Complete')
    # hold (40) + fade (40) + margin
    QTest.qWait(200)
    self.assertEqual(self.ind.text(), u'')


if __name__ == '__main__':
  unittest.main()
