#!/usr/bin/env python
"""Re-reduce Off_Off with the off-spec band widened to 1.6 A (matching the v2
GUI reference) instead of v1's 1.4 A crop, to test whether the band-crop is the
~0.6x wing residual. pc-fix + BG-off + single-DB, bins=400."""
import sys

import quicknxs.qreduce as q
q.MANTID_OFFSPEC_HALF_BANDWIDTH = 1.6  # match v2 GUI load band (was 1.4)

sys.path.insert(0, 'scripts')
import reduce_offspec_headless as h  # noqa: E402

REF = ('/SNS/users/6ov/shared/REF_M/11486/session13/'
       'REF_M_44159+44160+44161_peak1_OffSpecSmooth_Off_Off-correct-db-id.dat')
OUT = '/tmp/v1_rematch/v1_band16_Off_Off.dat'

recipe = h.parse_recipe(REF)
db_map = h.assign_dbs(recipe, 'single')
print('band half-width now:', q.MANTID_OFFSPEC_HALF_BANDWIDTH)
pieces = h.reduce_recipe(recipe, 'Off_Off', 400, db_map, subtract_bg=False)
x, y, I = h.smooth_pieces(pieces, recipe.smooth_grid)
h.write_offspec_smooth_dat(OUT, x, y, I, recipe, 'Off_Off', db_map, 'single')
print('wrote', OUT)
