"""Shared test configuration for quicknxs test suite.

Warning policy
--------------
The test suite runs with ``filterwarnings = ["error", ...]`` (see pyproject.toml).
Any Python warning that is *not* explicitly suppressed will cause the test that
triggered it to fail.

How to handle a new warning:

1. If the warning is from *our* code (quicknxs/*): fix the root cause.
   Common patterns:
   - ResourceWarning: unclosed file → use ``with open(...) as f:`` instead of
     bare ``open(...).read()`` or ``f = open(...) / f.close()``.
   - DeprecationWarning from a third-party API call → update to the current API.

2. If the warning is from an *upstream library* and is not actionable from our
   code, add a targeted ``filterwarnings`` entry in pyproject.toml under
   ``[tool.pytest.ini_options]``.  Always include a comment explaining *why* the
   warning cannot be fixed here.  Use the most specific match pattern possible,
   e.g. ``"ignore::PendingDeprecationWarning:ipykernel"`` rather than a blanket
   ``"ignore::PendingDeprecationWarning"``.

Currently suppressed upstream warnings (see pyproject.toml for details):
- pytest.PytestCollectionWarning  (numpy.test attribute)
- PendingDeprecationWarning       (ipykernel do_history not async)
"""

import gc
import os

import pytest

# Ensure Qt uses offscreen rendering for headless test environments
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def _qt_cleanup():
    """Reset class-level mutable state and clean up Qt objects after each test.

    MainGUI uses class-level mutable attributes (ref_norm, reduction_list,
    etc.) that are shared across all instances.  Tests that call setNorm() or
    addRefList() mutate these dicts/lists at the class level, polluting
    subsequent tests.  This fixture resets them after each test.

    Additionally, processes pending Qt events and runs garbage collection to
    prevent accumulation of C++ widget objects.
    """
    yield
    # Reset class-level mutable attributes on MainGUI
    from quicknxs.main_gui import MainGUI
    MainGUI.ref_norm = {}
    MainGUI.ref_list_channels = []
    MainGUI.reduction_list = []
    MainGUI.cut_areas = {'fan': (0, 0)}
    MainGUI.open_plots = []
    MainGUI.channels = []
    MainGUI._gisansThread = None

    from qtpy.QtWidgets import QApplication
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    gc.collect()
    if app is not None:
        app.processEvents()
