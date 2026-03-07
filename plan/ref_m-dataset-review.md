```
  Summary of Findings
                                                                                                                                                             
  My earlier assessment that the format transition was a "clean break" was wrong. Exploring the complete REF_M dataset reveals:
                                                                                                                                                             
  Corrected picture                                                                                                                                        
                                                                               
  ┌──────────────────┬──────────────────────────────────┬───────────────────────────────────────────────────────────────────────────────────────────────┐
  │     Finding      │          Old Assessment          │                                           Corrected                                           │
  ├──────────────────┼──────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Format overlap   │ Zero overlap (based on           │ 42 IPTS have both formats, many with complete overlap                                         │
  │                  │ IPTS-16196 only)                 │                                                                                               │
  ├──────────────────┼──────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Overlap zone     │ N/A                              │ Runs ~29732–34727+ (most of 2018–2019 production data)                                        │
  ├──────────────────┼──────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Polarization in  │ Mentioned as limitation          │ Confirmed critical: polarized runs exist in overlap zone (e.g., run 29742 has 3 states in     │
  │ h5               │                                  │ histo, single entry in h5)                                                                    │
  ├──────────────────┼──────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Missing metadata │ "Common" for early h5 files      │ Isolated: only IPTS-16196 commissioning runs (29001–29016); all production h5 files have full │
  │                  │                                  │  metadata                                                                                     │
  └──────────────────┴──────────────────────────────────┴───────────────────────────────────────────────────────────────────────────────────────────────┘

  Impact on the plan

  Three significant updates:

  1. locate_file() must prefer histo: When both formats exist for a run (very common in the overlap era), histo files must be returned first because they
  preserve polarization channel separation. This is now documented and tested.
  2. Cross-validation test added: The overlap zone provides ground-truth — we can bin .nxs.h5 events and compare pixel-by-pixel against the pre-histogrammed
  data. Run 29750 validated at 0.999992 correlation. This is now a TDD test (Step 3.3).
  3. Phase 8 (future work) added: Event-level polarization filtering using DASlogs/PolarizerState time-series, with validation against the 70 overlap runs in
   IPTS-9801.

  The plan has been updated accordingly. You can mount REF_L next if you'd like me to perform the same analysis there before we begin implementation.

✻ Churned for 25m 8s · 1 background task still running (↓ to manage)

● Background command "Check run ranges for key IPTS with both formats" completed (exit code 0)

● Background command "Check for old event.nxs with polarization" completed (exit code 0)

● The earlier background tasks completed. Let me check if the slow directory listing produced any additional useful data.

● Read 1 file (ctrl+o to expand)                                                                                                                             
                                                                              
● This confirms: IPTS-16196 has a gap (histo ends 25899, h5 starts 29001), but IPTS-20508 and IPTS-20736 have complete overlap (identical run ranges in both 
  formats). The slight count difference in IPTS-20736 (134 histo vs 135 h5) suggests one run exists only as h5.                                            
                                                                                                                                                             
● Read 1 file (ctrl+o to expand)                                                                                                                             
                                                                                                                                                             
● Good — old _event.nxs files exist too. Runs 29779 and 29793 are in the overlap zone, meaning some runs have three representations: _histo.nxs, _event.nxs, 
  and .nxs.h5. This further confirms that locate_file() correctly preferring histo format is the right strategy.                                             
                                                                               
  These results are consistent with everything already captured in the updated plan. No further plan changes needed. The plan at plan/read-event-nexus-h5.md 
  is ready for implementation.
                                                                                                                                                             
● Background command "Find IPTS with only h5 files (no histo)" completed (exit code 0)                                                                       
                                                                               
● Read 1 file (ctrl+o to expand)                                                                                                                             
                                                                                                                                                           
● This is very informative. 119 IPTS directories have only .nxs.h5 files (no histo counterpart). These are the experiments where our new code will be the    
  only way to access the data in quicknxsv1. The earliest h5-only IPTS start at run ~35523, while the overlap zone extends up to at least run ~34727. So the
  picture is:                                                                                                                                                
                                                                                                                                                             
  ┌───────────────┬─────────────────────────────────────────────────────────────┐
  │   Run range   │                     Format availability                     │                                                                            
  ├───────────────┼─────────────────────────────────────────────────────────────┤                                                                          
  │ ≤ ~28832      │ Histo only                                                  │
  ├───────────────┼─────────────────────────────────────────────────────────────┤
  │ ~29001–~29731 │ H5 only (IPTS-16196 commissioning — no wavelength metadata) │
  ├───────────────┼─────────────────────────────────────────────────────────────┤
  │ ~29732–~34727 │ Both histo and h5 (overlap era)                             │
  ├───────────────┼─────────────────────────────────────────────────────────────┤
  │ ~35523+       │ H5 only (119 IPTS, production data with full metadata)      │
  └───────────────┴─────────────────────────────────────────────────────────────┘

  This confirms the plan is correct: locate_file() preferring histo when available handles the overlap zone, and the h5 reader is essential for the 119
  h5-only experiments (runs ~35523+). No further plan updates needed — all of this is already well-covered.
```

