# Eval run archive

One directory per recorded run, named by the report generation timestamp in
ISO form with the UTC offset, for example `2026-11-20T0755+0800`. Each
directory holds the generated report, the raw run table, the plan, and a
README with the headline numbers and provenance.

Costs stay unmeasured unless the provider returns pricing. `unscored
(missing)` cells are missing, not zero.

- [2026-11-20T0755+0800](2026-11-20T0755+0800/README.md): full pilot suite,
  deepseek-flash agent, qwen3.7-flash judge, 46 of 46 runs. Tree changed
  mid-run, so 1 of 27 paired comparisons is invalid.
- [2026-11-20T1008+0800](2026-11-20T1008+0800/README.md): full pilot suite on
  `main`, one code hash across all 46 runs, 27 of 27 pairs valid. Task
  success: full 8/9, structured 7/9, prose 6/9, none 1/9; screening 8/10.
