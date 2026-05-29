#!/usr/bin/env python
"""Measure per-polarization-channel proton charge via MRFilterCrossSections.

Hypothesis: v1 normalizes every channel by the FULL-run proton charge, while
v2 uses the PER-CHANNEL (split) charge. The off-spec deficit for a data run R,
channel C, normalized by DB D is then  frac_C(R) / frac_C(D), where
frac_C(X) = pc_C(X) / pc_total(X). For a polarizer-out direct beam frac~1, so
the deficit ~= the data run's channel time-fraction.
"""
from mantid.simpleapi import LoadEventNexus, MRFilterCrossSections, mtd, DeleteWorkspace

RUNS = {
    44159: '/SNS/REF_M/IPTS-34473/nexus/REF_M_44159.nxs.h5',
    44160: '/SNS/REF_M/IPTS-34473/nexus/REF_M_44160.nxs.h5',
    44161: '/SNS/REF_M/IPTS-34473/nexus/REF_M_44161.nxs.h5',
    44033: '/SNS/REF_M/IPTS-34473/nexus/REF_M_44033.nxs.h5',
    44034: '/SNS/REF_M/IPTS-34473/nexus/REF_M_44034.nxs.h5',
    44035: '/SNS/REF_M/IPTS-34473/nexus/REF_M_44035.nxs.h5',
}

results = {}
for rn, p in RUNS.items():
    raw = LoadEventNexus(Filename=p, OutputWorkspace='raw', LoadMonitors=False)
    pc_total = float(raw.getRun().getProtonCharge())
    grp = MRFilterCrossSections(InputWorkspace=raw, CrossSectionWorkspaces='xs')
    perchan = {}
    for i in range(grp.getNumberOfEntries()):
        w = grp.getItem(i)
        cid = w.getRun().getProperty('cross_section_id').value
        perchan[cid] = float(w.getRun().getProtonCharge())
    results[rn] = (pc_total, perchan)
    frac = {c: (v / pc_total if pc_total else float('nan')) for c, v in perchan.items()}
    fracs = '  '.join(f'{c}={v:.4f}' for c, v in frac.items())
    print(f"run {rn}: total_gd={pc_total:.4f} µAh | per-channel µAh: "
          + '  '.join(f'{c}={v:.3f}' for c, v in perchan.items())
          + f" | fractions: {fracs}")
    for w in ('raw', 'xs'):
        if mtd.doesExist(w):
            DeleteWorkspace(w)

print("\n-- predicted v1/v2 off-spec deficit = frac_C(DR) / frac_C(DB) --")
def frac(rn, c):
    tot, pc = results[rn]
    return pc.get(c, 0.0) / tot if tot else float('nan')
for dr, db in [(44159, 44033), (44160, 44033), (44161, 44033),
               (44159, 44034), (44160, 44034), (44161, 44035)]:
    for c in ('Off_Off', 'On_Off'):
        fdr, fdb = frac(dr, c), frac(db, c)
        pred = fdr / fdb if fdb else float('nan')
        print(f"  {c} DR{dr}/DB{db}: frac_dr={fdr:.4f} frac_db={fdb:.4f} -> v1/v2={pred:.4f}")
