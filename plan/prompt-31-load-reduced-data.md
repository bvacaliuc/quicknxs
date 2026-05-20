# prompt-31: Load Reduced Data from QuickNXS v2 files

Goal (from the session that produced commits `1b2439f`, `ddb7944`):
quicknxsv1 should open a QuickNXS **v2** reduced `.dat` file via
**File → Load Extraction…** ("Load Reduced Data"), reconstruct the recipe
(direct beams + data runs + scale factors), and reproduce a statistically
similar reduction.

Reference data on this machine:
`/SNS/users/6ov/shared/REF_M/11486/correctReduction/` — 7 files written by
QuickNXS 4.3.0rc1 / Mantid 6.12.0 (2025-04-08, IPTS-34473, DB 44033/34/35,
data 44159/60/61). The intended off-spec/specular "correct" outputs.

## What landed (committed, tested)

### Parse (was a hard blocker)
`HeaderParser` raised `IndexError` on the v2 `[Global Options]` block
because a long key (`lock_direct_beam_y`) left only one space before its
value and the 2-space column split dropped it. Fixed in `quicknxs/qio.py`
(`_evaluate_global_options` + eval-free `_convert_scalar`). **All 7 v2
files now parse** (`DB=3, DR=3, Global Options` extracted). Test:
`tests/qio_test.py::V2GlobalOptionsParseTest`.

### Reproduce (verified on real data)
`scripts/validate_load_reduced_specular.py` loads the v2
`Specular_Off_Off.dat` *through `HeaderParser` — the same path the GUI's
Load Extraction uses* — reconstructs 3 DBs + 3 refls, stitches R(Qz) and
compares to the embedded `[Data]` table:

```
reconstructed: 3 direct beams, 3 refls
                              40 bins      160 bins
log-R Pearson correlation :   0.9609       0.9670     # shape matches v2
median ratio (mine/ref)   :   0.3109       0.3120     # ~3.2x dim, STABLE
RMS log10 residual (dex)  :   0.6266       0.6233
```

**Shape reproduction is excellent (corr 0.96–0.97).** The intensity offset
is a **constant ~3.2× factor that does NOT move with bin count** (0.311 at
40 bins vs 0.312 at 160). This is *unlike* the off-spec smoothing case in
`plan/prompt-28-findings.md` (where the ratio was bin-density dependent,
0.45→1.30 from 40→80). For **specular**, the bin-independent constant
points to a **normalization-convention** difference, not a binning artifact.

### Investigation lead: the ~3.2× specular constant
Per `setup/patterns/numerical-diagnostics.md` (clean-factor audit before
chasing physics): 1/0.311 ≈ **3.21** (near π ≈ 3.14). Candidates, in
likely order — audit each as a parameter, not new physics:
- **Sample-length / footprint correction.** The recipe sets
  `sample_length 10.0`; check whether quicknxsv1 applies the footprint /
  beam-spill factor that v2 (Mantid `MagnetismReflectometryReduction`)
  applies. This is the most likely single global factor.
- **`sin_scale` / solid-angle** in `qreduce.Reflectivity`
  (`self.R = sin_scale*options['scale']*self.Rraw`, ~line 2932) and the
  direct-beam `Rraw` normalization.
- **Stitch method.** This script *concatenates* the 3 refls' points; v2
  weight-merges overlaps. That perturbs overlap regions but cannot produce
  a uniform 3.2× across all Qz — so it is not the main cause, but use the
  GUI/`Reducer` stitch for a definitive number.
Confirm constancy is real (not a stitch artifact) by comparing a **single**
refl (e.g. 44159 alone) to the reference over its own Qz range.

## Remaining work

### 1. Resolve the specular normalization constant
Find and document the ~3.2× factor (above). A constant scale is often
acceptable in reflectometry (curves are scaled in fitting), but the match
is only a "stunning success" once the convention is understood. Do **not**
keep raising `--bins` for specular — empirically it does not move the
ratio.

### 2. GUI smoke test of Load Extraction on a v2 file
`make gui` → File → Load Extraction… → pick
`correctReduction/REF_M_44159+44160+44161_peak1_Specular_Off_Off.dat`.
Confirm: 3 DBs populate the normalization table, 3 refls populate the
reduction table, the spinboxes show the refl region (prompt-30), and the
reflectivity plot renders. This exercises `loadExtraction` →
`HeaderParser.parse()` → `setNorm`/`addRefList` end to end (headlessly
covered by `LoadExtractionRoundTrip`, but never clicked through on a real
v2 file).

### 3. Off-specular reproduction
The off-spec path is already validated headlessly in prompt-28
(`scripts/compare_offspec_44159.py`, `scripts/reduce_offspec_headless.py`).
Re-confirm against `correctReduction/*OffSpecSmooth*` after the prompt-30
changes and at matched bins. Note `reduce_offspec_headless.py` uses its own
recipe parser (`parse_recipe`), independent of the `HeaderParser` fix.

### 4. `session12/` files ("what v2 can produce today")
The user referenced `/SNS/users/6ov/shared/REF_M/11486/session12/**` as a
second, harder target. **It does not exist on this mount** (only
`session1`–`session9`; `session12` appears only in
`compare/*-session12.png` filenames). It is likely on the other machine
(`/media/ssd2/...`) or post-dates this mount snapshot. When it appears,
repeat (1)–(3) against it; expect the same load path to work since the
header format is shared.

## Key facts for the next agent
- "Load Reduced Data" in quicknxsv1 == **File → Load Extraction…** ==
  `MainGUI.loadExtraction` → `qio.HeaderParser`.
- v2 and v1 share the `.dat` section format
  (`[Direct Beam Runs]`/`[Data Runs]`/`[Global Options]`/`[Data]`); the
  only parse incompatibility found was the Global Options spacing (fixed).
- The referenced `.nxs.h5` files exist under
  `/SNS/REF_M/IPTS-34473/nexus/REF_M_440{33,34,35,59,60,61}.nxs.h5`.
