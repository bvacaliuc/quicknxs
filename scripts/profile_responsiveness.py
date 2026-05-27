#!/usr/bin/env python
"""
Headless responsiveness profiler for the quicknxs GUI.

Measures the *wall-clock* time each heavy GUI handler spends on the main
(event-loop) thread, using a LOCAL test file so the numbers reflect the
systematic cost independent of any sshfs latency.

Usage:
    QT_QPA_PLATFORM=offscreen pixi run python scripts/profile_responsiveness.py
    QT_QPA_PLATFORM=offscreen pixi run python scripts/profile_responsiveness.py --cprofile
"""
import os
import sys
import time
import cProfile
import pstats
import io

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Keep matplotlib honest: use the same Agg-backed Qt canvas the GUI uses.

from qtpy.QtWidgets import QApplication, QMessageBox

_app = QApplication.instance() or QApplication([])

# Neutralize modal dialogs so a headless run never blocks on user input
# (the GUI pops a modal "Previous Crash" box and modal warning dialogs).
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.critical = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
QMessageBox.about = staticmethod(lambda *a, **k: None)

from quicknxs.main_gui import MainGUI  # noqa: E402 (must import after patching dialogs)

_test_dir = os.path.join(os.path.dirname(__file__), "..", "tests")
HISTO = os.path.abspath(os.path.join(_test_dir, "test1_histo.nxs"))
REFL = os.path.abspath(os.path.join(_test_dir, "test_refl_histo.nxs"))


def timeit(label, fn, *args, **kw):
    """Run fn once, return (label, elapsed_seconds)."""
    t0 = time.perf_counter()
    try:
        fn(*args, **kw)
    except Exception as e:  # noqa: BLE001 — diagnostic, report and continue
        dt = time.perf_counter() - t0
        print(f"  {label:<42s} {dt*1000:8.1f} ms   [EXC: {type(e).__name__}: {e}]")
        return label, dt
    dt = time.perf_counter() - t0
    print(f"  {label:<42s} {dt*1000:8.1f} ms")
    return label, dt


def switch_tab(gui, idx):
    gui.ui.plotTab.setCurrentIndex(idx)
    gui.plotActiveTab()


def main():
    do_cprofile = "--cprofile" in sys.argv
    print(f"Test file: {HISTO}")
    print(f"  exists={os.path.exists(HISTO)}  size={os.path.getsize(HISTO)/1e6:.1f} MB\n")

    gui = MainGUI([])
    _app.processEvents()

    print("=== Cold file open (load + overview plot, do_plot=True) ===")
    timeit("fileOpen(do_plot=True)  [cold]", gui.fileOpen, HISTO, do_plot=True)
    _app.processEvents()

    print("\n=== Warm file open (same file, cache hit) ===")
    timeit("fileOpen(do_plot=True)  [warm]", gui.fileOpen, HISTO, do_plot=True)
    _app.processEvents()

    print("\n=== Tab switches (plotActiveTab dispatch) ===")
    tabs = {0: "overview", 1: "xy", 2: "xtof", 3: "offspec", 5: "daslog"}
    for idx, name in tabs.items():
        timeit(f"tab {idx} ({name})", switch_tab, gui, idx)
        _app.processEvents()

    # Re-show overview so projections / refl exist for the region-change test
    switch_tab(gui, 0)
    _app.processEvents()

    print("\n=== Reflectivity recompute + replot ===")
    timeit("calc_refl()", gui.calc_refl)
    timeit("plot_refl()", gui.plot_refl)
    _app.processEvents()

    print("\n=== Region change (the spinbox-drag path) ===")
    # changeRegionValues needs proj_lines; plot_projections builds them.
    timeit("plot_projections()", gui.plot_projections)
    _app.processEvents()
    timeit("changeRegionValues()", gui.changeRegionValues)
    _app.processEvents()

    print("\n=== Add to reduction list + OffSpec preview ===")
    # Set the active dataset as its own normalization so addRefList accepts it,
    # then add it to the reduction list so plot_offspec has something to draw.
    gui.calc_refl()
    timeit("setNorm()", gui.setNorm, do_plot=False)
    _app.processEvents()
    gui.calc_refl()
    timeit("addRefList()", gui.addRefList, do_plot=False)
    _app.processEvents()
    gui.ref_list_channels = list(gui.active_data.keys())
    timeit("plot_offspec()  (re-reads file from disk)", gui.plot_offspec)
    _app.processEvents()
    print("  (second offspec call — measures pure re-read+recompute cost)")
    timeit("plot_offspec()  [again]", gui.plot_offspec)
    _app.processEvents()

    if do_cprofile:
        print("\n=== cProfile: 10x region change (calc_refl+plot_refl) ===")
        pr = cProfile.Profile()
        pr.enable()
        for _ in range(10):
            gui.plot_refl()
        pr.disable()
        s = io.StringIO()
        ps = pstats.Stats(pr, stream=s).sort_stats("cumulative")
        ps.print_stats(25)
        print(s.getvalue())

        print("\n=== cProfile: 1x plot_offspec ===")
        pr = cProfile.Profile()
        pr.enable()
        gui.plot_offspec()
        pr.disable()
        s = io.StringIO()
        ps = pstats.Stats(pr, stream=s).sort_stats("cumulative")
        ps.print_stats(30)
        print(s.getvalue())

    print("\nDone.")


if __name__ == "__main__":
    main()
