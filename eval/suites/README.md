# Pilot comparison plan

[pilot.json](pilot.json) fixes the scenario selection before a model run:

- Run all ten cases once with full memory.
- Run PORT-01, NEWS-01, and PORT-02 three times under each of the four memory
  conditions. They cover constraints, changed preferences, and earlier decisions.

This gives 10 screening runs and 36 comparison runs, for 46 agent runs in total.
The screening runs are separate from the repeated comparison. Judge calls and
any invalid-output retry are additional calls.

The plan uses seed 74 and keeps the same scenario inputs for every condition.
It contains synthetic cases pending reference review. Offline rehearsals check
the workflow; they cannot establish which memory condition performs better.

[source-pilot.json](source-pilot.json) is a separate two-case development smoke
suite using archived issuer evidence and assumed user context. It runs each case
once with full memory and has no ablation trials. Its archives must be supplied
through `--evidence-root`; the references remain pending human review. It does
not replace the ten-case plan or turn synthetic results into sourced experiments.
