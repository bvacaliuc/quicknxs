#!/usr/bin/env python
"""
Headless reduction script for reproducing OOM crashes under strace.

Usage:
    pixi run python scripts/reduce_headless.py [state_file]

Loads the run_state.dat (or specified file), sets up the reduction with all
export options enabled (except GISANS, email, mantidplot, and plot which
require GUI interaction), and runs the full pipeline.

This script does NOT require a display or Qt event loop for the extraction
and export phases. It only needs Qt for HeaderParser's data loading.
"""

import os
import sys
import tempfile
import logging

logging.basicConfig(level=logging.DEBUG, format='[%(levelname)s] - %(asctime)s - %(filename)s:%(lineno)d:%(funcName)s %(message)s')

# Need QApplication for some Qt-dependent code paths
from qtpy import QtWidgets
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

from quicknxs.qio import HeaderParser
from quicknxs.gui_utils import Reducer
from quicknxs.config import paths

def main():
    # Determine state file
    if len(sys.argv) > 1:
        state_file = sys.argv[1]
    else:
        state_file = paths.STATE_FILE

    if not os.path.exists(state_file):
        print(f"State file not found: {state_file}")
        sys.exit(1)

    print(f"Loading state from: {state_file}")
    header = open(state_file, 'r').read()

    # Parse header (from_backup=True means parse_meta=False)
    parser = HeaderParser(header, parse_meta=False)
    parser.parse()

    if not parser.refls:
        print("No datasets found in header.")
        sys.exit(1)

    print(f"Loaded {len(parser.refls)} data runs, {len(parser.norms)} normalization runs")
    channels = list(parser.refls[0].options.get('normalization', parser.refls[0]).read_options.get('_channels', ['x']))

    # Determine channels from the first dataset's raw data
    from quicknxs.qreduce import NXSData
    first_refl = parser.refls[0]
    if type(first_refl.origin) is list:
        test_data = NXSData(first_refl.origin[0][0], **first_refl.read_options)
    else:
        test_data = NXSData(first_refl.origin[0], **first_refl.read_options)
    channels = list(test_data.keys())
    print(f"Channels: {channels}")

    # Set up output directory
    output_dir = tempfile.mkdtemp(prefix='quicknxs_reduce_')
    print(f"Output directory: {output_dir}")

    # Create Reducer with all options enabled
    reducer = Reducer(parent=None, channels=channels, refls=parser.refls)
    reducer._overwrite_all = True  # skip GUI file-exists dialog
    reducer.export_optios = {
        'foldername': output_dir,
        'naming': 'test_reduce.dat',
        'exportSpecular': True,
        'exportTrueSpecular': False,
        'exportOffSpecular': True,
        'exportOffSpecularCorr': True,
        'exportOffSpecularSmoothed': False,  # requires SmoothDialog (GUI)
        'exportGISANS': False,               # requires GISANSDialog (GUI)
        'export_SA': False,
        'emailSend': False,
        'multiAscii': True,
        'combinedAscii': True,
        'matlab': False,
        'mantidplot': False,
        'gnuplot': False,
        'numpy': True,
        'plot': False,                       # requires GUI
        'genx': False,
        'sampleSize': 10.,
    }

    # Report memory before reduction
    import resource
    mem_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    print(f"RSS before reduction: {mem_before / 1024:.1f} MB")

    print("Starting reduction with options:")
    for key, value in sorted(reducer.export_optios.items()):
        if key.startswith('export') and isinstance(value, bool):
            print(f"  {key}: {value}")

    try:
        reducer.execute()
        print("Reduction completed successfully!")
    except Exception as e:
        print(f"Reduction failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    mem_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    print(f"RSS after reduction: {mem_after / 1024:.1f} MB")
    print(f"Peak RSS increase: {(mem_after - mem_before) / 1024:.1f} MB")

    # List output files
    print(f"\nOutput files in {output_dir}:")
    for f in sorted(os.listdir(output_dir)):
        fpath = os.path.join(output_dir, f)
        size = os.path.getsize(fpath)
        print(f"  {f} ({size / 1024:.1f} KB)")

    print("\nDone.")

if __name__ == '__main__':
    main()
