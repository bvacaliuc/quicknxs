# Fix OOM crash 

On certain limited memory machines, an out of memory error leads to a SIGKILL.
A reduction with all options selected in the ReduceDialog was executed, but did not complete successfully.
An strace output file was captured using the command 'strace pixi run python scripts/quicknxs 2>strace.dat'.
Read strace.dat to understand the behavior of the application leading up to the error.
In the debug.log file, the last entry was:
```
[INFO] - 2026-02-14 21:10:30,832 - gui_utils.py:97:execute Extracting corrected off-specular data...
                                                                                                                                                             ```
