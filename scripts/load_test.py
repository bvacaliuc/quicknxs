#!/usr/bin/env python
'''
Standalone CLI tool for verifying NXS file loading.

Reports instrument detection, dataset class, channel count, measurement type,
array shapes, key metadata, and PASS/FAIL per file.

Usage:
  python scripts/load_test.py --file /path/to/file.nxs
  python scripts/load_test.py --dir /path/to/data/ --pattern "*_histo.nxs"
  python scripts/load_test.py --file /path/to/file.nxs --refl
'''
import os
import sys
import argparse
import logging
from glob import glob

# Allow running from the scripts/ directory or project root
try:
  if os.path.abspath(__file__).endswith('scripts/load_test.py'):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
except NameError:
  pass

from quicknxs import qreduce
from quicknxs.config import instrument


def test_file(filepath, extract_refl=False):
  '''Load a single NXS file and report results. Returns True on success.'''
  basename = os.path.basename(filepath)

  # Skip broken symlinks
  if not os.path.isfile(filepath):
    print('  SKIP  %s  (broken symlink or missing)' % basename)
    return True  # not a failure

  try:
    is_event = filepath.endswith('event.nxs')
    kwargs = dict(use_caching=False)
    if is_event:
      kwargs['bins'] = 40

    obj = qreduce.NXSData(filepath, **kwargs)
    if obj is None:
      print('  FAIL  %s  NXSData returned None' % basename)
      return False

    ds = obj[0]
    ds_class = type(ds).__name__
    beamline = getattr(obj, '_beamline', '?')
    instr_name = 'REF_L' if beamline == '4B' else 'REF_M'

    info = (
      'instrument=%s  class=%s  channels=%d  type=%s'
      % (instr_name, ds_class, len(obj), obj.measurement_type)
    )

    # Array shapes
    shapes = []
    if hasattr(ds, 'data') and ds.data is not None:
      shapes.append('data=%s' % repr(ds.data.shape))
    if hasattr(ds, 'xydata') and ds.xydata is not None:
      shapes.append('xydata=%s' % repr(ds.xydata.shape))
    if hasattr(ds, 'xtofdata') and ds.xtofdata is not None:
      shapes.append('xtofdata=%s' % repr(ds.xtofdata.shape))
    shape_str = '  '.join(shapes)

    # Key metadata
    meta_parts = []
    for attr in ('number', 'lambda_center', 'sangle', 'dangle', 'proton_charge', 'total_counts'):
      val = getattr(ds, attr, None)
      if val is not None:
        if isinstance(val, float):
          meta_parts.append('%s=%.4g' % (attr, val))
        else:
          meta_parts.append('%s=%s' % (attr, val))
    meta_str = '  '.join(meta_parts)

    print('  PASS  %s' % basename)
    print('        %s' % info)
    if shape_str:
      print('        %s' % shape_str)
    if meta_str:
      print('        %s' % meta_str)

    if extract_refl:
      try:
        refl = qreduce.Reflectivity(ds, x_pos=ds.dpix, x_width=10, y_pos=128, y_width=50)
        q = refl.Q
        print('        Q range: %.4g .. %.4g (%d points)' % (q.min(), q.max(), len(q)))
      except Exception as e:
        print('        Reflectivity extraction failed: %s' % e)

    return True

  except Exception as e:
    print('  FAIL  %s  %s: %s' % (basename, type(e).__name__, e))
    return False


def main():
  parser = argparse.ArgumentParser(description='NXS file load verification tool')
  group = parser.add_mutually_exclusive_group(required=True)
  group.add_argument('--file', help='Single NXS file to test')
  group.add_argument('--dir', help='Directory of NXS files to scan')
  parser.add_argument('--pattern', default='*_histo.nxs',
                      help='Glob pattern for --dir mode (default: *_histo.nxs)')
  parser.add_argument('--refl', action='store_true',
                      help='Also extract Reflectivity and report Q range')
  parser.add_argument('--verbose', '-v', action='store_true',
                      help='Enable debug logging')
  args = parser.parse_args()

  if args.verbose:
    logging.basicConfig(level=logging.DEBUG)
  else:
    logging.basicConfig(level=logging.WARNING)

  if args.file:
    files = [args.file]
  else:
    pattern = os.path.join(args.dir, args.pattern)
    files = sorted(glob(pattern))
    print('Found %d files matching %s' % (len(files), pattern))

  passed = 0
  failed = 0
  skipped = 0
  for f in files:
    if not os.path.isfile(f):
      skipped += 1
      continue
    if test_file(f, extract_refl=args.refl):
      passed += 1
    else:
      failed += 1

  print('\n--- Results: %d passed, %d failed, %d skipped ---' % (passed, failed, skipped))
  sys.exit(1 if failed > 0 else 0)


if __name__ == '__main__':
  main()
