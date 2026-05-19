# Investigate reduce_offspec_headless.py failure

A new script developed for quicknxs (v2) runs for a while but hangs and then is stopped with a KeyboardInterrupt.

## Fault 1

Is this a real fault or was the user just impatient?

```
6ov@uvdl3:/media/ssd2/Projects/Claude/2/quicknxsv1$ pixi run python scripts/reduce_offspec_headless.py --recipe /media/ssd2/shared/REF_M/11486/correctReduction/REF_M_44159+44160+44161_peak1_OffSpecSmooth_Off_Off.dat --channel Off_Off --db-mode paired --bins 400 --out /tmp/REF_M_44159+44160+44161_peak1_OffSpecSmooth_Off_Off.dat
Parsing recipe: /media/ssd2/shared/REF_M/11486/correctReduction/REF_M_44159+44160+44161_peak1_OffSpecSmooth_Off_Off.dat
  app/version:   ('QuickNXS', '4.3.0rc1')
  direct beams:  [44033, 44034, 44035]
  data runs:     [44159, 44160, 44161]
  smooth grid:   nx=563, ny=1000, x=[-0.1140,0.0859], y=[-0.1000,0.3758]

DB assignment (paired):
  data 44159 -> DB[0]=44033  (header DB_ID was 1)
  data 44160 -> DB[1]=44034  (header DB_ID was 1)
  data 44161 -> DB[2]=44035  (header DB_ID was 1)

Reducing channel=Off_Off, bins=400...
  loading REF_M_44033.nxs.h5 (bins=400)...
  loading REF_M_44034.nxs.h5 (bins=400)...
  loading REF_M_44035.nxs.h5 (bins=400)...
  loading REF_M_44159.nxs.h5 (bins=400)...
  loading REF_M_44160.nxs.h5 (bins=400)...
  loading REF_M_44161.nxs.h5 (bins=400)...
  DB 44033 (index 0): Rraw mean = 1.997e-11
  DB 44034 (index 1): Rraw mean = 1.228e-11
  DB 44035 (index 2): Rraw mean = 1.084e-11
  DR 44159 via DB[0]=44033: Qz=[-0.0702,0.1985], I=[-3.846e-03,2.557e+01]
  DR 44160 via DB[1]=44034: Qz=[-0.0026,0.2661], I=[-1.010e-02,5.120e-01]
  DR 44161 via DB[2]=44035: Qz=[0.0420,0.4345], I=[-9.920e-03,1.927e+00]

Smoothing...
/media/ssd2/Projects/Claude/2/quicknxsv1/quicknxs/qcalc.py:294: RuntimeWarning: overflow encountered in exp
  Pij=exp(-0.5*rij[take])
/media/ssd2/Projects/Claude/2/quicknxsv1/quicknxs/qcalc.py:295: RuntimeWarning: invalid value encountered in divide
  Pij/=Pij.sum()
/home/6ov/.cache/rattler/cache/envs/quicknxs-v1-7472859153360732580/envs/default/lib/python3.12/site-packages/numpy/_core/_methods.py:49: RuntimeWarning: overflow encountered in reduce
  return umr_sum(a, axis, dtype, out, keepdims, initial, where)




^CTraceback (most recent call last):
  File "/media/ssd2/Projects/Claude/2/quicknxsv1/scripts/reduce_offspec_headless.py", line 520, in <module>
    sys.exit(main())
             ^^^^^^
  File "/media/ssd2/Projects/Claude/2/quicknxsv1/scripts/reduce_offspec_headless.py", line 508, in main
    x, y, I = smooth_pieces(pieces, g,  # noqa: E741
              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/media/ssd2/Projects/Claude/2/quicknxsv1/scripts/reduce_offspec_headless.py", line 365, in smooth_pieces
    xout, yout, Iout = smooth_data(settings, x, y, I,
                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<string>", line 1, in <lambda>
  File "/media/ssd2/Projects/Claude/2/quicknxsv1/quicknxs/decorators.py", line 171, in log_input
    return func(*args, **kw)
           ^^^^^^^^^^^^^^^^^
  File "/media/ssd2/Projects/Claude/2/quicknxsv1/quicknxs/qcalc.py", line 291, in smooth_data
    take=where(rij<sigmas**2) # take points up to 3 sigma distance
         ^^^^^^^^^^^^^^^^^^^^
  File "/home/6ov/.cache/rattler/cache/envs/quicknxs-v1-7472859153360732580/envs/default/lib/python3.12/site-packages/numpy/_core/multiarray.py", line 403, in where
    @array_function_from_c_func_and_dispatcher(_multiarray_umath.where)
    
KeyboardInterrupt
6ov@uvdl3:/media/ssd2/Projects/Claude/2/quicknxsv1$ 
```
