# Fix: pixi.lock `editable` field toggles between systems

## Problem

`pixi.lock` oscillates between having `editable: true` and not having it for the
local `quicknxs-v1` dependency, depending on which system regenerates the lock
file.  This produces spurious commits and noisy `git diff` output.

### Symptom

```yaml
# pixi.lock — sometimes present (analysis.sns.gov)
- pypi: ./
  name: quicknxs-v1
  version: 1.1.6
  sha256: ...
  requires_python: '>=3.10,<3.13'
  editable: true          # <-- present on older pixi, absent on 0.63.2

# pixi.lock — sometimes absent (dragonfly / pixi 0.63.2)
- pypi: ./
  name: quicknxs-v1
  ...
  requires_python: '>=3.10,<3.13'
                          # <-- editable: true omitted
```

### Root Cause

pixi 0.63.2 no longer writes the `editable` field to `pixi.lock` for local path
dependencies.  It infers editability from `pyproject.toml` at install time, so
the lock-file field is redundant.  Older pixi versions still write it explicitly.

The package IS installed as editable on both systems regardless:
- `site-packages/__editable__.quicknxs_v1-1.1.6.pth` exists on both
- `direct_url.json` contains `{"dir_info": {"editable": true}}` on both
- `quicknxs.__file__` resolves to the source tree on both

The toggle is **functionally harmless** but produces unnecessary git noise every
time the lock file is regenerated on a system with the older pixi.

## Fix

### Step 1 — Add `requires-pixi` to `pyproject.toml`

In `[tool.pixi.workspace]`, add:

```toml
[tool.pixi.workspace]
platforms = ["linux-64"]
channels = ["conda-forge"]
requires-pixi = ">=0.63.2"
```

This causes older pixi to refuse and prompt the user to upgrade rather than
silently regenerating the lock file in the old format.

### Step 2 — Upgrade pixi on analysis.sns.gov

```bash
# On analysis.sns.gov:
pixi self-update
pixi --version   # should show >= 0.63.2
```

After upgrading, running `pixi install` or `make test` on analysis.sns.gov will
regenerate the lock file in the new format (without `editable: true`), and the
toggle stops.

### Step 3 — Commit the result

After confirming pixi >= 0.63.2 on all development systems, commit the updated
`pyproject.toml` and the stabilised `pixi.lock`.

## Verification

After applying the fix, run on both systems:

```bash
make test
git diff pixi.lock   # should be empty after both systems run
```

Also confirm the editable install is working:

```bash
pixi run python -c "import quicknxs; print(quicknxs.__file__)"
# Should print: .../quicknxsv1/quicknxs/__init__.py  (not inside .pixi/envs/...)
```

## Notes

- Lock file format `version: 6` is unchanged — this is a serialisation behaviour
  difference only, not a schema change.
- If analysis.sns.gov cannot be upgraded (e.g. managed environment), the only
  alternative is to treat `pixi.lock` as system-generated and exclude the
  `editable` field changes from commit review conventions.
- GitHub issue: https://github.com/bvacaliuc/quicknxs/issues/TBD
