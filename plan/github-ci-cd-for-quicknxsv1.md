# GitHub CI/CD for quicknxsv1

## Context

The `quicknxsv1` project has no `.github/` directory and only a dead Travis CI badge in its README. The goal is to add modern GitHub Actions CI with: linting (ruff), testing (pytest + coverage), Codecov integration, automated monthly lockfile updates, and branch protection on `main`. The reference project `neutrons/quicknxs` provides patterns to follow.

## Constraints

- **linux-64 only**: `pixi.lock` is a single-platform lock (no matrix testing)
- **Qt headless**: `conftest.py` already sets `QT_QPA_PLATFORM=offscreen`; no Xvfb needed
- **Test data**: ~23 MB NXS files are committed directly, not LFS
- **Coverage source**: `quicknxs/` (flat layout, not `src/`)
- **Codecov token**: Requires a GitHub Actions secret set manually — create a GitHub issue

## Implementation Sequence

**Critical**: branch protection must be applied _after_ the first CI run registers the check names.

1. Create `.github/workflows/ci.yml` and `.github/workflows/update-lockfile.yml`
2. Update `README.md` (replace dead Travis badge)
3. Commit and push to `dragonfly` branch
4. Create PR from `dragonfly` → `main` (triggers first CI run)
5. After CI passes: `gh api` to set branch protection on `main`
6. `gh issue create` for CODECOV_TOKEN setup
7. `gh issue create` for enabling "Allow GitHub Actions to create/approve PRs" (lockfile workflow needs it)
8. Merge the PR

---

## File 1: `.github/workflows/ci.yml`

```yaml
# Main CI pipeline: lint + test with coverage
#
# Pinned actions (tag + full SHA for supply-chain security):
#   actions/checkout        v4.2.2  11bd71901bbe5b1630ceea73d27597364c9af683
#   prefix-dev/setup-pixi  v0.9.4  a0af7a228712d6121d37aba47adf55c1332c9c2e
#   codecov/codecov-action  v5.5.0  fdcc8476540edceab3de004e990f80d881c6cc00

name: CI

on:
  push:
    branches: [main, dragonfly]
    tags: ["v*"]
  pull_request:
    branches: [main]
  workflow_dispatch:

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

defaults:
  run:
    shell: bash -el {0}

jobs:
  lint:
    name: lint
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2
      - uses: prefix-dev/setup-pixi@a0af7a228712d6121d37aba47adf55c1332c9c2e  # v0.9.4
        with:
          cache: true
      - name: Run ruff
        run: pixi run ruff check quicknxs/

  test:
    name: test
    runs-on: ubuntu-24.04
    env:
      QT_QPA_PLATFORM: offscreen
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2
      - uses: prefix-dev/setup-pixi@a0af7a228712d6121d37aba47adf55c1332c9c2e  # v0.9.4
        with:
          cache: true
      - name: Run pytest with coverage
        run: pixi run pytest --cov=quicknxs --cov-report=xml
      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@fdcc8476540edceab3de004e990f80d881c6cc00  # v5.5.0
        with:
          token: ${{ secrets.CODECOV_TOKEN }}
          files: coverage.xml
          fail_ci_if_error: false
```

**Notes on job naming**: `name: lint` and `name: test` exactly match the strings used in the branch protection `contexts` array below, avoiding ambiguity.

---

## File 2: `.github/workflows/update-lockfile.yml`

```yaml
# Monthly automated pixi lockfile refresh → opens a PR against main
#
# Requires repo setting: Settings > Actions > General >
#   "Allow GitHub Actions to create and approve pull requests" = ON
#
# Pinned actions:
#   actions/checkout             v4.2.2  11bd71901bbe5b1630ceea73d27597364c9af683
#   prefix-dev/setup-pixi        v0.9.4  a0af7a228712d6121d37aba47adf55c1332c9c2e
#   peter-evans/create-pull-request v8.1.0  c0f553fe549906ede9cf27b5156039d195d2ece0

name: Update pixi lockfile

on:
  schedule:
    - cron: "17 5 1 * *"   # 05:17 UTC on 1st of every month
  workflow_dispatch:

permissions:
  contents: write
  pull-requests: write

defaults:
  run:
    shell: bash -el {0}

jobs:
  update-lockfile:
    name: Update pixi.lock
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2
      - uses: prefix-dev/setup-pixi@a0af7a228712d6121d37aba47adf55c1332c9c2e  # v0.9.4
        with:
          cache: false   # always resolve fresh against conda-forge

      - name: Update lockfile and generate markdown diff
        run: |
          pixi update --json | pixi exec pixi-diff-to-markdown > diff.md
          cat diff.md

      - name: Build PR body
        id: pr-body
        run: |
          {
            echo "body<<PR_BODY_EOF"
            echo "## Monthly pixi lockfile update"
            echo ""
            echo "Automated dependency bump from the monthly workflow."
            echo ""
            cat diff.md
            echo "PR_BODY_EOF"
          } >> "$GITHUB_OUTPUT"

      - name: Create Pull Request
        uses: peter-evans/create-pull-request@c0f553fe549906ede9cf27b5156039d195d2ece0  # v8.1.0
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
          commit-message: "chore: update pixi.lock"
          branch: chore/update-pixi-lockfile
          delete-branch: true
          title: "chore: monthly pixi lockfile update"
          body: ${{ steps.pr-body.outputs.body }}
          labels: dependencies
          base: main
```

---

## File 3: Updated `README.md`

Replace the single-line file with:

```markdown
[![CI](https://github.com/bvacaliuc/quicknxs/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/bvacaliuc/quicknxs/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/bvacaliuc/quicknxs/branch/main/graph/badge.svg)](https://codecov.io/gh/bvacaliuc/quicknxs)

# QuickNXS v1

Magnetism Reflectometer data reduction software (QuickNXS v1 fork).
```

---

## GitHub API Actions (post-push)

### Branch protection for `main`
Run **after** the first CI run completes (so status check names are registered):

```bash
gh api \
  --method PUT \
  repos/bvacaliuc/quicknxs/branches/main/protection \
  --input - <<'EOF'
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["lint", "test"]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": null,
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
EOF
```

### GitHub issue: Codecov token

```bash
gh issue create \
  --repo bvacaliuc/quicknxs \
  --title "Configure CODECOV_TOKEN secret for coverage reporting" \
  --body "..."
```

### GitHub issue: Workflow PR permissions (for lockfile workflow)

```bash
gh issue create \
  --repo bvacaliuc/quicknxs \
  --title "Enable 'Allow GitHub Actions to create PRs' for lockfile workflow" \
  --body "..."
```

---

## Critical Files

| File | Purpose |
|------|---------|
| `quicknxsv1/pyproject.toml` | Defines pixi tasks and pytest config |
| `quicknxsv1/tests/conftest.py` | Confirms offscreen Qt — no Xvfb step needed |
| `quicknxsv1/README.md` | Replace Travis badge |
| `quicknxsv1/pixi.lock` | Confirms linux-64 only (no matrix) |

## Verification

1. After push to `dragonfly`, check GitHub Actions tab — both `lint` and `test` jobs appear
2. `test` job: all pytest tests pass; `coverage.xml` artifact is present in the step log
3. Codecov step shows a warning (no token yet) but does not fail CI
4. After setting `CODECOV_TOKEN` secret: Codecov badge updates with a percentage
5. After branch protection: PRs to `main` require both checks green before merge
6. Monthly lockfile workflow: trigger manually via `workflow_dispatch` to verify PR creation
