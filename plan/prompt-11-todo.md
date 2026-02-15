# Fix several errors

There are several errors that need attention.

## Fix error in plotting

This error is obtained in reduction after off specular data is written out to the result folder:
```
[INFO] - 2026-02-14 17:00:22,958 - gui_logging.py:115:setup_system *** QuickNXS 1.1.6 feature/pixi_py3_qt5 Logging started ***
[INFO] - 2026-02-14 17:00:31,063 - main_gui.py:1293:loadExtraction Reloading data from information in file header...
[INFO] - 2026-02-14 17:00:31,065 - qio.py:494:_get_dataset Reading /SNS/REF_M/IPTS-15829/data/REF_M_23737_histo.nxs
[INFO] - 2026-02-14 17:00:31,550 - qio.py:494:_get_dataset Reading /SNS/REF_M/IPTS-15829/data/REF_M_23738_histo.nxs
[INFO] - 2026-02-14 17:00:31,995 - qio.py:494:_get_dataset Reading /SNS/REF_M/IPTS-15829/data/REF_M_23739_histo.nxs
[INFO] - 2026-02-14 17:00:32,428 - qio.py:494:_get_dataset Reading /SNS/REF_M/IPTS-15829/data/REF_M_23740_histo.nxs
[INFO] - 2026-02-14 17:00:33,341 - qio.py:494:_get_dataset Reading /SNS/REF_M/IPTS-15829/data/REF_M_23741_histo.nxs
[INFO] - 2026-02-14 17:00:34,263 - qio.py:494:_get_dataset Reading /SNS/REF_M/IPTS-15829/data/REF_M_23742_histo.nxs
[INFO] - 2026-02-14 17:00:35,281 - qio.py:494:_get_dataset Reading /SNS/REF_M/IPTS-15829/data/REF_M_23743_histo.nxs
[INFO] - 2026-02-14 17:00:36,340 - qio.py:494:_get_dataset Reading /SNS/REF_M/IPTS-15829/data/REF_M_23744_histo.nxs
[INFO] - 2026-02-14 17:00:37,361 - qio.py:494:_get_dataset Reading /SNS/REF_M/IPTS-15829/data/REF_M_23745_histo.nxs
[INFO] - 2026-02-14 17:00:38,545 - qio.py:494:_get_dataset Reading /SNS/REF_M/IPTS-15829/data/REF_M_23746_histo.nxs
[INFO] - 2026-02-14 17:00:39,711 - main_gui.py:1295:loadExtraction Data loaded
[INFO] - 2026-02-14 17:00:39,717 - main_gui.py:355:fileOpen Reading file /SNS/REF_M/IPTS-15829/data/REF_M_23746_histo.nxs...
[INFO] - 2026-02-14 17:00:39,717 - main_gui.py:412:_fileOpenDone /SNS/REF_M/IPTS-15829/data/REF_M_23746_histo.nxs loaded
[INFO] - 2026-02-14 17:00:57,464 - gui_utils.py:91:execute Extracting reflectivity...
[INFO] - 2026-02-14 17:00:58,875 - gui_utils.py:94:execute Extracting off-specular data...
[INFO] - 2026-02-14 17:01:00,286 - gui_utils.py:97:execute Extracting corrected off-specular data...
[INFO] - 2026-02-14 17:02:51,598 - gui_utils.py:128:execute Plotting...
[CRITICAL] - 2026-02-14 17:02:51,682 - gui_logging.py:39:excepthook_overwrite python error
Traceback (most recent call last):
  File "<string>", line 1, in <lambda>
  File "/SNS/users/6ov/QuickNXSv1/QuickNXS/quicknxs/decorators.py", line 154, in log_call
    if logging.root.getEffectiveLevel()>logging.DEBUG: return func(*args, **kw)
                                                              ^^^^^^^^^^^^^^^^^
  File "/SNS/users/6ov/QuickNXSv1/QuickNXS/quicknxs/main_gui.py", line 1965, in reduceDatasets
    dialog.exec_()
  File "<string>", line 1, in <lambda>
  File "/SNS/users/6ov/QuickNXSv1/QuickNXS/quicknxs/decorators.py", line 154, in log_call
    if logging.root.getEffectiveLevel()>logging.DEBUG: return func(*args, **kw)
                                                              ^^^^^^^^^^^^^^^^^
  File "/SNS/users/6ov/QuickNXSv1/QuickNXS/quicknxs/gui_utils.py", line 477, in exec_
    self.execute()
  File "/SNS/users/6ov/QuickNXSv1/QuickNXS/quicknxs/gui_utils.py", line 130, in execute
    self.plot_result(output_data, title)
  File "<string>", line 1, in <lambda>
  File "/SNS/users/6ov/QuickNXSv1/QuickNXS/quicknxs/decorators.py", line 154, in log_call
    if logging.root.getEffectiveLevel()>logging.DEBUG: return func(*args, **kw)
                                                              ^^^^^^^^^^^^^^^^^
  File "/SNS/users/6ov/QuickNXSv1/QuickNXS/quicknxs/gui_utils.py", line 280, in plot_result
    dialog=PlotDialog()
           ^^^^^^^^^^^^
  File "/SNS/users/6ov/QuickNXSv1/QuickNXS/quicknxs/gui_utils.py", line 555, in __init__
    self.plot.toolbar.labelAction.setVisible(True)
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AttributeError: 'NavigationToolbar' object has no attribute 'labelAction'
```

##  Fix error in File->Load Extraction...

In the UI, when 'File->Load Extraction...' is selected the program hangs and must be terminated.  The ~/.quicknxs/debug.log contains:
```
[INFO] - 2026-02-14 20:07:40,375 - main_gui.py:1293:loadExtraction Reloading data from information in file header...
[INFO] - 2026-02-14 20:07:40,375 - main_gui.py:1295:loadExtraction Data loaded
[INFO] - 2026-02-14 20:07:40,376 - main_gui.py:1297:loadExtraction No datasets found in header to restore.
```

## Fix error in Advanced->IPython Console

In the UI, when 'Advanced->IPython Console' is selected, a message is printed that:
```
[INFO] - 2026-02-14 20:08:10,251 - main_gui.py:228:run_ipython Start IPython console
[INFO] - 2026-02-14 20:08:10,253 - main_gui.py:232:run_ipython IPython is not installed, cannot open console.
```

## Fix error in 'Tools->Filter Points...'

In the UI, when 'Tools->Filter Points...' is selected, a dialog opens to select a '.dat' file. If the dialog is cancelled without selecting a file, this error is emitted:
```
[CRITICAL] - 2026-02-14 20:13:09,700 - gui_logging.py:39:excepthook_overwrite python error
Traceback (most recent call last):
  File "<string>", line 1, in <lambda>
  File "/SNS/users/6ov/QuickNXSv1/QuickNXS/quicknxs/decorators.py", line 154, in log_call
    if logging.root.getEffectiveLevel()>logging.DEBUG: return func(*args, **kw)
                                                              ^^^^^^^^^^^^^^^^^
  File "/SNS/users/6ov/QuickNXSv1/QuickNXS/quicknxs/main_gui.py", line 2443, in open_filter_dialog
    text=open(name, 'rb').read().decode('utf8')
         ^^^^^^^^^^^^^^^^
TypeError: expected str, bytes or os.PathLike object, not list
```
