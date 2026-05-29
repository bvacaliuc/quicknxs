# DB_ID=1/1/1 in v2 off-spec files — root cause + v1↔v2 interop (2026-05-29)

Closes the prompt-29 DB_ID thread. Resolves whether v2's `DB_ID=1/1/1` (seen in
`/SNS/users/6ov/shared/REF_M/11486/correctReduction/*OffSpecSmooth*.dat`) is a bug.

## TL;DR — it IS a v2 writer bug; the user's assumption was correct

`correctReduction` was produced by a **PAIRED** reduction (44159→44033, 44160→44034,
44161→44035) but its `[Data Runs]` `DB_ID` column was written **1/1/1** because of a
pass-by-value bug in v2's writer. Both v1 and v2 read `DB_ID` *literally*, so re-reading
the file reconstructs **single-DB (all→44033)** — a different, physically wrong
normalization. v2 can paper over it with the optional **Match-direct-beam** angle
re-match (default OFF); v1 has no such feature, so v1 is stuck with the wrong single-DB.

## The bug (v2)

`quicknxsv2/src/quicknxs/interfaces/data_handling/quicknxs_io.py`:

- `[Direct Beam Runs]` block (write_reflectivity_header, ~L120-162): `i_direct_beam`
  is incremented **inside the loop body** → correctly enumerates 1,2,3 with the actual
  DB run numbers (44033/44034/44035). So the DB block faithfully records the paired DBs.
- `[Data Runs]` block (~L173-177) calls
  `_get_cross_section_config_values(cross_section_data, i_direct_beam)` per run, and the
  helper (~L237-242) does:
  ```python
  if normalization_run == "None":
      db_id = 0
  else:
      i_direct_beam += 1   # BUG: increments the LOCAL int param, not the caller's
      db_id = i_direct_beam
  ```
  Python passes ints by value, so the caller's `i_direct_beam` (initialized 0 at L173)
  never advances. Every data run with a real DB gets `db_id = 0+1 = 1` ⇒ **DB_ID=1/1/1**.
  The intent was clearly 1,2,3 (mirroring the DB block).

**Evidence that the data is paired, not single:** the `[Direct Beam Runs]` block lists
three *different* run numbers (44033/44034/44035). The block is written one-entry-per-
data-run from each run's `normalization_run`; three different numbers ⇒ the three data
runs were normalized by three different DBs ⇒ paired. A single-DB reduction would have
written 44033/44033/44033.

## How DB_ID is USED on read

- **v1** (`quicknxs/qio.py:643`): `calc_opts['normalization']=self.norms[int(db['DB_ID'])-1]`.
  Literal. No angle re-match anywhere in v1. Reading 1/1/1 ⇒ every run → `norms[0]` = 44033
  ⇒ **single**. v1 cannot recover the paired intent.
- **v2** (`quicknxs_io.py:427-429`): `conf.normalization = direct_beam_runs[DB_ID-1][0]`.
  Also literal ⇒ reading 1/1/1 ⇒ all → `direct_beam_runs[0]` = 44033 ⇒ **single** —
  UNLESS `Configuration.match_direct_beam` is ON (default **False**, `configuration.py:148`),
  in which case `DataManager.load` calls `find_best_direct_beam()` (`data_manager.py:467`)
  and re-matches by angle, OVERRIDING the file's DB_ID and recovering the paired DBs.
  This optional re-match is what "papers over" the bug *in v2 only*.

## v1 writer is correct (v1→v2 is safe)

`quicknxs/qio.py:209-214` writes `DB_ID = self.norms.index(refl.options['normalization'])+1`
— the index of each run's *actual* normalization object. Paired ⇒ 1/2/3, single ⇒ 1/1/1,
faithfully. So a v1-written file round-trips correctly through a literal reader.

## Interop matrix (off-spec / reflectivity .dat)

| direction | result | safe? |
|---|---|---|
| v1 → v1 | v1 writes true DB_IDs, reads them literally | **SAFE** |
| v1 → v2 | v2 reads v1's true DB_IDs literally | **SAFE** (match-DB off) |
| v2 → v2 (match-DB **on**) | angle re-match recovers paired | OK (recovered) |
| v2 → v2 (match-DB **off**, default) | literal 1/1/1 ⇒ single, paired intent lost | **WRONG** |
| **v2 → v1** | literal 1/1/1 ⇒ single; v1 has no re-match | **DANGEROUS** |

The v2→v1 case is the dangerous one: a multi-DB (paired) v2 reduction silently re-reduces
as single-DB in v1, giving a lower, physically wrong normalization for the higher-angle
runs that still *looks* like a valid result. This is exactly the trap that sent earlier
sessions chasing a phantom "single-DB reference".

## What is correct / dangerous

- **Correct physics = PAIRED.** Each data run must be normalized by its own matched
  direct beam (its slit/resolution-matched DB). Using DB[0] (44033) for all (the literal
  1/1/1 reading) mis-normalizes 44160/44161. So `correctReduction`'s *data* (paired) is
  the right target; its *DB_ID column* (1/1/1) is wrong.
- The session13 `..._OffSpecSmooth_Off_Off-correct-db-id.dat` is the buggy file with the
  `DB_ID` column hand-relabeled to **1/2/3** — i.e. the corrected paired assignment that
  literal readers (v1) need. Use `--db-mode paired` (or `--db-mode header` on the
  -correct-db-id file) to reproduce `correctReduction`; **do NOT use single** (my earlier
  end-to-end did, which is part of why it landed low — corrected here).

## Recommendations

1. **Fix v2's writer** (the real fix): make `_get_cross_section_config_values` not rely on
   a mutated int param — pass/return the running index, or compute DB_ID from the run's
   `normalization_run` matched against the emitted DB list (the same key the DB block uses).
2. **Harden v1's reader** against buggy upstream files: when `DB_ID`s are all equal but the
   `[Direct Beam Runs]` block lists multiple distinct run numbers, warn (and optionally
   offer paired/by-number matching) rather than silently collapsing to single.
3. Until (1) ships, treat any v2-written multi-DB off-spec/reflectivity file as suspect;
   prefer reducing from raw with explicit per-run DBs (paired), or relabel DB_IDs.

Method scripts for this and the deficit analysis live in `plan/scripts/` (see that
directory's README); reference data in `/SNS/users/6ov/shared/REF_M/11486/`.
