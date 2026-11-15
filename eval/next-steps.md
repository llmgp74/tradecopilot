# Evaluation work plan

The runner and judge implementation is on main. The tests and scripted rehearsal
check software behavior. Real-model experiments, complete source collection, and human
review are still pending. This plan follows the dataset and evaluation sections
of [the proposal](../proposal/main.tex).

Evidence collection, implementation, and development model checks can proceed
while human review is pending. Model calls still require explicit opt-in. Keep
reference labels and calibration expectations provisional until reviewed. The
proposal's human audit covers 20% of formal outputs plus disputed cases; it does
not require two reviewers to finish four examples before development continues.

## 1. Check the current cases and prepare review materials

Run the reference checks on both development cases and the ten pilot cases.
Check amounts, percentages, factual labels, timestamps, and whether each response
criterion can be judged from the final answer. Keep trace checks separate.

From `eval/`, export a new local review directory:

```sh
uv run --locked --offline python -m tradecopilot_eval reference-review \
  --output /tmp/tradecopilot-reference-review
```

The export includes case summaries, exact input/reference snapshots, file hashes,
and blank reference-review forms. The four calibration responses have a separate
blind packet. Expected scores and candidate labels stay in `private/`.

Completion means the files are reproducible, numerical mismatches are reported,
blind forms contain no expected scores, and all human fields remain blank.
Exporting the files does not approve the labels or establish judge accuracy.

## 2. Collect and review real evidence

Start with one earnings case and one news case. For each fact, save the source
URL, the exact excerpt or record, the publication/availability time, the retrieval
time, and a content hash. Check the filing period, units, and company identity.
Only information available by the decision time may enter the scenario.

Two [source development cases](scenarios/source_pilot/README.md) now archive an
Apple earnings release and Google's Wiz announcement. The loader checks their
provenance, source hashes, and time boundaries. They still lack historical prices
and independently reviewed references. Keep invented user profiles and portfolio
assumptions separate from company and market facts. No broker account is needed
for frozen replay.

Arrange a review of facts, arithmetic, acceptable outcomes, and response criteria
before freezing the study. Another team member can provide an independent check.
Preserve each reviewer's name, date, notes, and the hashes they reviewed.
Correct disagreements before marking a case reviewed. Extend to all ten cases
with the proposal's six ordinary and four adversarial categories. Fix the memory
comparison subset before seeing model outputs.

Completion means every included factual reference has an archived source, a
valid availability time, and a recorded review; synthetic cases remain labeled.

## 3. Review the rubric and calibrate the judge

The four development responses can help check the rubric. An optional preparation
exercise is to ask two reviewers to score all four independently. This is a
suggested sample, not a proposal requirement or a prerequisite for model checks.
Each reviewer gets only `calibration/blind/` from the export. Record five dimension
scores and reasons, outcome, and criterion decisions. Save original forms before
showing provisional expectations. Record the actual number of reviewers.

Discuss disagreements after independent forms are saved. Confirm how sizing advice,
waiting, clarification, and refusal are classified. Revise anchors or wording on
development examples only, retain the old version, and record each decision.
The four examples help refine the rubric; they do not establish judge reliability.

Once model calls and a budget are agreed, run the separate-family judge on those
development responses, even if human reviews are still pending. AI scores can
help find ambiguous criteria, but cannot count as human ratings. When independent
reviews are available, compare scores and inspect large disagreements rather
than adjusting labels to match the judge. Freeze the rubric, prompt, and
calibration version before the formal comparison.

Completion means outcome definitions and anchors are documented, original human
ratings are retained, and unresolved differences are listed explicitly.

## 4. Run a small real-model integration check

Record exact agent/judge model IDs, different families, settings, per-run limits,
and an agreed spending limit. The current scoring view contains the final chat
answer and plan. Use the two-case source development suite and run it with
explicit model-call permission. Do not treat `--limit 2` on the pilot suite as a
development run: that selects two evaluation cases from its frozen schedule.

Check tool arguments, initial versus revised proposals, judge JSON, timeouts,
usage, estimated cost, and missing values. Confirm that frozen replay never calls
the broker or falls back to live market data. Investigate failures before running
more cases. The current runner has call/time/output limits, but no total-dollar
budget stop; keep the pilot small and review measured usage before expanding it.

Completion means both development cases finish through the real provider path,
errors remain visible, and the cost of the planned experiment can be estimated.

## 5. Freeze and run the comparison

Record the code commit, input/reference hashes, rubric and prompt versions, model
settings, resource limits, and trial schedule. Use the same evidence and execution
checks in every condition, and a fresh state for every trial.

Run the full system on all ten cases. The current pilot plan then compares three
preselected cases under four memory conditions, with three repetitions each:
10 screening trials plus 36 comparison trials. If the reviewed dataset changes
the plan, record the change before the experiment and generate a new manifest.

Keep failed and missing runs. Compare original proposals before constraint
feedback separately from final proposals and validator decisions. Do not select
only successful repeats or silently combine experiments with different versions.

Completion means every planned trial has a result or an explicit failure, and
the report can be rebuilt from saved records.

## 6. Human-check outputs and report the findings

Export about 20% of scored outputs, rounded up, with coverage across conditions
and scenario types; add disputed cases. Report the actual coverage and failures.
Reviewers should not see condition labels or judge scores.

Calculate human/judge agreement for each dimension, keeping missing ratings
visible. Summarize task completion, original constraint violations, correct and
false blocks, planted-claim checks, quality scores, tokens, cost, and latency.
Show per-scenario differences and variation across repeated runs. Turn confirmed
software failures into regression tests.

Completion means the presentation can trace each result to saved evidence and
identify the study's limits. Keep conclusions about assistant behavior separate
from claims about investment returns.
