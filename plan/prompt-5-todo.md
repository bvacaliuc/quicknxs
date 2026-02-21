# fix several GUI menu item faults

## Fault 1

This error occurs after loading run 25879 and typing a 6 into the X width box in the Reduction Parameters (Basic) section:
```
[INFO] - 2026-02-13 05:27:56,114 - gui_logging.py:115:setup_system *** QuickNXS 1.1.6 feature/pixi_py3_qt5 Logging started ***
[INFO] - 2026-02-13 05:28:06,665 - main_gui.py:1228:openByNumber Trying to locate file number 25879...
[INFO] - 2026-02-13 05:28:06,702 - main_gui.py:351:fileOpen Reading file /SNS/REF_M/IPTS-16196/data/REF_M_25879_histo.nxs...
[INFO] - 2026-02-13 05:28:07,689 - main_gui.py:408:_fileOpenDone /SNS/REF_M/IPTS-16196/data/REF_M_25879_histo.nxs loaded
[CRITICAL] - 2026-02-13 05:28:24,938 - gui_logging.py:39:excepthook_overwrite python error
Traceback (most recent call last):
  File "/home/bvacaliuc/Projects/Claude/quicknxsv1/quicknxs/gui_utils.py", line 1076, in run
    for name, items in self.actions.items():
                       ^^^^^^^^^^^^^^^^^^^^
RuntimeError: dictionary changed size during iteration
```

This fault is critical because it causes the entire application to exit.

## Fault 2

This fault occurs when restarting the UI after an earlier fault. The user is asked if they choose to re-load the previous analysis state. If the user answers Yes, this fault occurs and the previous state is not loaded:

```
[INFO] - 2026-02-13 05:09:50,915 - gui_logging.py:115:setup_system *** QuickNXS 1.1.6 feature/pixi_py3_qt5 Logging started ***
[WARNING] - 2026-02-13 05:10:00,318 - main_gui.py:1286:loadExtraction Could not evaluate header information, probably the wrong format:

Traceback (most recent call last):
  File "/SNS/users/6ov/QuickNXSv1/QuickNXS/quicknxs/main_gui.py", line 1284, in loadExtraction
    parser=HeaderParser(header, parse_meta=not from_backup)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/SNS/users/6ov/QuickNXSv1/QuickNXS/quicknxs/qio.py", line 370, in __init__
    self._evaluate()
  File "/SNS/users/6ov/QuickNXSv1/QuickNXS/quicknxs/qio.py", line 459, in _evaluate
    self.section_data['Direct Beam Runs']=self._evaluate_section('Direct Beam Runs',
                                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/SNS/users/6ov/QuickNXSv1/QuickNXS/quicknxs/qio.py", line 428, in _evaluate_section
    sitems=[item.strip() for item in self.sections[section][0].split(u'  ') if item.strip()!=u'']
                                     ~~~~~~~~~~~~~^^^^^^^^^
KeyError: 'Direct Beam Runs'
```

The expected and desired effect of loading the previous state is to return to the same file and parameter settings that were in effect prior to the fault.

## Fault 3

This error occurs when selecting Advanced->IPython Console from the menu bar:
```
[INFO] - 2026-02-13 05:10:46,397 - main_gui.py:228:run_ipython Start IPython console
[CRITICAL] - 2026-02-13 05:10:46,407 - gui_logging.py:39:excepthook_overwrite python error
Traceback (most recent call last):
  File "/SNS/users/6ov/QuickNXSv1/QuickNXS/quicknxs/main_gui.py", line 229, in run_ipython
    from .ipython_widget import IPythonConsoleQtWidget
  File "/SNS/users/6ov/QuickNXSv1/QuickNXS/quicknxs/ipython_widget.py", line 15, in <module>
    import IPython
ModuleNotFoundError: No module named 'IPython'
```

## Fault 4

This error occurs when selecting Help->About... from the menu bar:
```
[CRITICAL] - 2026-02-13 05:11:22,666 - gui_logging.py:39:excepthook_overwrite python error
Traceback (most recent call last):
  File "/SNS/users/6ov/QuickNXSv1/QuickNXS/quicknxs/main_gui.py", line 2484, in helpDialog
    webview=QtWebKit.QWebView(dia)
            ^^^^^^^^^^^^^^^^^
AttributeError: 'NoneType' object has no attribute 'QWebView'
[CRITICAL] - 2026-02-13 05:11:32,440 - gui_logging.py:39:excepthook_overwrite python error
Traceback (most recent call last):
  File "/SNS/users/6ov/QuickNXSv1/QuickNXS/quicknxs/main_gui.py", line 2522, in aboutDialog
    QtCore.QT_VERSION_STR, pyqtversion, h5pyversion, hdf5version))
    ^^^^^^^^^^^^^^^^^^^^^
AttributeError: module 'qtpy.QtCore' has no attribute 'QT_VERSION_STR'. Did you mean: 'PYQT_VERSION_STR'?
[INFO] - 2026-02-13 05:12:26,059 - gui_logging.py:45:goodby *** QuickNXS 1.1.6 feature/pixi_py3_qt5 Logging ended ***
```

