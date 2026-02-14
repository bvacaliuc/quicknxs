"""Shared test configuration for quicknxs test suite."""

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
