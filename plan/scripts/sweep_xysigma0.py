#!/usr/bin/env python
"""Sweep the off-spec smoothing kernel reference width (xysigma0) on the SAME
reduced pieces (pc-fix + BG-off + single-DB, 1.4 band) and write a .dat per
value, to test whether the ~0.6x wing residual vs correctReduction is the
smoothing-kernel parameter. The headless smooth_pieces hardcodes
xysigma0 = Qzmax/3; the v2 _smooth_data default is 0.06."""
import sys
import numpy as np

import quicknxs.qreduce as q
q.MANTID_OFFSPEC_HALF_BANDWIDTH = 1.4  # keep the artifact-suppressing crop

sys.path.insert(0, 'scripts')
import reduce_offspec_headless as h  # noqa: E402
from quicknxs.qcalc import smooth_data  # noqa: E402

REF = ('/SNS/users/6ov/shared/REF_M/11486/session13/'
       'REF_M_44159+44160+44161_peak1_OffSpecSmooth_Off_Off-correct-db-id.dat')

recipe = h.parse_recipe(REF)
db_map = h.assign_dbs(recipe, 'single')
pieces = h.reduce_recipe(recipe, 'Off_Off', 400, db_map, subtract_bg=False, verbose=False)

data = np.hstack(pieces)
x = data[:, :, 4].flatten()
y = data[:, :, 1].flatten()
I = data[:, :, 5].flatten()  # noqa: E741
Qzmax = data[:, :, 2].max() * 2.0
g = recipe.smooth_grid
print('Qzmax/3 (headless default) = %.4f' % (Qzmax / 3.0))

for xys in (Qzmax / 3.0, 0.06, 0.10, 0.20):
    settings = {'grid': (g.nx, g.ny), 'sigma': (0.0005, 0.0005),
                'region': [g.x_min, g.x_max, g.y_min, g.y_max],
                'sigmas': 3, 'xy_column': 0}
    xo, yo, Io = smooth_data(settings, x, y, I, axis_sigma_scaling=2,
                             xysigma0=xys, sigmas=3, callback=None)
    out = '/tmp/v1_rematch/v1_xys%.3f_Off_Off.dat' % xys
    h.write_offspec_smooth_dat(out, xo, yo, Io, recipe, 'Off_Off', db_map, 'single')
    print('xysigma0=%.4f  Imax=%.4f  nonzero=%d -> %s'
          % (xys, np.nanmax(Io), int((Io != 0).sum()), out))
