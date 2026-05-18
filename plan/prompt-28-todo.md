# fix several runtime faults

## Fault 1

After loading 44033, 44034, 44035 (as direct beam) then 44159, 44160, 44161 (as reflectivity), I observed "gaps" in the reflectivity. See [prompt-28-overview.png](prompt-28-overview.png). This is especially promiment in [prompt-28-offspec.png](prompt-28-offspec.png). I suspect this may have something to do with a mistake in interpreting the data as 60Hz when it is in fact 30Hz (for which the TOF range is 33.34ms, not 16.67ms). Please investigate thoroughly how event mode data is categorized and how das logs are interpreted.

## Fault 2

This error occurred after loading run 44161, adding it to the data runs and clicking on the DASLogs tab.

```
└─$ make gui                   
pixi install
✔ The default environment has been installed in '/home/bvacaliuc/.cache/rattler/cache/envs'.
pixi run python scripts/quicknxs --instrument ref_m
/home/bvacaliuc/Projects/Claude/1/quicknxsv1/quicknxs/mplwidget.py:380: UserWarning: No artists with labels found to put in legend.  Note that artists whose label start with an underscore are ignored when legend() is called with no argument.
  return self.canvas.ax.legend(*args, **opts)
CRITICAL: python error
Traceback (most recent call last):
  File "<string>", line 1, in <lambda>
  File "/home/bvacaliuc/Projects/Claude/1/quicknxsv1/quicknxs/decorators.py", line 155, in log_call
    return func(*args, **kw)
           ^^^^^^^^^^^^^^^^^
  File "/home/bvacaliuc/Projects/Claude/1/quicknxsv1/quicknxs/main_gui.py", line 531, in plotActiveTab
    self.update_daslog()
  File "<string>", line 1, in <lambda>
  File "/home/bvacaliuc/Projects/Claude/1/quicknxsv1/quicknxs/decorators.py", line 155, in log_call
    return func(*args, **kw)
           ^^^^^^^^^^^^^^^^^
  File "/home/bvacaliuc/Projects/Claude/1/quicknxsv1/quicknxs/main_gui.py", line 1206, in update_daslog
    item=QtWidgets.QTableWidgetItem(u'%g'%data.logs[key])
                                    ~~~~~^~~~~~~~~~~~~~~
TypeError: only 0-dimensional arrays can be converted to Python scalars
make: *** [Makefile:6: gui] Error 137
```

## Fault 3

After 'Fault 2' above, the GUI exited. In looking at the ~/.quicknxs/run_state.dat file, I observe that it is missing 44035 and 44161, the last direct beam and reflectivity files I loaded, respectively. As you can see from [prompt-28-overview.png](prompt-28-overview.png), I *did in fact add those to the table*. The ~/.quicknxs/debug.log captures the loading of the runs. Why did the run_state.dat file not capture this condition? Please do a thorough investigation.

I believe that the correct run_state.dat should contain (DB_ID 3 and a 3rd run number):

```
Running PID 467451
Datafile created by QuickNXS 1.3.0.dev49
Date: 2026-05-17 22:53:24
Type: %(datatype)s
Input file indices: %(indices)s
Extracted states: %(states)s

[Direct Beam Runs]
DB_ID  P0  PN  x_pos   x_width  y_pos  y_width  bg_pos  bg_width  dpix  tth           number  File                                          
1      0   0   227     12       136    100      30      20        226   -0.000933812  44033   /SNS/REF_M/IPTS-34473/nexus/REF_M_44033.nxs.h5
2      0   0   228.5   16       136    100      30      20        226   -0.000933812  44034   /SNS/REF_M/IPTS-34473/nexus/REF_M_44034.nxs.h5
3      0   0   230.5   24       134    100      30      20        226   ????????????  44035   /SNS/REF_M/IPTS-34473/nexus/REF_M_44035.nxs.h5

[Data Runs]
scale     P0  PN   x_pos   x_width  y_pos  y_width  bg_pos  bg_width  extract_fan  dpix  tth        number  DB_ID  File                                          
2.25424   4   15   172.3   17       137    55       30      20        False        168   0.997078   44159   1      /SNS/REF_M/IPTS-34473/nexus/REF_M_44159.nxs.h5
2.25424   4   15   172     17       137    55       30      20        False        168   2.32963    44160   2      /SNS/REF_M/IPTS-34473/nexus/REF_M_44160.nxs.h5
2.0808    1   2    173.3   17       137    55       30      20        False        168   5.62792    44161   3      /SNS/REF_M/IPTS-34473/nexus/REF_M_44161.nxs.h5

[Global Options]
name           value
sample_length  10   
```
