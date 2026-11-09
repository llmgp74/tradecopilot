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
