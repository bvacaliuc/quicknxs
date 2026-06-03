#!/usr/bin/env python
"""Compare two specular reflectivity reductions in scientific coordinate space.

Reads two ``Specular_*.dat`` files emitted by QuickNXS (5-column layout:
``Qz, R, dR, dQz, theta``), interpolates the "proposed" reduction onto the
"reference" reduction's Qz grid, then writes a multi-panel comparison
figure and a set of scientific metrics. Use cases mirror
``plot_offspec_compare.py``:

  * Bisect a regression between two QuickNXS versions (eg. v4.3.0rc1 vs v1.3.0dev49).
  * Verify that a different TOF binning has not changed the data.
  * Sanity-check a headless reduction against a GUI reduction.

The 1D reflectivity is naturally a list of points along Qz, but the data
is *stitched together* from multiple data runs at different incident
angles. Each run produces one segment with a constant ``theta`` (incident
angle αi). This tool detects segments by sorting points on theta and
colors them separately, so a per-segment regression (eg. only the
highest-angle run differs) is visible at a glance.

Usage::

    pixi run python scripts/plot_specular_compare.py \\
        --ref  /SNS/.../correctReduction/REF_M_..._Specular_Off_Off.dat \\
        --prop /SNS/.../prompt35/reduced-tof-400/REF_M_..._Specular_Off_Off.dat \\
        --out  /tmp/specular_compare.png

Metrics summary is printed to stdout; pass ``--json-out PATH`` to also
serialize the metrics (including extracted file metadata).
"""
import argparse
import json
import os
import re
import sys
from dataclasses import dataclass

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import LogLocator


# ----- Header parsing (mirrors plot_offspec_compare.py) ----------------------

_VERSION_RE = re.compile(r'Datafile created by\s+(\S+)\s+(\S+)')
_MANTID_RE  = re.compile(r'Datafile created using\s+(\S+)\s+(\S+)')
_DATE_RE    = re.compile(r'Date:\s*(.+)')
_RUNS_RE    = re.compile(r'Input file indices:\s*(.+)')
_TYPE_RE    = re.compile(r'Type:\s*(.+)')
_STATES_RE  = re.compile(r'Extracted states:\s*(.+)')


def _parse_header(path):
    """Extract version / run metadata from a QuickNXS .dat header."""
    meta = {'path': path, 'app': None, 'app_version': None,
            'mantid': None, 'mantid_version': None,
            'date': None, 'runs': None, 'type': None, 'states': None}
    with open(path, 'r') as fh:
        for line in fh:
            if not line.startswith('#'):
                break
            body = line[1:].strip()
            for rx, k1, k2 in [(_VERSION_RE, 'app', 'app_version'),
                               (_MANTID_RE, 'mantid', 'mantid_version')]:
                m = rx.search(body)
                if m:
                    meta[k1], meta[k2] = m.group(1), m.group(2)
            for rx, k in [(_DATE_RE, 'date'), (_RUNS_RE, 'runs'),
                          (_TYPE_RE, 'type'), (_STATES_RE, 'states')]:
                m = rx.search(body)
                if m:
                    meta[k] = m.group(1).strip()
    return meta


# ----- Reduction container ---------------------------------------------------

@dataclass
class SpecularReduction:
    """In-memory representation of one Specular .dat file."""
    path: str
    meta: dict
    Qz:    np.ndarray
    R:     np.ndarray
    dR:    np.ndarray
    dQz:   np.ndarray
    theta: np.ndarray
    # `segments` is a list of np.ndarray index arrays (one per unique
    # incident angle, ordered by ascending theta).  Each array is sorted
    # so Qz[idx] is ascending within the segment.
    segments: list

    @property
    def short_label(self):
        a = self.meta.get('app') or ''
        v = self.meta.get('app_version') or ''
        return f'{a} {v}'.strip() or os.path.basename(self.path)

    @property
    def long_label(self):
        bits = []
        if self.meta.get('app'):
            bits.append(f"{self.meta['app']} {self.meta.get('app_version', '?')}")
        if self.meta.get('mantid'):
            bits.append(f"{self.meta['mantid']} {self.meta.get('mantid_version', '?')}")
        if self.meta.get('date'):
            bits.append(self.meta['date'])
        return ' | '.join(bits) or os.path.basename(self.path)

    def iter_segments(self):
        """Yield (k, theta_value, Qz_arr, R_arr, dR_arr) per segment."""
        for k, idx in enumerate(self.segments):
            if len(idx) == 0:
                continue
            yield (k, float(self.theta[idx[0]]),
                   self.Qz[idx], self.R[idx], self.dR[idx])


def load_specular_dat(path):
    """Load a 5-column Specular .dat file: (Qz, R, dR, dQz, theta).

    Segments are detected by GROUPING rows by theta VALUE -- one segment
    per unique incident angle, regardless of row order.  v1 sorts the
    output by Qz and interleaves runs at the overlapping stitch
    boundaries; v4.3.0rc1 emits the runs sequentially.  Both produce
    the same {unique θ} set so this grouping converges to the natural
    "one segment per run" view.
    """
    meta = _parse_header(path)
    data = np.loadtxt(path, comments='#')
    if data.ndim != 2 or data.shape[1] < 5:
        raise ValueError(f'{path}: expected ≥5-column data, got shape {data.shape}')
    Qz, R, dR, dQz, theta = (data[:, i] for i in range(5))
    meta['ncols'] = data.shape[1]
    meta['n_points'] = int(len(Qz))

    # Group rows by theta (rounded to suppress float jitter between writers).
    # Order segments by ascending theta so seg0 is always the lowest angle.
    if len(theta) > 0:
        theta_keys = np.round(theta, 6)
        unique = sorted(set(theta_keys.tolist()))
        segments = []
        for u in unique:
            idx = np.where(theta_keys == u)[0]
            # Sort each segment by Qz so plots render as a clean curve, not
            # a zigzag at the stitching overlap.
            idx = idx[np.argsort(Qz[idx])]
            segments.append(idx)
    else:
        segments = []
    meta['n_segments'] = len(segments)

    return SpecularReduction(
        path=path, meta=meta,
        Qz=Qz, R=R, dR=dR, dQz=dQz, theta=theta,
        segments=segments,
    )


# ----- Comparison -----------------------------------------------------------

def _interp_log_R(Qz_src, R_src, Qz_tgt):
    """Interpolate R linearly in log(R) onto Qz_tgt (linear in Qz).

    Outside the source's [Qz_src.min(), Qz_src.max()] range -> NaN.
    Non-positive source R -> treated as NaN (no log).
    """
    Qz_src = np.asarray(Qz_src, dtype=float)
    R_src  = np.asarray(R_src,  dtype=float)
    Qz_tgt = np.asarray(Qz_tgt, dtype=float)
    order = np.argsort(Qz_src)
    Qz_s = Qz_src[order]
    R_s  = R_src[order]
    # Carry uncertainty about non-monotonic chunks (overlapping segments at
    # stitching boundaries) by collapsing duplicate Qz with the geometric mean.
    if len(Qz_s) >= 2:
        dup_mask = np.zeros(len(Qz_s), dtype=bool)
        i = 0
        Qz_c = []
        R_c  = []
        while i < len(Qz_s):
            j = i + 1
            while j < len(Qz_s) and Qz_s[j] == Qz_s[i]:
                j += 1
            Qz_c.append(Qz_s[i])
            sub = R_s[i:j]
            pos = sub[sub > 0]
            if len(pos):
                R_c.append(float(np.exp(np.mean(np.log(pos)))))
            else:
                R_c.append(0.0)
            i = j
        Qz_s = np.array(Qz_c)
        R_s  = np.array(R_c)
    pos = R_s > 0
    if pos.sum() < 2:
        return np.full(Qz_tgt.shape, np.nan)
    logR = np.log(R_s[pos])
    Qz_p = Qz_s[pos]
    in_range = (Qz_tgt >= Qz_p[0]) & (Qz_tgt <= Qz_p[-1])
    out = np.full(Qz_tgt.shape, np.nan)
    out[in_range] = np.exp(np.interp(Qz_tgt[in_range], Qz_p, logR))
    return out


def regrid_pair(ref, prop):
    """Sample prop's R onto ref's Qz grid via log-R linear interpolation.

    Returns a dict with the common-Qz arrays + a per-segment dictionary.
    """
    Qz_common = ref.Qz
    R_ref     = ref.R
    R_prop    = _interp_log_R(prop.Qz, prop.R, Qz_common)
    dR_ref    = ref.dR
    # Propagate prop dR via linear-in-Qz interpolation (not log) -- absolute
    # uncertainty in the same units as R; this is approximate but the right
    # qualitative shape for the comparison.
    dR_prop   = np.interp(Qz_common, np.sort(prop.Qz),
                          prop.dR[np.argsort(prop.Qz)],
                          left=np.nan, right=np.nan)
    overlap = (Qz_common >= max(ref.Qz.min(), prop.Qz.min()) - 1e-12) & \
              (Qz_common <= min(ref.Qz.max(), prop.Qz.max()) + 1e-12)
    return dict(Qz=Qz_common, R_ref=R_ref, R_prop=R_prop,
                dR_ref=dR_ref, dR_prop=dR_prop,
                overlap=overlap,
                ref=ref, prop=prop,
                xrange=(min(ref.Qz.min(), prop.Qz.min()),
                        max(ref.Qz.max(), prop.Qz.max())))


# ----- Metrics --------------------------------------------------------------

def compute_metrics(grid, intensity_floor=1e-8):
    """Per-overlap-region metrics on the common-Qz pair."""
    Qz = grid['Qz']
    Rr = grid['R_ref']
    Rp = grid['R_prop']
    valid_both = grid['overlap'] & np.isfinite(Rr) & np.isfinite(Rp)
    pos_both = valid_both & (Rr > intensity_floor) & (Rp > intensity_floor)

    m = {
        'points_total':         int(len(Qz)),
        'points_valid_ref':     int(np.isfinite(Rr).sum()),
        'points_valid_prop':    int(np.isfinite(Rp).sum()),
        'points_valid_both':    int(valid_both.sum()),
        'points_positive_both': int(pos_both.sum()),
        'fraction_valid_both':  float(valid_both.mean()),
    }

    if pos_both.sum() >= 50:
        logr = np.log(Rr[pos_both])
        logp = np.log(Rp[pos_both])
        m['log_pearson']      = float(np.corrcoef(logr, logp)[0, 1])
        residual              = logp - logr
        m['rms_log_residual'] = float(np.sqrt(np.mean(residual ** 2)))
        ratio = Rp[pos_both] / Rr[pos_both]
        m['median_ratio']     = float(np.median(ratio))
        m['ratio_q25']        = float(np.percentile(ratio, 25))
        m['ratio_q75']        = float(np.percentile(ratio, 75))
        # trapezoidal integral of R(Qz) over the common Qz overlap, on the
        # log-spaced grid implicit in the data.  Use only points where both
        # are positive so the integral makes sense.
        Qz_sel = Qz[pos_both]
        order  = np.argsort(Qz_sel)
        # numpy >=2 renames np.trapz to np.trapezoid; prefer the new name
        # and fall back so this script runs on older numpy as well.
        _trapz = getattr(np, 'trapezoid', getattr(np, 'trapz', None))
        m['integrated_R_ref']  = float(_trapz(Rr[pos_both][order], Qz_sel[order]))
        m['integrated_R_prop'] = float(_trapz(Rp[pos_both][order], Qz_sel[order]))
        m['integrated_ratio']  = (m['integrated_R_prop']
                                   / max(m['integrated_R_ref'], 1e-30))
    else:
        for k in ('log_pearson', 'rms_log_residual', 'median_ratio',
                  'ratio_q25', 'ratio_q75',
                  'integrated_R_ref', 'integrated_R_prop', 'integrated_ratio'):
            m[k] = None

    # Critical edge / plateau: where R is at total reflection (within 5% of 1.0).
    # The number of points and the median R in that region tell you whether
    # both reductions land the same plateau.
    plateau = valid_both & (Rr > 0.9) & (Rr < 1.10)
    m['plateau_pixels'] = int(plateau.sum())
    if plateau.sum() >= 10:
        m['plateau_median_ref']  = float(np.median(Rr[plateau]))
        m['plateau_median_prop'] = float(np.median(Rp[plateau]))
    else:
        m['plateau_median_ref'] = m['plateau_median_prop'] = None

    # Per-segment metrics on the REF segmentation: group the common-Qz indices
    # by which ref segment they fall into.  This shows whether a particular
    # angle's run is the outlier.  `ref.segments` is a list of index arrays
    # into the (un-sorted) ref file; reuse them to mask the common-Qz grid.
    ref = grid['ref']
    seg_metrics = []
    for k, idx in enumerate(ref.segments):
        seg_mask = np.zeros_like(valid_both)
        seg_mask[idx] = True
        sub = seg_mask & pos_both
        n = int(sub.sum())
        theta_val = float(ref.theta[idx[0]]) if len(idx) else None
        entry = dict(
            segment=k,
            n_positive=n,
            theta_rad=theta_val,
            Qz_min=float(ref.Qz[idx].min()) if len(idx) else None,
            Qz_max=float(ref.Qz[idx].max()) if len(idx) else None,
        )
        if n >= 10:
            ratio = Rp[sub] / Rr[sub]
            entry['median_ratio'] = float(np.median(ratio))
            entry['log_pearson']  = float(np.corrcoef(np.log(Rr[sub]),
                                                       np.log(Rp[sub]))[0, 1])
        else:
            entry['median_ratio'] = None
            entry['log_pearson']  = None
        seg_metrics.append(entry)
    m['segments_ref'] = seg_metrics
    return m


# ----- Plotting -------------------------------------------------------------

_SEG_COLORS = ['#1f77b4', '#d62728', '#2ca02c', '#9467bd', '#ff7f0e', '#17becf']


def plot_comparison(ref, prop, grid, metrics, out_path,
                    ymin=1e-6, ymax=2.0, ratio_clip=1.0,
                    plot_segments=True):
    """Render the 5-panel comparison figure for two 1-D specular reductions.

    Layout mirrors plot_offspec_compare.py: 4 panels on the top row
    (Ref, Prop, log-ratio vs Qz, relative-error vs Qz) and one wide
    panel on the bottom row showing both curves overlaid by segment.
    """
    fig = plt.figure(figsize=(18, 11))
    gs = fig.add_gridspec(2, 4, height_ratios=[3, 2], width_ratios=[1, 1, 1, 1])
    ax_ref   = fig.add_subplot(gs[0, 0])
    ax_prop  = fig.add_subplot(gs[0, 1])
    ax_ratio = fig.add_subplot(gs[0, 2])
    ax_err   = fig.add_subplot(gs[0, 3])
    ax_over  = fig.add_subplot(gs[1, :])

    def _draw_R(ax, red, title):
        if plot_segments:
            seg_iter = list(red.iter_segments())
        else:
            # one un-segmented "segment" covering all rows
            seg_iter = [(0, float('nan'), red.Qz, red.R, red.dR)]
        for k, theta_v, Qz_seg, R_seg, dR_seg in seg_iter:
            color = _SEG_COLORS[k % len(_SEG_COLORS)]
            pos = R_seg > 0
            if not pos.any():
                continue
            label = (f'seg{k} θ={theta_v:.4f} ({pos.sum()} pts)'
                     if plot_segments else None)
            ax.errorbar(Qz_seg[pos], R_seg[pos], yerr=dR_seg[pos],
                        fmt='.', ms=2.5, elinewidth=0.5, capsize=0,
                        color=color, alpha=0.85, label=label)
        ax.set_xscale('log')
        ax.set_yscale('log')
        ax.set_xlabel(r'$Q_z\ [\mathrm{\AA}^{-1}]$')
        ax.set_ylabel(r'$R\ [\mathrm{a.u.}]$')
        ax.set_title(title, fontsize=10)
        ax.set_ylim(ymin, ymax)
        ax.grid(True, which='major', alpha=0.4)
        ax.grid(True, which='minor', alpha=0.15)
        if plot_segments:
            ax.legend(fontsize=7, loc='lower left')

    _draw_R(ax_ref,  ref,  f'Ref: {ref.long_label}')
    _draw_R(ax_prop, prop, f'Prop: {prop.long_label}')

    # log10(prop/ref) vs Qz on the common grid (interpolated prop).
    Qz = grid['Qz']
    Rr = grid['R_ref']
    Rp = grid['R_prop']
    valid_both = grid['overlap'] & np.isfinite(Rr) & np.isfinite(Rp)
    pos_both   = valid_both & (Rr > 0) & (Rp > 0)
    logratio = np.full_like(Rr, np.nan)
    logratio[pos_both] = np.log10(Rp[pos_both] / Rr[pos_both])
    ax_ratio.axhline(0.0, color='k', lw=0.8, alpha=0.6)
    ax_ratio.plot(Qz[pos_both], logratio[pos_both],
                  '.', ms=2.5, alpha=0.7, color='#404040')
    ax_ratio.set_xscale('log')
    ax_ratio.set_ylim(-ratio_clip, ratio_clip)
    ax_ratio.set_xlabel(r'$Q_z\ [\mathrm{\AA}^{-1}]$')
    ax_ratio.set_ylabel(r'$\log_{10}\!\left(R_\mathrm{prop}/R_\mathrm{ref}\right)$')
    ax_ratio.set_title(r'$\log_{10}$(prop / ref) vs $Q_z$ (common grid)')
    ax_ratio.grid(True, alpha=0.4)

    # Relative error vs Qz: dR/R for each side.
    dRr = grid['dR_ref']
    dRp = grid['dR_prop']
    rel_err_ref  = np.where(Rr > 0, dRr / Rr, np.nan)
    rel_err_prop = np.where(Rp > 0, dRp / Rp, np.nan)
    ax_err.plot(Qz[pos_both], rel_err_ref[pos_both],  '.', ms=2.5, alpha=0.7,
                color='#1f77b4', label='ref')
    ax_err.plot(Qz[pos_both], rel_err_prop[pos_both], '.', ms=2.5, alpha=0.7,
                color='#d62728', label='prop')
    ax_err.set_xscale('log')
    ax_err.set_yscale('log')
    ax_err.set_xlabel(r'$Q_z\ [\mathrm{\AA}^{-1}]$')
    ax_err.set_ylabel(r'$\sigma_R / R$')
    ax_err.set_title('Relative error vs $Q_z$')
    ax_err.legend(fontsize=8, loc='upper left')
    ax_err.grid(True, which='major', alpha=0.4)
    ax_err.grid(True, which='minor', alpha=0.15)

    # Bottom overlay: ref (solid filled markers) + prop (open dashed-line markers)
    # by segment.  This is the canonical "both curves on one plot" view.
    def _overlay_one(red, *, marker, fillstyle, linestyle, alpha):
        for k, _theta_v, Qz_seg, R_seg, _dR_seg in red.iter_segments():
            color = _SEG_COLORS[k % len(_SEG_COLORS)]
            pos = R_seg > 0
            if not pos.any():
                continue
            ax_over.plot(Qz_seg[pos], R_seg[pos],
                         marker=marker, linestyle=linestyle, lw=0.8, ms=3.5,
                         fillstyle=fillstyle, color=color, alpha=alpha)
    _overlay_one(ref,  marker='o', fillstyle='full', linestyle='-',  alpha=0.85)
    _overlay_one(prop, marker='x', fillstyle='none', linestyle='--', alpha=0.85)
    ax_over.set_xscale('log')
    ax_over.set_yscale('log')
    ax_over.set_ylim(ymin, ymax)
    ax_over.set_xlabel(r'$Q_z\ [\mathrm{\AA}^{-1}]$')
    ax_over.set_ylabel(r'$R\ [\mathrm{a.u.}]$')
    ax_over.set_title('R(Q) overlay (ref = ● solid, prop = ✕ dashed); color = segment')
    ax_over.grid(True, which='major', alpha=0.4)
    ax_over.grid(True, which='minor', alpha=0.15)

    fig.suptitle(os.path.basename(out_path), fontsize=11, y=0.995)

    def _fmt(v, fmt='.4g'):
        return 'n/a' if v is None else format(v, fmt)
    lines = [
        f"points (both):       {metrics['points_valid_both']:>10,d} "
        f"({100*metrics['fraction_valid_both']:5.1f}% of ref grid)",
        f"log-R Pearson:       {_fmt(metrics.get('log_pearson')):>10s}",
        f"median ratio:        {_fmt(metrics.get('median_ratio')):>10s}",
        f"ratio IQR:           [{_fmt(metrics.get('ratio_q25'))}, "
        f"{_fmt(metrics.get('ratio_q75'))}]",
        f"RMS(log resid):      {_fmt(metrics.get('rms_log_residual')):>10s}",
        f"integrated R ref:    {_fmt(metrics.get('integrated_R_ref')):>10s}",
        f"integrated R prop:   {_fmt(metrics.get('integrated_R_prop')):>10s}",
        f"integrated ratio:    {_fmt(metrics.get('integrated_ratio')):>10s}",
        f"plateau px:          {metrics.get('plateau_pixels'):>10,d}  "
        f"med ref={_fmt(metrics.get('plateau_median_ref'))}  "
        f"med prop={_fmt(metrics.get('plateau_median_prop'))}",
    ]
    for seg in metrics.get('segments_ref', []):
        lines.append(
            f"seg{seg['segment']} θ={_fmt(seg.get('theta_rad'))}  "
            f"n={seg['n_positive']:5d}  "
            f"med={_fmt(seg.get('median_ratio'))}  "
            f"logP={_fmt(seg.get('log_pearson'))}")
    fig.text(0.01, 0.005, '\n'.join(lines),
             family='monospace', fontsize=8, va='bottom')

    plt.tight_layout(rect=(0, 0.10, 1, 0.97))
    plt.savefig(out_path, dpi=110)
    print(f'Wrote {out_path}')


# ----- CLI ------------------------------------------------------------------

def _describe(red):
    print(f'  meta:    {red.long_label}')
    print(f'  points:  {red.meta.get("n_points")}, '
          f'segments: {red.meta.get("n_segments")}')
    print(f'  Qz:      [{red.Qz.min():.5f}, {red.Qz.max():.5f}] '
          f'(span {red.Qz.max()-red.Qz.min():.4f})')
    for k, theta_v, Qz_seg, _R_seg, _dR_seg in red.iter_segments():
        print(f'    seg{k}  θ={theta_v:.5f}  '
              f'Qz=[{Qz_seg.min():.5f}, {Qz_seg.max():.5f}]  '
              f'n={len(Qz_seg)}')


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ref',  required=True,
                    help='Reference Specular .dat file (5 columns: Qz R dR dQz theta)')
    ap.add_argument('--prop', required=True,
                    help='Proposed Specular .dat file to compare against ref')
    ap.add_argument('--out',  default='/tmp/specular_compare.png',
                    help='Output PNG path')
    ap.add_argument('--json-out', default=None,
                    help='Optionally write metrics + metadata as JSON')
    ap.add_argument('--ymin', type=float, default=1e-6,
                    help='R color/y-axis floor (default 1e-6)')
    ap.add_argument('--ymax', type=float, default=2.0,
                    help='R color/y-axis ceiling (default 2.0)')
    ap.add_argument('--ratio-clip', type=float, default=1.0,
                    help='log10(ratio) panel symmetric clip (default 1.0 = ±decade)')
    ap.add_argument('--no-segments', dest='plot_segments', action='store_false',
                    help='Plot each side as a single color, not segmented by theta')
    args = ap.parse_args()

    print(f'Loading reference:  {args.ref}')
    ref  = load_specular_dat(args.ref)
    _describe(ref)
    print(f'Loading proposed:   {args.prop}')
    prop = load_specular_dat(args.prop)
    _describe(prop)

    print('Regridding (log-R linear-in-Qz) prop -> ref Qz grid...')
    grid = regrid_pair(ref, prop)
    print(f'  ref Qz grid: n={len(grid["Qz"])}  '
          f'overlap n={int(grid["overlap"].sum())}')

    print('Computing metrics...')
    metrics = compute_metrics(grid)
    for k, v in metrics.items():
        if k == 'segments_ref':
            continue
        if isinstance(v, float):
            print(f'  {k:25s} {v:.6g}')
        else:
            print(f'  {k:25s} {v}')
    for seg in metrics['segments_ref']:
        print(f'  seg{seg["segment"]}'
              f' theta={seg["theta_rad"]} '
              f'n={seg["n_positive"]:5d} '
              f'med={seg["median_ratio"]} '
              f'logP={seg["log_pearson"]}')

    print('Plotting...')
    plot_comparison(ref, prop, grid, metrics, args.out,
                    ymin=args.ymin, ymax=args.ymax,
                    ratio_clip=args.ratio_clip,
                    plot_segments=args.plot_segments)

    if args.json_out:
        payload = dict(metrics=metrics,
                       ref=ref.meta,
                       prop=prop.meta)
        with open(args.json_out, 'w') as fh:
            json.dump(payload, fh, indent=2, default=float)
        print(f'Wrote {args.json_out}')


if __name__ == '__main__':
    main()
