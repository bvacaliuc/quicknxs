#!/usr/bin/env python
"""General comparison of two off-specular reductions in scientific coordinate space.

Reads two ``OffSpecSmooth_*.dat`` files emitted by QuickNXS, regrids both
onto a common (k_iz - k_fz, Q_z) Cartesian grid, then writes
a multi-panel comparison figure and a set of scientific metrics.

The grid shape (n_x, n_y), extent, and orientation of each input file are
**auto-detected** from the data — there are no hardcoded dimensions. Inputs
may differ in resolution and extent; comparison is performed on the
intersection (or union, via ``--regrid union``) of the two regions.

Use cases:
  * bisect a regression between two QuickNXS versions (e.g. v4.3.0rc1 vs v4.17.0rc5)
  * verify that a headless reduction reproduces a GUI reduction
  * compare two smoothing / binning / slicing parameter sets against
    the same raw runs

Usage::

    pixi run python scripts/plot_offspec_compare.py \\
        --ref  /SNS/.../correctReduction/REF_M_..._OffSpecSmooth_Off_Off.dat \\
        --prop /SNS/.../session9/reduced/REF_M_..._OffSpecSmooth_Off_Off.dat \\
        --out  /tmp/offspec_compare.png

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
from matplotlib.colors import LogNorm, ListedColormap
from scipy.interpolate import RegularGridInterpolator, griddata


# ----- Header parsing --------------------------------------------------------

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
class OffSpecReduction:
    """In-memory representation of one OffSpecSmooth .dat file.

    Geometry attributes ``X``, ``Y``, ``I`` are 2D (ny, nx) for regular grids;
    when ``is_regular`` is False they are 1D columns and downstream code
    falls back to scipy griddata.
    """
    path: str
    meta: dict
    X: np.ndarray
    Y: np.ndarray
    I: np.ndarray            # noqa: E741
    x_axis: np.ndarray
    y_axis: np.ndarray
    is_regular: bool

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


# Default column triples (x, y, I) for each known file layout.
# - 3 columns: OffSpecSmooth_*.dat -> (k_iz-k_fz, Qz, I)
# - 7 columns: OffSpec_*.dat       -> (Qx, Qz, k_iz, k_fz, k_iz-k_fz, I, dI);
#                                     use columns (4, 1, 5) so plots stay in
#                                     (k_iz-k_fz, Qz, I) scientific space.
_DEFAULT_COLUMNS = {3: (0, 1, 2), 7: (4, 1, 5)}


def load_offspec_dat(path, x_col=None, y_col=None, I_col=None):  # noqa: E741
    """Load a QuickNXS off-spec .dat file and auto-detect its grid shape.

    Column selection: pass explicit ``x_col``/``y_col``/``I_col`` to override the
    auto-detected layout (3-col smoothed vs 7-col raw). When all three are
    ``None``, columns are inferred from the data width via ``_DEFAULT_COLUMNS``.
    """
    meta = _parse_header(path)
    data = np.loadtxt(path, comments='#')
    if data.ndim != 2 or data.shape[1] < 3:
        raise ValueError(f'{path}: expected ≥3-column data, got shape {data.shape}')

    ncols = data.shape[1]
    if x_col is None and y_col is None and I_col is None:
        if ncols not in _DEFAULT_COLUMNS:
            raise ValueError(
                f'{path}: {ncols}-column file has no default x/y/I mapping; '
                'pass --x-col, --y-col, --I-col explicitly')
        x_col, y_col, I_col = _DEFAULT_COLUMNS[ncols]
    if x_col is None or y_col is None or I_col is None:
        raise ValueError('must specify either all three of x/y/I_col or none')
    for c in (x_col, y_col, I_col):
        if c >= ncols or c < 0:
            raise ValueError(f'{path}: column index {c} out of range [0,{ncols})')
    meta['ncols'] = ncols
    meta['columns_used'] = (int(x_col), int(y_col), int(I_col))

    x = data[:, x_col]
    y = data[:, y_col]
    I = data[:, I_col]  # noqa: E741
    N = len(x)

    nx = len(np.unique(x))
    ny = len(np.unique(y))
    is_regular = (nx * ny == N)

    if is_regular:
        # Determine fast (inner-loop) axis from the first two rows.
        if x[0] != x[1]:                                      # x is the inner loop
            X = x.reshape(ny, nx)
            Y = y.reshape(ny, nx)
            II = I.reshape(ny, nx)
        elif y[0] != y[1]:                                    # y is the inner loop
            X = x.reshape(nx, ny).T
            Y = y.reshape(nx, ny).T
            II = I.reshape(nx, ny).T
        else:
            raise ValueError(f'{path}: cannot determine fast axis '
                             '(both x[0]==x[1] and y[0]==y[1])')
        x_axis = X[0, :].copy()
        y_axis = Y[:, 0].copy()
        # RegularGridInterpolator requires strictly increasing axes.
        if x_axis[0] > x_axis[-1]:
            X = X[:, ::-1]
            Y = Y[:, ::-1]
            II = II[:, ::-1]
            x_axis = x_axis[::-1].copy()
        if y_axis[0] > y_axis[-1]:
            X = X[::-1, :]
            Y = Y[::-1, :]
            II = II[::-1, :]
            y_axis = y_axis[::-1].copy()
    else:
        # Irregular: keep flat. regrid_pair will route to griddata.
        X = x.copy()
        Y = y.copy()
        II = I.copy()
        x_axis = np.unique(x)
        y_axis = np.unique(y)

    return OffSpecReduction(path=path, meta=meta, X=X, Y=Y, I=II,
                            x_axis=x_axis, y_axis=y_axis, is_regular=is_regular)


# ----- Regridding ------------------------------------------------------------

def _make_evaluator(red):
    """Return a callable f(x_query, y_query) -> (I_interp, valid_mask).

    The returned function handles NaN cleanly via the standard "weighted-divide"
    trick: NaN-source pixels are zeroed for the intensity interpolation, and a
    parallel interpolation of the validity mask is used to renormalise the
    intensity and to compute an output validity flag.
    """
    if not red.is_regular:
        pts = np.column_stack([red.X.ravel(), red.Y.ravel()])
        I = red.I.ravel()  # noqa: E741
        valid = ~np.isnan(I)
        I_clean = np.where(valid, I, 0.0)

        def _eval(xq, yq):
            qpts = np.column_stack([xq.ravel(), yq.ravel()])
            I_out = griddata(pts[valid], I_clean[valid], qpts,
                             method='linear', fill_value=np.nan)
            M_out = griddata(pts, valid.astype(float), qpts,
                             method='nearest', fill_value=0.0)
            return (I_out.reshape(xq.shape),
                    (M_out > 0.5).reshape(xq.shape))
        return _eval

    I = red.I  # noqa: E741
    valid = (~np.isnan(I)).astype(float)
    I_clean = np.where(valid > 0, I, 0.0)
    f_I = RegularGridInterpolator((red.y_axis, red.x_axis), I_clean,
                                  method='linear', bounds_error=False,
                                  fill_value=np.nan)
    f_M = RegularGridInterpolator((red.y_axis, red.x_axis), valid,
                                  method='linear', bounds_error=False,
                                  fill_value=0.0)

    def _eval(xq, yq):
        pts = np.stack([yq, xq], axis=-1)
        I_out = f_I(pts)
        M_out = f_M(pts)
        # Renormalize intensity to "undo" the NaN-as-zero dilution near edges.
        with np.errstate(invalid='ignore', divide='ignore'):
            I_out = np.where(M_out > 1e-6, I_out / np.maximum(M_out, 1e-6), np.nan)
        return I_out, (M_out > 0.5)
    return _eval


def regrid_pair(ref, prop, mode='intersect', max_size=1024):
    """Regrid both reductions onto a common (x, y) Cartesian evaluation grid.

    mode='intersect' (default) clips to the overlapping bounding box;
    mode='union' extrapolates with NaN outside each grid.
    """
    if mode == 'intersect':
        xmin = max(ref.x_axis.min(), prop.x_axis.min())
        xmax = min(ref.x_axis.max(), prop.x_axis.max())
        ymin = max(ref.y_axis.min(), prop.y_axis.min())
        ymax = min(ref.y_axis.max(), prop.y_axis.max())
    elif mode == 'union':
        xmin = min(ref.x_axis.min(), prop.x_axis.min())
        xmax = max(ref.x_axis.max(), prop.x_axis.max())
        ymin = min(ref.y_axis.min(), prop.y_axis.min())
        ymax = max(ref.y_axis.max(), prop.y_axis.max())
    else:
        raise ValueError(f'unknown regrid mode {mode!r}')

    if xmax <= xmin or ymax <= ymin:
        raise ValueError(f'empty regrid region: x=[{xmin},{xmax}], y=[{ymin},{ymax}]')

    def _common_n(a, b, lo, hi, cap):
        # Take the *finer* (smaller) step so we keep both grids' detail.
        sa = (a[-1] - a[0]) / max(1, len(a) - 1)
        sb = (b[-1] - b[0]) / max(1, len(b) - 1)
        step = min(abs(sa), abs(sb))
        n = int(round((hi - lo) / step)) + 1
        return max(2, min(cap, n))

    nx = _common_n(ref.x_axis, prop.x_axis, xmin, xmax, max_size)
    ny = _common_n(ref.y_axis, prop.y_axis, ymin, ymax, max_size)
    x_axis_c = np.linspace(xmin, xmax, nx)
    y_axis_c = np.linspace(ymin, ymax, ny)
    X_c, Y_c = np.meshgrid(x_axis_c, y_axis_c)

    f_ref = _make_evaluator(ref)
    f_prop = _make_evaluator(prop)
    I_ref_c, M_ref_c = f_ref(X_c, Y_c)
    I_prop_c, M_prop_c = f_prop(X_c, Y_c)

    return dict(X=X_c, Y=Y_c,
                I_ref=I_ref_c, I_prop=I_prop_c,
                mask_ref=M_ref_c, mask_prop=M_prop_c,
                x_axis=x_axis_c, y_axis=y_axis_c,
                xrange=(xmin, xmax), yrange=(ymin, ymax))


# ----- Metrics ---------------------------------------------------------------

def compute_metrics(grid, specular_halfwidth=2e-3, intensity_floor=1e-6):
    """Scientific-coordinate-space comparison metrics for a common-grid pair."""
    Ir = grid['I_ref']
    Ip = grid['I_prop']
    Mr = grid['mask_ref']
    Mp = grid['mask_prop']
    X = grid['X']

    valid_both = Mr & Mp & np.isfinite(Ir) & np.isfinite(Ip)
    pos_both = valid_both & (Ir > intensity_floor) & (Ip > intensity_floor)

    metrics = {
        'pixels_total': int(valid_both.size),
        'pixels_valid_ref': int((Mr & np.isfinite(Ir)).sum()),
        'pixels_valid_prop': int((Mp & np.isfinite(Ip)).sum()),
        'pixels_valid_both': int(valid_both.sum()),
        'pixels_positive_both': int(pos_both.sum()),
        'fraction_valid_both': float(valid_both.mean()),
    }

    if pos_both.sum() > 100:
        logr = np.log(Ir[pos_both])
        logp = np.log(Ip[pos_both])
        metrics['log_pearson'] = float(np.corrcoef(logr, logp)[0, 1])
        residual = logp - logr
        metrics['rms_log_residual'] = float(np.sqrt(np.mean(residual ** 2)))
        ratio = Ip[pos_both] / Ir[pos_both]
        metrics['median_ratio'] = float(np.median(ratio))
        metrics['ratio_q25'] = float(np.percentile(ratio, 25))
        metrics['ratio_q75'] = float(np.percentile(ratio, 75))
        metrics['total_intensity_ref']  = float(np.nansum(Ir[valid_both]))
        metrics['total_intensity_prop'] = float(np.nansum(Ip[valid_both]))
        metrics['integrated_ratio'] = (metrics['total_intensity_prop']
                                       / max(metrics['total_intensity_ref'], 1e-30))
    else:
        for k in ('log_pearson', 'rms_log_residual', 'median_ratio',
                  'ratio_q25', 'ratio_q75',
                  'total_intensity_ref', 'total_intensity_prop',
                  'integrated_ratio'):
            metrics[k] = None

    if valid_both.any():
        for tag, II in (('ref', np.where(valid_both, Ir, -np.inf)),
                        ('prop', np.where(valid_both, Ip, -np.inf))):
            j, i = np.unravel_index(int(np.argmax(II)), II.shape)
            metrics[f'peak_{tag}'] = dict(
                x=float(grid['x_axis'][i]), y=float(grid['y_axis'][j]),
                I=float({'ref': Ir, 'prop': Ip}[tag][j, i]))
        metrics['peak_dx'] = metrics['peak_prop']['x'] - metrics['peak_ref']['x']
        metrics['peak_dy'] = metrics['peak_prop']['y'] - metrics['peak_ref']['y']

    # Specular stripe (|ki_z - kf_z| < halfwidth) vs off-specular split.
    spec_mask = np.abs(X) < specular_halfwidth
    for name, m in [('specular', spec_mask), ('offspec', ~spec_mask)]:
        sel = m & pos_both
        metrics[f'{name}_pixels'] = int(sel.sum())
        if sel.sum() >= 100:
            r = Ip[sel] / Ir[sel]
            metrics[f'{name}_median_ratio'] = float(np.median(r))
            metrics[f'{name}_log_pearson'] = float(
                np.corrcoef(np.log(Ir[sel]), np.log(Ip[sel]))[0, 1])
            metrics[f'{name}_total_ref']  = float(Ir[sel].sum())
            metrics[f'{name}_total_prop'] = float(Ip[sel].sum())
        else:
            for k in (f'{name}_median_ratio', f'{name}_log_pearson',
                      f'{name}_total_ref', f'{name}_total_prop'):
                metrics[k] = None
    return metrics


# ----- Plotting --------------------------------------------------------------

def plot_comparison(ref, prop, grid, metrics, out_path,
                    vmin=1e-6, vmax=2.0, qz_cuts=None, kxz_cuts=None,
                    cut_axis='horizontal', ratio_clip=1.0):
    """Render the 5-panel comparison figure (Ref, Prop, log ratio, coverage, line cuts).

    ``cut_axis`` selects the bottom-panel line-cut direction:

      - ``'horizontal'`` (default): cut along the x axis at representative
        ``Qz`` values -- the plot shows I vs (k_iz - k_fz).  Source list:
        ``qz_cuts`` (auto-picked spread across the Qz extent if None).
      - ``'vertical'``: cut along the y axis at representative ``k_iz - k_fz``
        values -- the plot shows I vs Qz.  Source list: ``kxz_cuts``
        (auto-picked with ``k_iz - k_fz = 0`` always included if it lies in
        the common-grid x extent).

    Both modes plot ref as solid and prop as dashed, matched colors per cut.
    """
    fig = plt.figure(figsize=(18, 11))
    gs = fig.add_gridspec(2, 4, height_ratios=[3, 2], width_ratios=[1, 1, 1, 1])

    ax_ref   = fig.add_subplot(gs[0, 0])
    ax_prop  = fig.add_subplot(gs[0, 1])
    ax_ratio = fig.add_subplot(gs[0, 2])
    ax_mask  = fig.add_subplot(gs[0, 3])
    ax_cuts  = fig.add_subplot(gs[1, :])

    Ir = grid['I_ref']
    Ip = grid['I_prop']
    Mr = grid['mask_ref']
    Mp = grid['mask_prop']

    def _draw_intensity(ax, I, M, title):  # noqa: E741
        I_show = np.where(M & np.isfinite(I), np.maximum(I, vmin), np.nan)
        im = ax.pcolormesh(grid['x_axis'], grid['y_axis'], I_show,
                           norm=LogNorm(vmin=vmin, vmax=vmax),
                           cmap='turbo', shading='auto')
        ax.set_title(title, fontsize=10)
        ax.set_xlabel(r'$k_{i,z} - k_{f,z}\ [\mathrm{\AA}^{-1}]$')
        ax.set_ylabel(r'$Q_z\ [\mathrm{\AA}^{-1}]$')
        plt.colorbar(im, ax=ax, label='I [a.u.]')

    _draw_intensity(ax_ref, Ir, Mr, f'Ref: {ref.long_label}')
    _draw_intensity(ax_prop, Ip, Mp, f'Prop: {prop.long_label}')

    # Log-ratio panel
    valid_both = Mr & Mp & np.isfinite(Ir) & np.isfinite(Ip)
    pos_both = valid_both & (Ir > 1e-6) & (Ip > 1e-6)
    log_ratio = np.full_like(Ir, np.nan, dtype=float)
    log_ratio[pos_both] = np.log10(Ip[pos_both] / Ir[pos_both])
    im = ax_ratio.pcolormesh(grid['x_axis'], grid['y_axis'], log_ratio,
                             vmin=-ratio_clip, vmax=ratio_clip,
                             cmap='RdBu_r', shading='auto')
    ax_ratio.set_title(r'$\log_{10}$(prop / ref)')
    ax_ratio.set_xlabel(r'$k_{i,z} - k_{f,z}\ [\mathrm{\AA}^{-1}]$')
    ax_ratio.set_ylabel(r'$Q_z\ [\mathrm{\AA}^{-1}]$')
    plt.colorbar(im, ax=ax_ratio, label=r'$\log_{10}$ ratio')

    # Coverage map: 0=neither, 1=ref only, 2=prop only, 3=both
    cov = np.zeros(Ir.shape, dtype=int)
    cov[Mr & np.isfinite(Ir)] += 1
    cov[Mp & np.isfinite(Ip)] += 2
    cov_cmap = ListedColormap(['#202020', '#d62728', '#1f77b4', '#2ca02c'])
    im = ax_mask.pcolormesh(grid['x_axis'], grid['y_axis'], cov,
                            cmap=cov_cmap, vmin=-0.5, vmax=3.5, shading='auto')
    ax_mask.set_title('Coverage')
    ax_mask.set_xlabel(r'$k_{i,z} - k_{f,z}\ [\mathrm{\AA}^{-1}]$')
    ax_mask.set_ylabel(r'$Q_z\ [\mathrm{\AA}^{-1}]$')
    cb = plt.colorbar(im, ax=ax_mask, ticks=[0, 1, 2, 3])
    cb.set_ticklabels(['none', 'ref', 'prop', 'both'])

    # Line cuts.  Two modes:
    #
    # - 'horizontal': cut across constant-Qz rows of the regrided
    #   intensity, so the bottom plot is I vs (k_iz - k_fz) at several
    #   representative Qz values.  This is the historical default.
    # - 'vertical': cut down constant-(k_iz-k_fz) columns, so the bottom
    #   plot is I vs Qz at several representative k_iz-k_fz values --
    #   useful for asking "does the specular ridge (k_iz-k_fz=0) match?"
    #   without having to read it off the 2-D maps above.  Always
    #   includes the column closest to 0 if the common-grid x extent
    #   straddles 0.
    if cut_axis == 'horizontal':
        if qz_cuts is None:
            ymin, ymax = grid['yrange']
            qz_cuts = [ymin + 0.10 * (ymax - ymin),
                       ymin + 0.30 * (ymax - ymin),
                       ymin + 0.55 * (ymax - ymin),
                       ymin + 0.80 * (ymax - ymin)]
        for qz in qz_cuts:
            j = int(np.argmin(np.abs(grid['y_axis'] - qz)))
            qz_actual = grid['y_axis'][j]
            Ir_cut = np.where(Mr[j] & np.isfinite(Ir[j]), Ir[j], np.nan)
            Ip_cut = np.where(Mp[j] & np.isfinite(Ip[j]), Ip[j], np.nan)
            line, = ax_cuts.plot(grid['x_axis'], Ir_cut, '-', lw=1.5,
                                 label=f'ref  Qz={qz_actual:.3f}')
            ax_cuts.plot(grid['x_axis'], Ip_cut, '--', color=line.get_color(),
                         lw=1.2, label=f'prop Qz={qz_actual:.3f}')
        ax_cuts.set_xlabel(r'$k_{i,z} - k_{f,z}\ [\mathrm{\AA}^{-1}]$')
        ax_cuts.set_title(r'Line cuts at representative $Q_z$ '
                          r'(solid=ref, dashed=prop)')
    elif cut_axis == 'vertical':
        if kxz_cuts is None:
            xmin, xmax = grid['xrange']
            kxz_cuts = [xmin + 0.15 * (xmax - xmin),
                        xmin + 0.40 * (xmax - xmin),
                        xmin + 0.60 * (xmax - xmin),
                        xmin + 0.85 * (xmax - xmin)]
            # Always include the specular ridge (k_iz - k_fz = 0) if it
            # is inside the common-grid x extent.
            if xmin <= 0.0 <= xmax:
                kxz_cuts.append(0.0)
        for kxz in kxz_cuts:
            i = int(np.argmin(np.abs(grid['x_axis'] - kxz)))
            kxz_actual = grid['x_axis'][i]
            Ir_col = Ir[:, i]
            Ip_col = Ip[:, i]
            Ir_cut = np.where(Mr[:, i] & np.isfinite(Ir_col), Ir_col, np.nan)
            Ip_cut = np.where(Mp[:, i] & np.isfinite(Ip_col), Ip_col, np.nan)
            line, = ax_cuts.plot(grid['y_axis'], Ir_cut, '-', lw=1.5,
                                 label=f'ref  Δkz={kxz_actual:+.4f}')
            ax_cuts.plot(grid['y_axis'], Ip_cut, '--', color=line.get_color(),
                         lw=1.2, label=f'prop Δkz={kxz_actual:+.4f}')
        ax_cuts.set_xlabel(r'$Q_z\ [\mathrm{\AA}^{-1}]$')
        ax_cuts.set_title(r'Line cuts at representative $k_{i,z} - k_{f,z}$ '
                          r'(solid=ref, dashed=prop)')
    else:
        raise ValueError(f'unknown cut_axis {cut_axis!r}; '
                         "expected 'horizontal' or 'vertical'")
    ax_cuts.set_yscale('log')
    ax_cuts.set_ylabel('I (log)')
    ax_cuts.legend(fontsize=7, ncol=4, loc='upper right')
    ax_cuts.grid(True, alpha=0.3)

    fig.suptitle(os.path.basename(out_path), fontsize=11, y=0.995)

    def _fmt(v, fmt='.4g'):
        return 'n/a' if v is None else format(v, fmt)
    txt = '\n'.join([
        f"valid (both):       {metrics['pixels_valid_both']:>10,d} "
        f"({100*metrics['fraction_valid_both']:5.1f}%)",
        f"log-I Pearson:      {_fmt(metrics.get('log_pearson')):>10s}",
        f"median ratio:       {_fmt(metrics.get('median_ratio')):>10s}",
        f"RMS(log resid):     {_fmt(metrics.get('rms_log_residual')):>10s}",
        f"integrated ratio:   {_fmt(metrics.get('integrated_ratio')):>10s}",
        f"spec  median ratio: {_fmt(metrics.get('specular_median_ratio')):>10s}  "
        f"({metrics.get('specular_pixels'):,d} px)",
        f"offsp median ratio: {_fmt(metrics.get('offspec_median_ratio')):>10s}  "
        f"({metrics.get('offspec_pixels'):,d} px)",
        f"peak Δ(x,y):        ({_fmt(metrics.get('peak_dx'), '+.4f')}, "
        f"{_fmt(metrics.get('peak_dy'), '+.4f')})",
    ])
    fig.text(0.01, 0.005, txt, family='monospace', fontsize=8, va='bottom')

    plt.tight_layout(rect=(0, 0.07, 1, 0.97))
    plt.savefig(out_path, dpi=110)
    print(f'Wrote {out_path}')


# ----- CLI -------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ref', required=True,
                    help='Reference OffSpecSmooth .dat file')
    ap.add_argument('--prop', required=True,
                    help='Proposed OffSpecSmooth .dat file to compare against ref')
    ap.add_argument('--out', default='/tmp/offspec_compare.png',
                    help='Output PNG path')
    ap.add_argument('--json-out', default=None,
                    help='Optionally write metrics + metadata as JSON')
    ap.add_argument('--regrid', choices=('intersect', 'union'), default='intersect',
                    help='Common-grid extent (default: intersect)')
    ap.add_argument('--max-size', type=int, default=1024,
                    help='Per-axis cap on common-grid resolution (default 1024)')
    ap.add_argument('--vmin', type=float, default=1e-6,
                    help='Intensity color-scale floor (default 1e-6)')
    ap.add_argument('--vmax', type=float, default=2.0,
                    help='Intensity color-scale ceiling (default 2.0)')
    ap.add_argument('--ratio-clip', type=float, default=1.0,
                    help='Log-ratio panel symmetric clip (default 1.0 = ±decade)')
    ap.add_argument('--specular-halfwidth', type=float, default=2e-3,
                    help='|k_iz - k_fz| < this is the specular stripe (default 2e-3)')
    ap.add_argument('--cut-axis', choices=('horizontal', 'vertical'),
                    default='horizontal',
                    help='Direction of the bottom-panel line cuts: '
                         '"horizontal" (default) = I vs (k_iz-k_fz) at '
                         'representative Qz values; "vertical" = I vs Qz '
                         'at representative k_iz-k_fz values (always '
                         'includes k_iz-k_fz=0 if the grid straddles it).')
    ap.add_argument('--qz-cut', type=float, action='append', default=None,
                    help='Add a HORIZONTAL line-cut at this Qz value; '
                         'repeat for multiple.  Only used when '
                         '--cut-axis=horizontal.')
    ap.add_argument('--kxz-cut', type=float, action='append', default=None,
                    help='Add a VERTICAL line-cut at this k_iz - k_fz '
                         'value; repeat for multiple.  Only used when '
                         '--cut-axis=vertical.')
    ap.add_argument('--x-col', type=int, default=None,
                    help='Column index for x = k_iz - k_fz (auto if omitted: '
                         '3-col file -> 0, 7-col -> 4)')
    ap.add_argument('--y-col', type=int, default=None,
                    help='Column index for y = Q_z (auto if omitted: 3-col -> 1, '
                         '7-col -> 1)')
    ap.add_argument('--I-col', type=int, default=None,
                    help='Column index for intensity (auto if omitted: 3-col -> 2, '
                         '7-col -> 5)')
    args = ap.parse_args()

    def _describe(name, red):
        print(f'  meta:    {red.long_label}')
        print(f'  columns: {red.meta.get("ncols")}-col file, '
              f'using (x,y,I)={red.meta.get("columns_used")}')
        print(f'  grid:    nx={len(red.x_axis)}, ny={len(red.y_axis)}, '
              f'regular={red.is_regular}')
        print(f'  x range: [{red.x_axis.min():.5f}, {red.x_axis.max():.5f}]')
        print(f'  y range: [{red.y_axis.min():.5f}, {red.y_axis.max():.5f}]')

    print(f'Loading reference:  {args.ref}')
    ref = load_offspec_dat(args.ref,
                           x_col=args.x_col, y_col=args.y_col, I_col=args.I_col)
    _describe('ref', ref)

    print(f'Loading proposed:   {args.prop}')
    prop = load_offspec_dat(args.prop,
                            x_col=args.x_col, y_col=args.y_col, I_col=args.I_col)
    _describe('prop', prop)

    print(f'Regridding ({args.regrid}) to common scientific coordinate space...')
    grid = regrid_pair(ref, prop, mode=args.regrid, max_size=args.max_size)
    print(f'  common grid: nx={len(grid["x_axis"])}, ny={len(grid["y_axis"])}, '
          f'x=[{grid["xrange"][0]:.5f},{grid["xrange"][1]:.5f}], '
          f'y=[{grid["yrange"][0]:.5f},{grid["yrange"][1]:.5f}]')

    print('Computing metrics...')
    metrics = compute_metrics(grid, specular_halfwidth=args.specular_halfwidth)
    for k in ('pixels_valid_ref', 'pixels_valid_prop', 'pixels_valid_both',
              'pixels_positive_both', 'fraction_valid_both',
              'log_pearson', 'rms_log_residual', 'median_ratio',
              'ratio_q25', 'ratio_q75',
              'total_intensity_ref', 'total_intensity_prop', 'integrated_ratio',
              'specular_pixels', 'specular_median_ratio', 'specular_log_pearson',
              'offspec_pixels', 'offspec_median_ratio', 'offspec_log_pearson',
              'peak_dx', 'peak_dy'):
        v = metrics.get(k)
        if isinstance(v, float):
            print(f'  {k:24s} {v:.6g}')
        else:
            print(f'  {k:24s} {v}')

    print('Plotting...')
    plot_comparison(ref, prop, grid, metrics, args.out,
                    vmin=args.vmin, vmax=args.vmax,
                    ratio_clip=args.ratio_clip,
                    cut_axis=args.cut_axis,
                    qz_cuts=args.qz_cut, kxz_cuts=args.kxz_cut)

    if args.json_out:
        out = {'ref_meta': ref.meta,
               'prop_meta': prop.meta,
               'regrid_mode': args.regrid,
               'common_grid': {'nx': int(len(grid['x_axis'])),
                               'ny': int(len(grid['y_axis'])),
                               'xrange': [float(v) for v in grid['xrange']],
                               'yrange': [float(v) for v in grid['yrange']]},
               'metrics': metrics}
        with open(args.json_out, 'w') as fh:
            json.dump(out, fh, indent=2, default=str)
        print(f'Wrote metrics JSON to {args.json_out}')


if __name__ == '__main__':
    sys.exit(main())
