"""
Status-bar activity indicator.

QuickNXS does all of its work on the GUI thread, so any handler that loads a
file, runs a reduction, or redraws a matplotlib canvas freezes the window for
the full duration (measured at 0.2-4 s).  Nothing tells the user the click even
registered, which is the whole "not crisp" complaint.

``ActivityIndicator`` is the single channel for two states:

* **busy**  -- a persistent message shown the instant an action starts (the
  caller pairs it with a wait cursor and ``processEvents`` so it actually
  paints before the blocking work begins);
* **complete** -- a transient message shown when the GUI returns to idle, which
  *fades out* after a short hold so it does not clutter the status bar.

The widget is a single ``QLabel`` inserted at the left of the status bar with a
``QGraphicsOpacityEffect`` driven by a ``QPropertyAnimation`` for the fade.  It
calls ``statusbar.clearMessage()`` before showing text so it stays visible over
any transient ``showMessage`` (e.g. from the logging bridge).
"""

from qtpy import QtCore, QtWidgets


class ActivityIndicator(QtCore.QObject):
  """Own a status-bar label that shows busy text and a fading 'Complete'.

  :param statusbar: the ``QStatusBar`` to host the label in.
  :param hold_ms: how long the completion message stays fully opaque before
      it starts to fade.
  :param fade_ms: duration of the opacity fade-out.
  """

  def __init__(self, statusbar, hold_ms=2000, fade_ms=1200, settle_ms=400, parent=None):
    super(ActivityIndicator, self).__init__(parent or statusbar)
    self._statusbar = statusbar
    self.hold_ms = hold_ms
    self.fade_ms = fade_ms
    self.settle_ms = settle_ms

    self._label = QtWidgets.QLabel(u'')
    self._label.setObjectName(u'activityStatus')
    self._label.setContentsMargins(4, 0, 0, 0)
    # stretch=1 so the label occupies the left region of the status bar, the
    # same area QStatusBar.showMessage() uses for transient text.
    statusbar.addWidget(self._label, 1)

    self._effect = QtWidgets.QGraphicsOpacityEffect(self._label)
    self._effect.setOpacity(1.0)
    self._label.setGraphicsEffect(self._effect)

    self._fade = QtCore.QPropertyAnimation(self._effect, b'opacity', self)
    self._fade.setDuration(self.fade_ms)
    self._fade.setStartValue(1.0)
    self._fade.setEndValue(0.0)
    self._fade.finished.connect(self._on_fade_finished)

    self._hold = QtCore.QTimer(self)
    self._hold.setSingleShot(True)
    self._hold.timeout.connect(self._start_fade)

    # Coalescing timer for high-frequency inputs (spinbox drags): each change
    # restarts it; when the user stops, it fires and surfaces "Complete".
    self._settle = QtCore.QTimer(self)
    self._settle.setSingleShot(True)
    self._settle.timeout.connect(self._on_settle)

  # -- queries (used by tests and callers) ----------------------------------
  def text(self):
    return self._label.text()

  def opacity(self):
    return self._effect.opacity()

  def is_holding(self):
    return self._hold.isActive()

  def is_fading(self):
    return self._fade.state() == QtCore.QAbstractAnimation.Running

  def is_settling(self):
    return self._settle.isActive()

  # -- state transitions -----------------------------------------------------
  def _quiesce(self):
    """Cancel any in-flight settle / hold timer or fade animation, reset opacity."""
    self._settle.stop()
    self._hold.stop()
    self._fade.stop()
    self._effect.setOpacity(1.0)

  def show_busy(self, message):
    """Show a persistent message immediately (no fade)."""
    self._quiesce()
    self._statusbar.clearMessage()
    self._label.setText(message)

  def show_complete(self, message=u'Complete'):
    """Show a message that holds, then fades out."""
    self._quiesce()
    self._statusbar.clearMessage()
    self._label.setText(message)
    if self.hold_ms <= 0:
      self._start_fade()
    else:
      self._hold.start(self.hold_ms)

  def busy_until_idle(self, message, done=u'Complete'):
    """Coalesced busy state for high-frequency inputs (e.g. spinbox drags).

    Shows *message* persistently and (re)starts the settle timer; when the
    caller stops invoking this for ``settle_ms``, a fading *done* message is
    surfaced.  Avoids one "Complete" flash per value change.
    """
    self._quiesce()
    self._statusbar.clearMessage()
    self._label.setText(message)
    self._settle_done = done
    if self.settle_ms <= 0:
      self.show_complete(done)
    else:
      self._settle.start(self.settle_ms)

  def clear(self):
    """Immediately remove any message and stop timers/animation."""
    self._quiesce()
    self._label.setText(u'')

  # -- internals -------------------------------------------------------------
  def _on_settle(self):
    # Input has stopped: transition the coalesced busy state to "Complete".
    self.show_complete(getattr(self, '_settle_done', u'Complete'))

  def _start_fade(self):
    self._fade.stop()
    self._effect.setOpacity(1.0)
    if self.fade_ms <= 0:
      self._on_fade_finished()
      return
    self._fade.start()

  def _on_fade_finished(self):
    # Only blank the text if we actually faded to (near) zero; a new message
    # arriving mid-fade calls _quiesce() which stops the animation first.
    self._label.setText(u'')
    self._effect.setOpacity(1.0)
