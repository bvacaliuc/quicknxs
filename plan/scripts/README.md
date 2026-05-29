# plan/scripts — diagnostic scripts for the off-spec deficit / DB_ID work

These are the one-off diagnostic scripts cited in `plan/v1-vs-mantid-deficit-rootcause.md`
and `plan/db-id-bug-and-interop.md`. They are committed here (rather than left in `/tmp`)
so the findings are reproducible on any machine — a documented method must live in the
repo, never be referenced out-of-tree.

They are *diagnostics*, not production tools (the production headless tools are
`scripts/reduce_offspec_headless.py` and `scripts/plot_offspec_compare.py`). Each writes
its scratch intermediates to `/tmp/*.npz` (fine — undocumented scratch); only the scripts
themselves are version-controlled.

## Two environments

| env | python | PYTHONPATH | has Mantid? |
|---|---|---|---|
| **v1** | `quicknxsv1/.pixi/envs/default/bin/python` | `quicknxsv1` (repo root) | no |
| **v2 / Mantid** | `quicknxsv2/.pixi/envs/default/bin/python` | `quicknxsv2/src` | yes (`mantid.simpleapi`) |

Run from the relevant repo root, e.g.:
```bash
cd quicknxsv1 && PYTHONPATH=$(pwd) .pixi/envs/default/bin/python plan/scripts/v1_load_probe.py
cd quicknxsv2 && PYTHONPATH=$(pwd)/src .pixi/envs/default/bin/python ../quicknxsv1/plan/scripts/v2_load_probe.py
```
Data paths are hard-coded to REF_M 11486 (IPTS-34473) under the `/SNS` mounts.

## Scripts

| script | env | purpose | dep |
|---|---|---|---|
| `pc_probe.py` | v1 (h5py) | `entry/proton_charge` vs `DASlogs/proton_charge/value.sum()` per run (ruled out a pc-unit bug) | — |
| `v1_load_probe.py` | v1 | load 44159 via `NXSData`, dump per-channel counts + I(tof) → `/tmp/v1_44159.npz` | — |
| `v2_load_probe.py` | v2 | load 44159 via `MRFilterCrossSections` on v1's tof edges; shows histograms are byte-identical | needs `/tmp/v1_44159.npz` |
| `pc_ratio_probe.py` | v2 | `entry/proton_charge` (pC) vs Mantid `gd_prtn_chrg` (µAh) ratio per run (constant → cancels) | — |
| `pc_split_probe.py` | v2 | per-channel proton charge via `MRFilterCrossSections` (the per-run spin-state fractions) | — |
| `verify_pc_split.py` | v1 (h5py) | reproduce Mantid's per-channel charge split from logs (validates the fix logic) | — |
| `v1_offspec_S.py` | v1 | raw off-spec S, 44159/DB44033/BG-off → `/tmp/v1_S.npz` | — |
| `v2_offspec_S.py` | v2 | raw off-spec S, 44159/DB44033/BG-off → `/tmp/v2_S.npz` (the 1.07 ratio check) | needs `/tmp/v1_44159.npz` |
| `v1_offspec_allruns.py` | v1 | per-run raw-S total (44159/60/61, DB44033, BG-off) | — |
| `v2_offspec_allruns.py` | v2 | per-run raw-S total (v2 side) — the table that localized the residual to 44161 | needs `/tmp/v1_44159.npz` |
| `reduce_band16.py` | v1 | re-reduce Off_Off with the off-spec band widened 1.4→1.6 Å | — |
| `sweep_xysigma0.py` | v1 | sweep the smoothing kernel `xysigma0` (ruled smoothing out) | — |
| `test_44161_crop.py` | v1 | 44161 S.sum vs band half-width (1.4/1.6/none) — pins the band-crop as the 44161 cause | — |

## Typical order for the proton-charge / deficit reproduction
1. `v1_load_probe.py` (v1) → writes `/tmp/v1_44159.npz`
2. `v2_load_probe.py` (v2) → confirms identical histograms
3. `pc_split_probe.py` (v2) → per-channel charge fractions
4. `verify_pc_split.py` (v1) → matches Mantid's split
5. `v1_offspec_allruns.py` (v1) + `v2_offspec_allruns.py` (v2) → per-run v1/v2 ratios
6. `test_44161_crop.py` (v1) → band-crop is the 44161 residual
