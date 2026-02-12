# quicknxsv1: Python 2 + Qt4 → Python 3 + Qt5 Migration Plan

## Context

**quicknxsv1** is a legacy Python 2 / PyQt4 application for neutron reflectometry data reduction (SNS beamline 4A). The goal is to modernize it to Python 3 + Qt5, matching the patterns used by the sibling **quicknxsv2** project. The upstream author began this work on the `upstream/py3_qt5` branch (partially migrating Qt4→Qt5 imports and regenerating UI files), but left many Python 2 idioms, several Qt5 misplacements, and no build infrastructure. This plan completes that work in a structured, test-driven manner suitable for parallel agent execution.

**Working directory:** `/home/bvacaliuc/Projects/Claude/quicknxsv1`
**Current branch:** `feature/pixi_py3_qt5`
**Reference project:** `/home/bvacaliuc/Projects/Claude/quicknxsv2`

---

## Phase 0: Build Infrastructure & Branch Setup

**Goal:** Create the pixi-based build system so we can install dependencies and run tests.
**Blocks:** All other phases (nothing can be tested without this).

### Tasks

#### 0.1 Merge upstream/py3_qt5 into feature branch
- `git merge upstream/py3_qt5` into `feature/pixi_py3_qt5`
- This gives us the partially-migrated code as our starting point
- Resolve any merge conflicts

#### 0.2 Create `pyproject.toml`
Reference: `/home/bvacaliuc/Projects/Claude/quicknxsv2/pyproject.toml`

```
[project]
name = "quicknxs-v1"
description = "QuickNXS v1 - Magnetism Reflectometer data reduction"
requires-python = ">=3.10,<3.13"

[build-system]
build-backend = "setuptools.build_meta"
requires = ["setuptools>=68.0"]

[tool.setuptools.packages.find]
where = ["."]
include = ["quicknxs*"]

[tool.pixi.workspace]
platforms = ["linux-64"]
channels = ["conda-forge"]

[tool.pixi.dependencies]
python = ">=3.10,<3.13"
pyqt = ">=5.15,<6"
qtpy = "*"
numpy = "*"
matplotlib = ">=3.8"
h5py = "*"
scipy = "*"

[tool.pixi.pypi-dependencies]
quicknxs-v1 = { path = ".", editable = true }

[tool.pixi.feature.test.dependencies]
pytest = ">=8"
pytest-cov = "*"
pytest-qt = ">=4.4.0"
pytest-xvfb = ">=3.1.1"

[tool.pixi.feature.dev.dependencies]
ruff = "*"

[tool.pixi.environments]
default = { features = ["dev", "test"], solve-group = "default" }

[tool.pixi.tasks]
test = { cmd = "pytest", description = "Run the test suite" }
test-core = { cmd = "pytest tests/qreduce_test.py tests/qcalc_test.py tests/qio_test.py -v", description = "Run non-GUI tests" }
test-gui = { cmd = "pytest tests/main_gui_test.py -v", description = "Run GUI tests" }

[tool.pytest.ini_options]
testpaths = ["tests/"]
python_files = ["*_test.py"]

[tool.ruff.lint]
select = ["E", "F", "W"]

[tool.ruff.lint.per-file-ignores]
"quicknxs/icons_rc.py" = ["E501"]
"quicknxs/default_interface.py" = ["E501"]
"quicknxs/docked_interface.py" = ["E501"]
```

#### 0.3 Create `Makefile`
```makefile
.PHONY: install test test-core test-gui lint clean

install:
	pixi install

test: install
	pixi run test

test-core: install
	pixi run test-core

test-gui: install
	pixi run test-gui

lint: install
	pixi run ruff check quicknxs/

clean:
	rm -rf __pycache__ .pytest_cache *.egg-info
```

#### 0.4 Verify pixi environment resolves
- Run `pixi install` to confirm all dependencies resolve
- Run `pixi shell` and confirm `python --version` shows 3.10+

**Gate:** `pixi install` succeeds and Python 3 is available.

---

## Phase 1: Critical Import Chain Fix (Sequential, Unblocks Everything)

**Goal:** Fix the Python 2 syntax that prevents ANY module from importing under Python 3.
**Blocks:** All subsequent phases. These files form the import chain that every other module depends on.

The import chain is: `quicknxs.config.__init__` → `quicknxs.config.baseconfig` → `quicknxs.decorators`. If any of these fail to import, nothing else works.

### Tasks

#### 1.1 Fix `quicknxs/decorators.py`
**Critical blockers (prevents import):**
- Line 9: `from StringIO import StringIO` → `from io import StringIO`
- Line 29: `inspect.getargspec(func)` → `inspect.getfullargspec(func)`
- Line 38: `func.func_defaults` → `func.__defaults__`
- Line 40: `func.func_globals` → `func.__globals__`; `func.func_closure` → `func.__closure__`
- Line 68: `wrapper.func_defaults` → `wrapper.__defaults__`
- Lines 136-139: `func.im_func.func_code` → `func.__func__.__code__`; `func.func_code` → `func.__code__`
- Lines 229, 166: `func.im_func` → `hasattr(func, '__func__')`
- Lines 318-320: `raise ValueError, "..."` → `raise ValueError("...")`

#### 1.2 Fix `quicknxs/config/__init__.py`
- Line 75: `except Exception, error:` → `except Exception as error:`
- Line 101: `exec "global %s;%s=config_holder"%(name, name)` → use `globals()[name] = config_holder`
- Line 46: `from logging import warn` → `from logging import warning` (or `import warnings`)

#### 1.3 Fix `quicknxs/config/baseconfig.py`
- Check for Python 2 syntax; fix any `except X, e:` patterns
- Check for `unicode` / `basestring` type references
- Check for `has_key()` dict calls

#### 1.4 Fix `quicknxs/config/configobj.py` (87KB vendored)
- This is a large vendored file. Scan for Python 2 syntax blockers
- Focus only on import-blocking syntax: `print` statements, `except X, e:`, `exec`, `raise X, Y`
- Consider replacing with a pip-installable `configobj` package if the vendored version is too problematic

#### 1.5 Fix `quicknxs/gui_logging.py` and `quicknxs/console_logging.py`
- These are imported early in the startup chain
- Fix any Python 2 syntax

**Gate:** `python -c "from quicknxs.config import ref_m; print('OK')"` succeeds under Python 3.

---

## Phase 2: Core Data Module Migration (Parallelizable)

**Goal:** Migrate non-Qt Python files from Python 2 to 3. These modules can be tested independently.
**Requires:** Phase 1 complete.

### Common Python 2→3 patterns to apply across all files:
| Python 2 | Python 3 |
|-----------|----------|
| `print x` | `print(x)` |
| `unicode(x)` | `str(x)` |
| `u'string'` | `'string'` (keep u-prefix, it's harmless but unnecessary) |
| `basestring` | `str` |
| `except E, e:` | `except E as e:` |
| `raise E, msg` | `raise E(msg)` |
| `dict.has_key(k)` | `k in dict` |
| `dict.iteritems()` | `dict.items()` |
| `dict.itervalues()` | `dict.values()` |
| `xrange()` | `range()` |
| `type(x) is unicode` | `isinstance(x, str)` |
| `exec code in gls` | `exec(code, gls)` |
| `cmp(a, b)` | `(a > b) - (a < b)` |
| `reduce()` | `from functools import reduce` |
| `reload()` | `from importlib import reload` |

### Agent Stream A: Core Science Modules

#### 2A.1 `quicknxs/qreduce.py` - Core data reduction
- Main data loading and reflectivity extraction
- Fix Python 2 syntax, string handling, division behavior
- **Test with:** `tests/qreduce_test.py`

#### 2A.2 `quicknxs/qcalc.py` - Calculations
- Gaussian fitting, stitching, position detection, smoothing
- Fix Python 2 syntax
- **Test with:** `tests/qcalc_test.py`

#### 2A.3 `quicknxs/qio.py` - I/O and export
- Header creation/parsing, data export
- `unicode()` calls are heavily used here - replace with `str()`
- **Test with:** `tests/qio_test.py`

#### 2A.4 `quicknxs/mpfit.py` - Fitting library (115KB vendored)
- Large vendored Marquardt-Levenberg fitting
- Carefully scan for Python 2 patterns
- Consider `from __future__` removals

### Agent Stream B: Supporting Modules

#### 2B.1 `quicknxs/peakfinder.py`
#### 2B.2 `quicknxs/genx_data.py`
#### 2B.3 `quicknxs/database.py` and `quicknxs/database_updater.py`
#### 2B.4 `quicknxs/version.py` (minimal changes expected)

### Agent Stream C: Buzhug Package

#### 2C.1 `quicknxs/buzhug/` - all 5 files
- `buzhug.py`, `buzhug_algos.py`, `buzhug_files.py`, `buzhug_info.py`, `conversion_float.py`
- This is a vendored database package - may have extensive Python 2 patterns
- Focus on making it importable and functional

### Agent Stream D: Config Subpackage

#### 2D.1 Remaining config modules
- `quicknxs/config/email.py`, `export.py`, `gui.py`, `misc.py`
- `quicknxs/config/output_templates.py`, `paths.py`, `plotting.py`
- `quicknxs/config/ref_l.py`, `ref_m.py` (fix hardcoded paths in ref_m.py)

**Gate:** `pixi run test-core` passes - all non-GUI tests (qreduce_test, qcalc_test, qio_test) pass under Python 3.

---

## Phase 3: Test Infrastructure Migration

**Goal:** Modernize tests from unittest to pytest patterns and fix Python 2 syntax in test files.
**Requires:** Phase 2 complete.

### Tasks

#### 3.1 Fix `tests/qreduce_test.py`
- Fix `u'string'` literals, Python 2 syntax

#### 3.2 Fix `tests/qcalc_test.py`
- Line 29: `raise ValueError, "..."` → `raise ValueError("...")`
- Fix any other Python 2 patterns

#### 3.3 Fix `tests/qio_test.py`
- Replace `unicode(header)` → `str(header)`
- Replace `type(x) is unicode` → `isinstance(x, str)`
- Fix any `dict.items()` vs `dict.iteritems()` issues

#### 3.4 Fix `tests/main_gui_test.py` (Qt-dependent, do after Phase 4)
- Fix imports: `from PyQt5.QtGui import QApplication, QMainWindow` → use qtpy:
  ```python
  from qtpy.QtWidgets import QApplication, QMainWindow
  from qtpy.QtTest import QTest
  from qtpy.QtCore import QLocale
  ```
- Fix `basestring` reference on line 13
- Fix any Python 2 patterns

#### 3.5 Fix `tests/__init__.py`
- Fix `dict.values()` usage if needed
- Ensure test discovery works with pytest

#### 3.6 Fix `test_all.py`
- This is the legacy test runner; keep it working but tests should also run via `pytest`

**Gate:** `pixi run test-core` passes with the fixed test files.

---

## Phase 4: Qt4→Qt5 Migration via qtpy (Parallelizable)

**Goal:** Complete the Qt migration using qtpy abstraction layer (matching quicknxsv2 pattern).
**Requires:** Phases 1-2 complete. Can overlap with Phase 3.

### Design Decision: Use qtpy
Following quicknxsv2's pattern, all Qt imports will use `qtpy` as the abstraction layer:
```python
# Before (PyQt4 or direct PyQt5):
from PyQt4.QtGui import QMainWindow, QWidget
from PyQt5.QtWidgets import QMainWindow, QWidget

# After (qtpy):
from qtpy.QtWidgets import QMainWindow, QWidget
from qtpy.QtGui import QPixmap, QColor, QPainter
from qtpy.QtCore import Qt, QTimer, Signal
from qtpy.QtPrintSupport import QPrinter, QPrintPreviewDialog
```

### Qt4→Qt5 Module Remapping Reference
| Qt4 (PyQt4.QtGui) | Qt5 Location |
|---|---|
| QMainWindow, QWidget, QDialog, QFrame | qtpy.QtWidgets |
| QApplication, QDesktopWidget | qtpy.QtWidgets |
| QLabel, QPushButton, QLineEdit, QTextEdit | qtpy.QtWidgets |
| QTableWidgetItem, QTreeWidgetItem, QListWidgetItem | qtpy.QtWidgets |
| QFileDialog, QMessageBox, QInputDialog, QColorDialog | qtpy.QtWidgets |
| QVBoxLayout, QHBoxLayout, QGridLayout | qtpy.QtWidgets |
| QSizePolicy, QSplitter, QProgressBar | qtpy.QtWidgets |
| QAction, QMenu, QMenuBar, QToolBar, QStatusBar | qtpy.QtWidgets |
| QPrinter, QPrintPreviewDialog | qtpy.QtPrintSupport |
| QPixmap, QColor, QPainter, QFont, QIcon, QImage | qtpy.QtGui (stays) |
| QCursor, QPen, QBrush | qtpy.QtGui (stays) |
| Signal (pyqtSignal) | qtpy.QtCore.Signal |

### Deprecated API Replacements
| Deprecated (Qt4) | Qt5 Replacement |
|---|---|
| `setMargin(n)` | `setContentsMargins(n, n, n, n)` |
| `setTextColor(color)` | `setForeground(QBrush(color))` |
| `setBackgroundColor(color)` | `setBackground(QBrush(color))` |
| `header().setMovable(True)` | `header().setSectionsMovable(True)` |
| `QMessageBox.NoButton` | Remove (just use `QMessageBox.Ok`) |
| `app.exec_()` | `app.exec()` (or keep `exec_()` - both work) |
| `QDesktopWidget` | `QApplication.primaryScreen().availableGeometry()` |

### Agent Stream E: Core GUI Module

#### 4E.1 `quicknxs/mplwidget.py` - Matplotlib/Qt integration (HIGH PRIORITY)
Used by every GUI module. Fix:
- All `from PyQt5` → `from qtpy`
- `QtWidgets.QPixmap` → `QtGui.QPixmap`
- `QtWidgets.QPrintPreviewDialog` → `QtPrintSupport.QPrintPreviewDialog`
- `QtGui.QPrinter` → `QtPrintSupport.QPrinter`
- `QtWidgets.QMessageBox.NoButton` → remove
- `except Exception, e:` → `except Exception as e:`
- `setMargin(1)` → `setContentsMargins(1, 1, 1, 1)` (currently commented out)
- matplotlib backend: keep `Qt5Agg` (already done on upstream branch)
- Backend imports: `from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg` (modern) or keep `backend_qt5agg`

#### 4E.2 `quicknxs/main_gui.py` - Main window (~2500 lines, LARGEST)
- All `from PyQt5` → `from qtpy`
- `exec code in gls` → `exec(code, gls)` (line ~2461)
- `from PyQt5.pyqtconfig import Configuration` → `from qtpy.QtCore import PYQT_VERSION_STR`
- All `setTextColor`/`setBackgroundColor` → `setForeground`/`setBackground`
- `unicode()` calls → `str()`
- All Python 2 syntax fixes

#### 4E.3 `quicknxs/gui_utils.py`
#### 4E.4 `quicknxs/gui_logging.py` (may already be partially done in Phase 1)

### Agent Stream F: Dialog/Widget Modules

#### 4F.1 `quicknxs/compare_plots.py`
- `from PyQt5` → `from qtpy`
- `setSectionsMovable(True)` to replace commented-out `setMovable(True)`

#### 4F.2 `quicknxs/database_dialog.py`
#### 4F.3 `quicknxs/nxs_gui.py`
#### 4F.4 `quicknxs/point_picker.py`
#### 4F.5 `quicknxs/polarization_gui.py`
#### 4F.6 `quicknxs/rawcompare_plots.py`
#### 4F.7 `quicknxs/separate_plots.py`
#### 4F.8 `quicknxs/smooth_dialog.py` (hand-coded, not the generated one)
#### 4F.9 `quicknxs/background_dialog.py` and `quicknxs/advanced_background.py`
#### 4F.10 `quicknxs/gisans_dialog.py`
#### 4F.11 `quicknxs/help_widgets.py`
#### 4F.12 `quicknxs/persistentframe.py`
#### 4F.13 `quicknxs/quicklog_gui.py`
#### 4F.14 `quicknxs/filter_widget.py` (hand-coded wrapper)
#### 4F.15 `quicknxs/ipython_widget.py` and `quicknxs/ipython_tools.py`
- `QtGui.QApplication` → `QtWidgets.QApplication`

### Agent Stream G: Generated UI Files

#### 4G.1 Regenerate with pyuic5 (if .ui files available in `designer/`)
The upstream branch already regenerated these. Verify they use `from PyQt5`:
- `quicknxs/default_interface.py` - ✓ already pyuic5
- `quicknxs/docked_interface.py` - ✓ already pyuic5
- `quicknxs/icons_rc.py` - ✓ already pyrcc5

For qtpy compatibility, the generated files that import `from PyQt5` directly are acceptable since qtpy sets the backend. Alternatively, post-process them to use `from qtpy`.

#### 4G.2 Update generated widget/dialog files
These were already regenerated on upstream/py3_qt5:
- `compare_widget.py`, `database_widget.py`, `filter_widget.py`
- `nxs_widget.py`, `plot_dialog.py`, `point_picker_dialog.py`
- `polarization_dialog.py`, `quicklog_window.py`, `rawcompare_dialog.py`
- `reduce_dialog.py`, `smooth_dialog.py`, `gisans_dialog.py`
- `background_dialog.py`

### Agent Stream H: Entry Points

#### 4H.1 Fix `scripts/quicknxs`
- `from PyQt4.QtGui import QApplication, QPixmap` → `from qtpy.QtWidgets import QApplication; from qtpy.QtGui import QPixmap`
- Add `import os; os.environ["QT_API"] = "pyqt5"` at the top (before any Qt imports)
- Add `import matplotlib; matplotlib.use("Qt5Agg")` early
- Restore executable bit: `chmod +x`

#### 4H.2 Fix `scripts/quicklog`
- Same Qt import pattern
- Restore executable bit

#### 4H.3 Fix `scripts/nxsdialog`
- Same Qt import pattern
- Restore executable bit

**Gate:** `pixi run test-gui` passes - main_gui_test.py passes under Python 3 + Qt5.

---

## Phase 5: Integration & Polish

**Goal:** Final integration testing, cleanup, and documentation.
**Requires:** All previous phases complete.

### Tasks

#### 5.1 Full test suite verification
- `pixi run test` - all tests pass
- Manual smoke test: `pixi run python scripts/quicknxs` launches the GUI

#### 5.2 Revert hardcoded paths in `quicknxs/config/ref_m.py`
- The upstream branch changed `data_base` and `database_file` to local paths
- Restore to original `/SNS/REF_M` paths or make configurable

#### 5.3 Update `setup.py` or remove in favor of `pyproject.toml`
- If keeping for backward compat, fix Python 2 `print` statements
- Otherwise, delete and rely solely on pyproject.toml

#### 5.4 Clean up unused Python 2 artifacts
- Remove `#-*- coding: utf-8 -*-` (unnecessary in Python 3)
- Remove `from __future__` imports if any
- Remove `pyuic4` wrapper script (replaced by pyuic5)
- Update `compile_gui.sh` to use pyuic5/pyrcc5

#### 5.5 Git commit strategy
- One commit per phase for clarity
- Or one commit per logical unit (build infra, core migration, Qt migration, tests)
- Tag the final working state

**Gate:** Full test suite passes. Application launches under Python 3 + Qt5.

---

## Parallel Execution Map

```
Phase 0: Infrastructure (sequential, one agent)
    │
Phase 1: Import Chain Fix (sequential, one agent)
    │
    ├── Phase 2A: Core Science ──┐
    ├── Phase 2B: Supporting    ──┤
    ├── Phase 2C: Buzhug        ──┤── All parallel
    └── Phase 2D: Config        ──┘
         │
    Phase 3: Test Fix (one agent, after Phase 2)
         │
    ├── Phase 4E: Core GUI      ──┐
    ├── Phase 4F: Dialogs       ──┤── All parallel
    ├── Phase 4G: Generated UI  ──┤
    └── Phase 4H: Entry Points  ──┘
         │
    Phase 5: Integration (one agent)
```

**Recommended team size:** 2-3 agents
- Agent 1: Phases 0, 1, 2A, 3 (critical path)
- Agent 2: Phases 2B, 2C, 2D (parallel core work)
- Agent 3: Phases 4E, 4F, 4G, 4H (Qt migration, after Phase 1)

---

## Key Files Quick Reference

| File | Priority | Changes Needed |
|------|----------|----------------|
| `quicknxs/config/__init__.py` | CRITICAL | `exec`, `except` syntax |
| `quicknxs/decorators.py` | CRITICAL | `StringIO`, `func_code`, `getargspec` |
| `quicknxs/config/baseconfig.py` | CRITICAL | Python 2 syntax |
| `quicknxs/config/configobj.py` | HIGH | 87KB vendored, extensive Py2 |
| `quicknxs/mplwidget.py` | HIGH | Qt module misplacements, Py2 |
| `quicknxs/main_gui.py` | HIGH | Largest file, many patterns |
| `quicknxs/qreduce.py` | HIGH | Core science, test-backed |
| `quicknxs/qio.py` | HIGH | Heavy unicode usage |
| `quicknxs/mpfit.py` | MEDIUM | 115KB vendored fitting |
| `quicknxs/buzhug/*.py` | MEDIUM | Vendored DB package |
| `quicknxs/ipython_widget.py` | LOW | QtGui.QApplication fix |
| `scripts/*` | LOW | Entry point Qt imports |

## Verification Commands

```bash
# After Phase 0:
pixi install

# After Phase 1:
pixi run python -c "from quicknxs.config import ref_m; print('config OK')"
pixi run python -c "from quicknxs.decorators import log_call; print('decorators OK')"

# After Phase 2:
pixi run test-core

# After Phase 4:
pixi run test-gui
pixi run test

# After Phase 5:
pixi run python scripts/quicknxs  # smoke test GUI launch
```
