#!/usr/bin/env python
"""Headless off-specular reduction with explicit per-run direct-beam assignment.

Reads a "recipe" — direct-beam runs and reflectivity runs with their parameters
— from a reference QuickNXS ``OffSpecSmooth_*.dat`` file's header, then
reproduces the reduction headlessly using ``quicknxs.qreduce`` and writes the
result in the same .dat format. Designed for CI regression testing: any data
set with a declared-correct reduction can be re-reduced as new code lands.

The reduction's smoothing grid is inferred from the reference .dat's data body
(shape + bounding box) so the output is directly comparable via
``plot_offspec_compare.py``.

**Direct-beam assignment modes** (the key knob for the v4.3.0rc1 DB_ID
investigation):

* ``paired`` *(default)* — i-th data run is normalised by the i-th
  direct beam. Reproduces the per-run pairing the GUI's "Matched
  direct beam" widget displays. Requires ``len(data_runs) == len(db_runs)``.
* ``single`` — all data runs are normalised by the first direct beam
  (DB index 0). Reproduces the buggy v4.3.0rc1 behaviour where every
  data run's ``DB_ID`` is written as 1 and reload collapses all data
  runs onto the same DB.
* ``header`` — uses the ``DB_ID`` column actually written in the
  recipe file's ``[Data Runs]`` block (0-based or 1-based, auto-detected).

Usage::

    pixi run python scripts/reduce_offspec_headless.py \\
        --recipe /SNS/.../correctReduction/REF_M_..._OffSpecSmooth_Off_Off.dat \\
        --channel Off_Off --db-mode paired --bins 400 \\
        --out /tmp/headless_paired_Off_Off.dat

    pixi run python scripts/plot_offspec_compare.py \\
        --ref  /SNS/.../correctReduction/REF_M_..._OffSpecSmooth_Off_Off.dat \\
        --prop /tmp/headless_paired_Off_Off.dat --out /tmp/cmp.png
"""
import argparse
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np


# ---------- Recipe parsing -------------------------------------------------

@dataclass
class DirectBeamSpec:
    run_number: int
    x_pos: float
    x_width: float
    y_pos: float
    y_width: float
    bg_pos: float
    bg_width: float
    dpix: float
    tth: float
    file_path: str


@dataclass
class DataRunSpec:
    run_number: int
    scale: float
    P0: int
    PN: int
    x_pos: float
    x_width: float
    y_pos: float
    y_width: float
    bg_pos: float
    bg_width: float
    dpix: float
    tth: float
    db_id_header: int        # the DB_ID as written in the recipe file
    extract_fan: bool
    file_path: str


@dataclass
class SmoothGrid:
    nx: int
    ny: int
    x_min: float
    x_max: float
    y_min: float
    y_max: float


@dataclass
class Recipe:
    direct_beams: list
    data_runs: list
    sample_length: float
    smooth_grid: Optional[SmoothGrid]
    source_path: str
    source_version: tuple  # (app, version)


_DB_HEADER_RE = re.compile(r'^#\s*DB_ID\b')
_DATA_HEADER_RE = re.compile(r'^#\s*(scale|DB_ID)\b')


def _split_row(line):
    """Split a # data row, treating leading '#' + whitespace as a single sep."""
    body = line.lstrip('#').strip()
    return body.split()


def parse_recipe(path: str) -> Recipe:
    """Parse [Direct Beam Runs], [Data Runs], [Global Options] from a .dat header."""
    direct_beams: list = []
    data_runs: list = []
    sample_length = 10.0
    app, version = None, None
    section = None
    db_cols = None
    data_cols = None

    # First pass: header
    with open(path) as fh:
        for line in fh:
            if not line.startswith('#'):
                break
            body = line[1:].strip()
            m = re.match(r'Datafile created by\s+(\S+)\s+(\S+)', body)
            if m:
                app, version = m.group(1), m.group(2)
            if '[Direct Beam Runs]' in body:
                section = 'db'
                continue
            if '[Data Runs]' in body:
                section = 'data'
                continue
            if re.match(r'\[Peak \d+ Runs\]', body):
                section = 'peak'
                continue
            if '[Global Options]' in body:
                section = 'globals'
                continue
            if section == 'db':
                if 'DB_ID' in body and db_cols is None:
                    db_cols = body.split()
                    continue
                toks = _split_row(line)
                if not toks or db_cols is None or len(toks) < len(db_cols):
                    continue
                try:
                    row = dict(zip(db_cols, toks))
                    direct_beams.append(DirectBeamSpec(
                        run_number=int(row['number']),
                        x_pos=float(row['x_pos']),
                        x_width=float(row['x_width']),
                        y_pos=float(row['y_pos']),
                        y_width=float(row['y_width']),
                        bg_pos=float(row['bg_pos']),
                        bg_width=float(row['bg_width']),
                        dpix=float(row['dpix']),
                        tth=float(row['tth']),
                        file_path=row['File'],
                    ))
                except (KeyError, ValueError):
                    continue
            elif section == 'data':
                if ('DB_ID' in body or 'scale' in body) and data_cols is None:
                    data_cols = body.split()
                    continue
                toks = _split_row(line)
                if not toks or data_cols is None or len(toks) < len(data_cols):
                    continue
                try:
                    row = dict(zip(data_cols, toks))
                    fan_str = row.get('fan') or row.get('extract_fan') or 'False'
                    data_runs.append(DataRunSpec(
                        run_number=int(row['number']),
                        scale=float(row['scale']),
                        P0=int(row['P0']),
                        PN=int(row['PN']),
                        x_pos=float(row['x_pos']),
                        x_width=float(row['x_width']),
                        y_pos=float(row['y_pos']),
                        y_width=float(row['y_width']),
                        bg_pos=float(row['bg_pos']),
                        bg_width=float(row['bg_width']),
                        dpix=float(row['dpix']),
                        tth=float(row['tth']),
                        db_id_header=int(row['DB_ID']),
                        extract_fan=str(fan_str).lower() == 'true',
                        file_path=row['File'],
                    ))
                except (KeyError, ValueError):
                    continue
            elif section == 'globals':
                m = re.match(r'sample_length\s+([0-9.e+-]+)', body)
                if m:
                    sample_length = float(m.group(1))

    # Second pass: smoothed grid from data body
    smooth_grid = None
    try:
        data = np.loadtxt(path, comments='#')
        if data.ndim == 2 and data.shape[1] == 3:
            x = data[:, 0]
            y = data[:, 1]
            nx = len(np.unique(x))
            ny = len(np.unique(y))
            if nx * ny == len(data):
                smooth_grid = SmoothGrid(
                    nx=nx, ny=ny,
                    x_min=float(x.min()), x_max=float(x.max()),
                    y_min=float(y.min()), y_max=float(y.max()),
                )
    except Exception:
        pass

    return Recipe(
        direct_beams=direct_beams,
        data_runs=data_runs,
        sample_length=sample_length,
        smooth_grid=smooth_grid,
        source_path=path,
        source_version=(app, version),
    )


# ---------- Direct-beam assignment ------------------------------------------

def assign_dbs(recipe: Recipe, mode: str) -> dict:
    """Return mapping run_number(data) -> index_into_direct_beams."""
    n_db = len(recipe.direct_beams)
    n_dr = len(recipe.data_runs)
    if n_db == 0 or n_dr == 0:
        raise ValueError(f'recipe has {n_db} DBs and {n_dr} data runs — need ≥1 of each')

    mapping = {}
    if mode == 'paired':
        if n_dr != n_db:
            print(f'  WARN: db-mode=paired but {n_dr} data runs vs {n_db} DBs; '
                  f'pairing by min(i, n_db-1)', file=sys.stderr)
        for i, dr in enumerate(recipe.data_runs):
            mapping[dr.run_number] = min(i, n_db - 1)
    elif mode == 'single':
        for dr in recipe.data_runs:
            mapping[dr.run_number] = 0
    elif mode == 'header':
        # Detect 0- vs 1-based DB_ID by the first data run's value
        first = recipe.data_runs[0].db_id_header
        offset = 1 if first >= 1 else 0
        for dr in recipe.data_runs:
            idx = max(0, dr.db_id_header - offset)
            mapping[dr.run_number] = min(idx, n_db - 1)
    else:
        raise ValueError(f'unknown --db-mode {mode!r}')

    return mapping


# ---------- Reduction --------------------------------------------------------

def _direct_beam_channel(nxs):
    """Return the first available channel for an unpolarized DB run."""
    # quicknxs v1 names unpolarized DBs 'x'; if that fails, fall back to the
    # first key in the channel dict.
    try:
        return nxs['x']
    except KeyError:
        keys = list(getattr(nxs, '_xydata', {}).keys()) or list(getattr(nxs, 'measurement', {}).keys())
        if not keys:
            raise
        return nxs[keys[0]]


def reduce_recipe(recipe: Recipe, channel: str, bins: int, db_map: dict,
                  subtract_bg=True, verbose=True):
    """Run the headless reduction for `channel`, return list of per-run arrays.

    Parameters
    ----------
    subtract_bg : bool
        Whether to subtract the background-vs-TOF from the intensity. v1's
        ``OffSpecular`` always subtracts (no flag); when ``False``, we
        post-process to undo the subtraction in scientific-coordinate space
        by adding back the BG contribution scaled by the same factor:
        ``S_no_bg = S + BG * scale / norm.Rraw``.

    Returns
    -------
    pieces : list[np.ndarray]
        One (n_x_pix, n_tof_kept, 7) array per data run, columns
        (Qx, Qz, ki_z, kf_z, ki_z-kf_z, I, dI).
    """
    from quicknxs.qreduce import NXSData, Reflectivity, OffSpecular

    # Load all NXS files (DBs + data runs); cache by run number
    nxs = {}
    all_runs = ([db.run_number for db in recipe.direct_beams]
                + [dr.run_number for dr in recipe.data_runs])
    for run in all_runs:
        if run in nxs:
            continue
        path = next((d.file_path for d in recipe.direct_beams if d.run_number == run),
                    None) or next((d.file_path for d in recipe.data_runs if d.run_number == run),
                                  None)
        if verbose:
            print(f'  loading {os.path.basename(path)} (bins={bins})...')
        nxs[run] = NXSData(path, use_caching=False, bins=bins)

    # Build a Reflectivity (normalization) object per direct beam
    norms = []
    for db in recipe.direct_beams:
        xs = _direct_beam_channel(nxs[db.run_number])
        norm = Reflectivity(xs, normalization=None,
                            x_pos=db.x_pos, x_width=db.x_width,
                            y_pos=db.y_pos, y_width=db.y_width,
                            bg_pos=db.bg_pos, bg_width=db.bg_width,
                            dpix=db.dpix, tth=db.tth)
        if verbose:
            print(f'  DB {db.run_number} (index {len(norms)}): Rraw mean = {norm.Rraw.mean():.3e}')
        norms.append(norm)

    # Off-spec reduction per data run, with the assigned norm
    pieces = []
    for dr in recipe.data_runs:
        db_idx = db_map[dr.run_number]
        norm = norms[db_idx]
        xs = nxs[dr.run_number][channel]
        oS = OffSpecular(xs,
                         scale=dr.scale, P0=dr.P0, PN=dr.PN,
                         x_pos=dr.x_pos, x_width=dr.x_width,
                         y_pos=dr.y_pos, y_width=dr.y_width,
                         bg_pos=dr.bg_pos, bg_width=dr.bg_width,
                         extract_fan=dr.extract_fan,
                         dpix=dr.dpix, tth=dr.tth,
                         normalization=norm)

        # Optionally undo v1's mandatory background subtraction (no flag in v1).
        # After OffSpecular computes S = (I - BG) * scale / norm.Rraw, we can
        # recover the no-BG-subtract output by adding back BG * scale / norm.Rraw
        # at TOF bins where the normalization is valid.
        if not subtract_bg:
            scale = oS.options.get('scale', 1.0)
            bg_contrib = oS.BG[np.newaxis, :] * scale
            valid = norm.Rraw > 0
            bg_normalized = np.zeros_like(bg_contrib, dtype=float)
            bg_normalized[:, valid] = bg_contrib[:, valid] / norm.Rraw[np.newaxis, valid]
            oS.S = oS.S + bg_normalized

        # Apply the P0/PN truncation as the Exporter does
        n_tof = len(xs.tof)
        keep_lo = dr.PN
        keep_hi = n_tof - dr.P0
        rdata = np.asarray([
            oS.Qx[:, keep_lo:keep_hi], oS.Qz[:, keep_lo:keep_hi],
            oS.ki_z[:, keep_lo:keep_hi], oS.kf_z[:, keep_lo:keep_hi],
            oS.ki_z[:, keep_lo:keep_hi] - oS.kf_z[:, keep_lo:keep_hi],
            oS.S[:, keep_lo:keep_hi], oS.dS[:, keep_lo:keep_hi]]).transpose((1, 2, 0))
        pieces.append(rdata)
        if verbose:
            db_run = recipe.direct_beams[db_idx].run_number
            bg_state = 'BG-on' if subtract_bg else 'BG-off'
            print(f'  DR {dr.run_number} via DB[{db_idx}]={db_run} ({bg_state}): '
                  f'Qz=[{oS.Qz.min():.4f},{oS.Qz.max():.4f}], '
                  f'I=[{oS.S.min():.3e},{oS.S.max():.3e}]')
    return pieces


def smooth_pieces(pieces, grid: SmoothGrid, sigma_x=0.0005, sigma_y=0.0005):
    """Apply the OffSpecSmooth gaussian smoothing to a stack of per-run pieces."""
    from quicknxs.qcalc import smooth_data

    data = np.hstack(pieces)
    x = data[:, :, 4].flatten()   # ki_z - kf_z
    y = data[:, :, 1].flatten()   # Qz
    I = data[:, :, 5].flatten()   # noqa: E741
    Qzmax = data[:, :, 2].max() * 2.0
    settings = {
        'grid': (grid.nx, grid.ny),
        'sigma': (sigma_x, sigma_y),
        'region': [grid.x_min, grid.x_max, grid.y_min, grid.y_max],
        'sigmas': 3,
        'xy_column': 0,
    }
    axis_sigma_scaling = 2
    xysigma0 = Qzmax / 3.0
    xout, yout, Iout = smooth_data(settings, x, y, I,
                                   axis_sigma_scaling=axis_sigma_scaling,
                                   xysigma0=xysigma0,
                                   sigmas=settings['sigmas'])
    return xout, yout, Iout


# ---------- Output writing ---------------------------------------------------

def write_offspec_smooth_dat(path: str, x, y, I, recipe: Recipe,  # noqa: E741
                             channel: str, db_map: dict, db_mode: str):
    """Write the smoothed off-spec result in QuickNXS .dat format.

    Headers retain the recipe's [Direct Beam Runs] and [Data Runs] blocks
    (rewritten with the *actual* per-run DB indices used here, in 1-based
    indexing), so the file is self-describing.
    """
    pol_state = '+' if channel == 'Off_Off' else '-'
    with open(path, 'w') as fh:
        fh.write(f'# Datafile created by reduce_offspec_headless.py '
                 f'(quicknxsv1 fork, db-mode={db_mode})\n')
        fh.write(f'# Source recipe: {recipe.source_path}\n')
        fh.write(f'# Recipe app/version: {recipe.source_version}\n')
        fh.write(f'# Date: {time.strftime("%Y-%m-%d %H:%M:%S")}\n')
        fh.write('# Type: Specular\n')
        runs = ','.join(str(d.run_number) for d in recipe.data_runs)
        fh.write(f'# Input file indices: {runs}\n')
        fh.write(f'# Extracted states: {pol_state}\n')
        fh.write('#\n')

        # [Direct Beam Runs]
        fh.write('# [Direct Beam Runs]\n')
        fh.write('#    DB_ID        P0        PN     x_pos   x_width     '
                 'y_pos   y_width    bg_pos  bg_width      dpix       tth    '
                 'number      File\n')
        for i, db in enumerate(recipe.direct_beams, start=1):
            fh.write(f'#  {i:8d}  {0:8d}  {0:8d}  {db.x_pos:8g}  {db.x_width:8g}  '
                     f'{db.y_pos:8g}  {db.y_width:8g}  {db.bg_pos:8g}  '
                     f'{db.bg_width:8g}  {db.dpix:8g}  {db.tth:8g}  '
                     f'{db.run_number:8d}  {db.file_path}\n')
        fh.write('#\n')

        # [Data Runs] — note: this writer writes the CORRECT per-run DB_ID
        fh.write('# [Data Runs]\n')
        fh.write('#    scale  scale_err        P0        PN     x_pos   x_width     '
                 'y_pos   y_width    bg_pos  bg_width       fan      dpix       tth    '
                 'number     DB_ID      File\n')
        for dr in recipe.data_runs:
            db_idx_0based = db_map[dr.run_number]
            db_id_1based = db_idx_0based + 1
            fh.write(f'#  {dr.scale:8g}  {0.0:8g}  {dr.P0:8d}  {dr.PN:8d}  '
                     f'{dr.x_pos:8g}  {dr.x_width:8g}  {dr.y_pos:8g}  '
                     f'{dr.y_width:8g}  {dr.bg_pos:8g}  {dr.bg_width:8g}  '
                     f'{str(dr.extract_fan):>9s}  {dr.dpix:8g}  {dr.tth:8g}  '
                     f'{dr.run_number:8d}  {db_id_1based:8d}  {dr.file_path}\n')
        fh.write('#\n')

        # [Global Options]
        fh.write('# [Global Options]\n')
        fh.write('# name               value\n')
        fh.write(f'# sample_length      {recipe.sample_length}\n')
        fh.write('# lock_direct_beam_y False\n')
        fh.write('#\n')

        # [Data]
        fh.write('# [Data]\n')
        fh.write('# ki_z-kf_z [1/A]\tQz [1/A]\tI [a.u.]\n')
        for i in range(I.shape[0]):
            for j in range(I.shape[1]):
                fh.write(f'{x[i, j]:.6e}\t{y[i, j]:.6e}\t{I[i, j]:.6e}\n')


# ---------- CLI --------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--recipe', required=True,
                    help='Reference QuickNXS .dat file to use as the reduction recipe')
    ap.add_argument('--channel', default='Off_Off',
                    help='Polarization channel (default Off_Off)')
    ap.add_argument('--bins', type=int, default=400,
                    help='Number of TOF bins (default 400, matches v4.3.0rc1)')
    ap.add_argument('--db-mode', choices=('paired', 'single', 'header'), default='paired',
                    help='How to assign DBs to data runs (default: paired)')
    ap.add_argument('--out', required=True, help='Output .dat path')
    ap.add_argument('--sigma-x', type=float, default=0.0005,
                    help='Smoothing sigma in k_iz-k_fz (default 0.0005)')
    ap.add_argument('--sigma-y', type=float, default=0.0005,
                    help='Smoothing sigma in Q_z (default 0.0005)')
    ap.add_argument('--grid-nx', type=int, default=None,
                    help='Override nx of smoothing grid (default: from recipe). '
                         'Use a coarser grid (e.g. 200) for fast iteration; the '
                         'smoothing cost is O(nx*ny*N_points).')
    ap.add_argument('--grid-ny', type=int, default=None,
                    help='Override ny of smoothing grid (default: from recipe).')
    ap.add_argument('--no-smooth', action='store_true',
                    help='Skip smoothing; write raw OffSpec instead')
    ap.add_argument('--no-subtract-bg', action='store_true',
                    help='Skip the background-vs-TOF subtraction. v1 always '
                         'subtracts (no flag); this post-processes to undo it. '
                         'Matches v4.3.0rc1 "BG X off" / subtract_background=False.')
    args = ap.parse_args()

    print(f'Parsing recipe: {args.recipe}')
    recipe = parse_recipe(args.recipe)
    print(f'  app/version:   {recipe.source_version}')
    print(f'  direct beams:  {[d.run_number for d in recipe.direct_beams]}')
    print(f'  data runs:     {[d.run_number for d in recipe.data_runs]}')
    if recipe.smooth_grid is not None:
        g = recipe.smooth_grid
        print(f'  smooth grid:   nx={g.nx}, ny={g.ny}, '
              f'x=[{g.x_min:.4f},{g.x_max:.4f}], y=[{g.y_min:.4f},{g.y_max:.4f}]')
    else:
        print('  smooth grid:   (not detected — will use heuristic defaults if smoothing)')

    db_map = assign_dbs(recipe, args.db_mode)
    print(f'\nDB assignment ({args.db_mode}):')
    for dr in recipe.data_runs:
        db_idx = db_map[dr.run_number]
        db_run = recipe.direct_beams[db_idx].run_number
        header_db = dr.db_id_header
        print(f'  data {dr.run_number} -> DB[{db_idx}]={db_run}  (header DB_ID was {header_db})')

    print(f'\nReducing channel={args.channel}, bins={args.bins}, '
          f'subtract_bg={not args.no_subtract_bg}...')
    pieces = reduce_recipe(recipe, args.channel, args.bins, db_map,
                           subtract_bg=not args.no_subtract_bg)

    if args.no_smooth or recipe.smooth_grid is None:
        if recipe.smooth_grid is None and not args.no_smooth:
            print('  (no smooth grid in recipe; writing raw OffSpec instead)')
        np.savez(args.out + '.npz',
                 **{f'piece_{i}': p for i, p in enumerate(pieces)})
        print(f'Wrote raw pieces to {args.out}.npz')
        return

    # Allow overriding grid resolution (smoothing cost is O(nx*ny*N_points)).
    g = recipe.smooth_grid
    if args.grid_nx is not None or args.grid_ny is not None:
        g = SmoothGrid(
            nx=args.grid_nx if args.grid_nx is not None else g.nx,
            ny=args.grid_ny if args.grid_ny is not None else g.ny,
            x_min=g.x_min, x_max=g.x_max, y_min=g.y_min, y_max=g.y_max,
        )
        print(f'  grid overridden: nx={g.nx}, ny={g.ny}')

    print('\nSmoothing...')
    t0 = time.time()
    x, y, I = smooth_pieces(pieces, g,  # noqa: E741
                            sigma_x=args.sigma_x, sigma_y=args.sigma_y)
    print(f'  smoothing took {time.time() - t0:.1f}s')
    print(f'  smoothed grid: {x.shape}, I in [{np.nanmin(I):.3e}, {np.nanmax(I):.3e}], '
          f'nonzero {(I != 0).sum()}/{I.size} ({(I != 0).mean()*100:.1f}%)')

    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    write_offspec_smooth_dat(args.out, x, y, I, recipe, args.channel, db_map, args.db_mode)
    print(f'Wrote {args.out}')


if __name__ == '__main__':
    sys.exit(main())
