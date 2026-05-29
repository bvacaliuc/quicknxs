#!/usr/bin/env python
"""Compare entry/proton_charge (what v1 sums, pC) vs Mantid gd_prtn_chrg
(what v2 normalizes by) per run, to test whether their ratio is constant
(cancels in the DB ratio) or varies per run (-> per-run deficit)."""
from mantid.simpleapi import LoadEventNexus
import numpy as np

RUNS = {
    44159: '/SNS/REF_M/IPTS-34473/nexus/REF_M_44159.nxs.h5',
    44160: '/SNS/REF_M/IPTS-34473/nexus/REF_M_44160.nxs.h5',
    44161: '/SNS/REF_M/IPTS-34473/nexus/REF_M_44161.nxs.h5',
    44033: '/SNS/REF_M/IPTS-34473/nexus/REF_M_44033.nxs.h5',
    44034: '/SNS/REF_M/IPTS-34473/nexus/REF_M_44034.nxs.h5',
    44035: '/SNS/REF_M/IPTS-34473/nexus/REF_M_44035.nxs.h5',
}
PC_PER_UAH = 3.6e9  # pC per micro-amp-hour

print(f"{'run':>6} {'gd_prtn(µAh)':>14} {'gd(pC)':>14} {'entry_pc(pC)':>16} "
      f"{'entry/gd':>10} {'log.sum(pC)':>16}")
rows = {}
for rn, p in RUNS.items():
    ws = LoadEventNexus(Filename=p, MetaDataOnly=True, LoadLogs=True,
                        OutputWorkspace=f'm{rn}')
    run = ws.getRun()
    gd_uah = float(run.getProtonCharge())            # Mantid: µAh
    gd_pc = gd_uah * PC_PER_UAH
    # entry/proton_charge total log
    pc_prop = run.getProperty('proton_charge')
    log_sum = float(np.asarray(pc_prop.value).sum()) if hasattr(pc_prop, 'value') else float('nan')
    # 'gd_prtn_chrg' raw property if present
    entry_pc = None
    for key in ('gd_prtn_chrg',):
        if run.hasProperty(key):
            entry_pc = float(run.getProperty(key).value)
    ratio = entry_pc / gd_uah if entry_pc else float('nan')
    rows[rn] = (gd_uah, gd_pc, entry_pc, log_sum)
    print(f"{rn:>6} {gd_uah:>14.4f} {gd_pc:>14.4e} {str(entry_pc):>16} "
          f"{ratio:>10.4f} {log_sum:>16.4e}")

print("\n-- DB-ratio cancellation check (data run normalized by its DB) --")
pairs = [(44159, 44033), (44160, 44034), (44161, 44035), (44160, 44033), (44161, 44033)]
for dr, db in pairs:
    # v1 uses entry log.sum (pC); v2 uses gd (µAh). Compare pc_db/pc_dr.
    v1_ratio = rows[db][3] / rows[dr][3]      # log.sum pC
    v2_ratio = rows[db][0] / rows[dr][0]      # gd µAh
    print(f"  DR{dr}/DB{db}: v1 pc_db/pc_dr={v1_ratio:.6f}  "
          f"v2 gd_db/gd_dr={v2_ratio:.6f}  v1/v2={v1_ratio/v2_ratio:.4f}")
