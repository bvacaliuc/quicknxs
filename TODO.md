# Fix error on using ReduceDialog()

This error occurs in the GUI when attempting after restoring state, then pressing Reduce:
```
[INFO] - 2026-02-13 15:59:10,420 - gui_logging.py:115:setup_system *** QuickNXS 1.1.6 feature/pixi_py3_qt5 Logging started ***
[INFO] - 2026-02-13 15:59:22,318 - main_gui.py:1293:loadExtraction Reloading data from information in file header...
[INFO] - 2026-02-13 15:59:22,320 - qio.py:494:_get_dataset Reading /SNS/REF_M/IPTS-15829/data/REF_M_23737_histo.nxs
[INFO] - 2026-02-13 15:59:22,793 - qio.py:494:_get_dataset Reading /SNS/REF_M/IPTS-15829/data/REF_M_23738_histo.nxs
[INFO] - 2026-02-13 15:59:23,221 - qio.py:494:_get_dataset Reading /SNS/REF_M/IPTS-15829/data/REF_M_23739_histo.nxs
[INFO] - 2026-02-13 15:59:23,654 - qio.py:494:_get_dataset Reading /SNS/REF_M/IPTS-15829/data/REF_M_23740_histo.nxs
[INFO] - 2026-02-13 15:59:24,576 - qio.py:494:_get_dataset Reading /SNS/REF_M/IPTS-15829/data/REF_M_23741_histo.nxs
[INFO] - 2026-02-13 15:59:25,501 - qio.py:494:_get_dataset Reading /SNS/REF_M/IPTS-15829/data/REF_M_23742_histo.nxs
[INFO] - 2026-02-13 15:59:26,485 - qio.py:494:_get_dataset Reading /SNS/REF_M/IPTS-15829/data/REF_M_23743_histo.nxs
[INFO] - 2026-02-13 15:59:27,449 - qio.py:494:_get_dataset Reading /SNS/REF_M/IPTS-15829/data/REF_M_23744_histo.nxs
[INFO] - 2026-02-13 15:59:28,466 - qio.py:494:_get_dataset Reading /SNS/REF_M/IPTS-15829/data/REF_M_23745_histo.nxs
[INFO] - 2026-02-13 15:59:29,522 - qio.py:494:_get_dataset Reading /SNS/REF_M/IPTS-15829/data/REF_M_23746_histo.nxs
[INFO] - 2026-02-13 15:59:30,615 - main_gui.py:1295:loadExtraction Data loaded
[INFO] - 2026-02-13 15:59:30,623 - main_gui.py:355:fileOpen Reading file /SNS/REF_M/IPTS-15829/data/REF_M_23746_histo.nxs...
[INFO] - 2026-02-13 15:59:30,623 - main_gui.py:412:_fileOpenDone /SNS/REF_M/IPTS-15829/data/REF_M_23746_histo.nxs loaded
[CRITICAL] - 2026-02-14 10:10:39,230 - gui_logging.py:39:excepthook_overwrite python error
Traceback (most recent call last):
  File "<string>", line 1, in <lambda>
  File "/SNS/users/6ov/QuickNXSv1/QuickNXS/quicknxs/decorators.py", line 154, in log_call
    if logging.root.getEffectiveLevel()>logging.DEBUG: return func(*args, **kw)
                                                              ^^^^^^^^^^^^^^^^^
  File "/SNS/users/6ov/QuickNXSv1/QuickNXS/quicknxs/main_gui.py", line 1964, in reduceDatasets
    dialog=ReduceDialog(self, self.ref_list_channels, self.reduction_list)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
TypeError: ReduceDialog.__init__() takes 3 positional arguments but 4 were given
```
