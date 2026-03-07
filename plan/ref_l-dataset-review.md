```
  Summary of REF_L Analysis
                                                                                                                                                             
  The REF_L dataset analysis reveals a much cleaner transition than REF_M, with three notable findings that impacted the plan:
                                                                                                                                                             
  1. No missing-metadata problem                                                                                                                           
                                               
  All REF_L .nxs.h5 files — from the earliest (run 133969, Dec 2015) to the most recent (run 225235, 2025) — have complete metadata (LambdaRequest, thi,
  ths). No fallback defaults needed for REF_L, unlike the REF_M commissioning runs.

  2. Minimal format overlap

  Only 25 runs exist in both formats, always in different IPTS directories (e.g., histo in IPTS-11021, h5 in IPTS-8090). The overlapping h5 files are empty
  (0 events) — likely DAS restart artifacts. ~250 IPTS have only .nxs.h5 files, making our new reader essential for accessing the majority of REF_L data.

  3. Distances must NOT be hardcoded (plan updated)

  This is the most significant finding. The instrument geometry changed between IDF versions:

  ┌─────────────┬────────────────────────┬───────────────────┐
  │  Parameter  │        2014 IDF        │     2024 IDF      │
  ├─────────────┼────────────────────────┼───────────────────┤
  │ Moderator z │ -13.63 m               │ -13.685 m         │
  ├─────────────┼────────────────────────┼───────────────────┤
  │ Detector z  │ 0.00035 m              │ 1.362 m           │
  ├─────────────┼────────────────────────┼───────────────────┤
  │ IDF format  │ Tube-based (256 tubes) │ Rectangular panel │
  └─────────────┴────────────────────────┴───────────────────┘

  I updated the plan to:
  - Add _get_distances_from_xml() helper that parses moderator and detector positions from the embedded instrument XML
  - Use this for both REF_L and REF_M (REF_M falls back to DASlogs first, then XML)
  - Add TDD test TestGetDistancesFromXml with both instruments
  - Add REF_L test file /SNS/REF_L/IPTS-14316/nexus/REF_L_138523.nxs.h5 (2016, tube-based IDF) to verify distance parsing works across IDF eras

  The plan is now validated against the complete datasets of both instruments and ready for implementation.
```
