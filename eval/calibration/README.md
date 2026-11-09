# Judge calibration

[dev01.json](dev01.json) contains four synthetic responses: strong, mixed, weak,
and justified abstention. Their expected score ranges are provisional and have
not been checked by human reviewers. They are separate from the formal scenarios.

The file keeps response content in `candidates` and quality labels in
`reference_expectations`. The loader checks IDs, rubric versions, and score
ranges. `build_calibration_inputs` supplies only candidate content and the common
scenario context to the judge; it replaces candidate IDs with opaque sample IDs.

From `eval/`, run an offline check into a new output directory:

```sh
uv run --locked --offline python -m tradecopilot_eval calibrate \
  --output /tmp/tradecopilot-calibration
```

The default mode uses fixed scripted scores to test the pipeline. It makes no
model calls and reports those controls as unassessed. Use `--data` to choose a
calibration file and `--case` to choose its scenario directory. Run
`uv run --locked --offline python -m tradecopilot_eval calibrate --help`
for model settings and the explicit
model-call option. Model calls require provider credentials and may incur costs.

Before treating the ranges as calibration labels:

1. Have reviewers score the responses without seeing the expected ranges or
   judge scores.
2. Discuss disagreements and revise the ranges or rubric on these development
   cases. Keep the original reviews and record each revision.
3. Freeze the rubric and prompt before the formal comparison.

The comparison retains missing runs and judge errors. A model score outside a
provisional range calls for review; it does not by itself prove that the judge
is wrong. Formal outputs use the separate human-review CSV and agreement tools.
