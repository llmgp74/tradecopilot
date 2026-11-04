# Evaluation framework

This is an initial documentation scaffold for the evaluation work in
[the proposal](../proposal/main.tex) and
[the system design](../docs/design-of-system.md). The contracts and rubric
are drafts for discussion with the agent implementation. There is no runner,
judge integration, or experimental result in this contribution.

## Scope

Evaluate whether user memory improves profile fit, constraint adherence, and
decision consistency, and what it costs. The study concerns assistant behavior,
not investment returns.

| Question | Planned measurement | Reference |
| --- | --- | --- |
| Does the agent use the user's rules? | Violations in the original proposal | Independently checked profile and portfolio |
| Do execution checks work? | Correct blocks and false blocks | Labeled valid and invalid tickets |
| Does verification work? | False-claim detection and true-claim false alarms | Independently checked facts |
| Is the recommendation useful? | Five separate quality scores | Judge rubric and human review |
| What does it cost? | Tokens, cost, latency, and failures | Recorded run metadata |

Keep these measures separate initially. A blocked invalid ticket is a successful
block, but still an invalid original proposal. An allowed ticket is not a fill.

## Memory comparison

Use the same agent with `none`, `prose`, `structured`, and `full` memory conditions.
The last condition adds relevant decision history to the structured profile.
The prose and structured versions must contain the same profile facts.

Keep the request, evidence, portfolio, model, other instructions, resource limits,
and execution safeguards fixed. All conditions use the same ground-truth profile
at the execution boundary; only the memory visible to the agent changes.
Save the original proposal before checking feedback, as well as the final response.

The proposal specifies ten formal scenarios: six representative cases (two each
for earnings, news, and portfolio adjustment) and four adversarial cases (two false
claims, one constraint temptation, and one tool failure). A preselected subset
will receive repeated four-condition comparisons. The subset and repetition count
still need agreement. Development examples are separate from this formal set.

## Working documents

- [Draft contracts](contracts.md): scenario, tool evidence, and run results.
- [Judge rubric](judge.md): quality scoring and human calibration.
- [Development examples](scenarios/development.md): two synthetic cases with
  human-authored expectations, not model outputs or evaluation results.

The evaluation side will own fixtures, independent reference labels, scoring,
the runner, and reporting. The agent side will expose the agreed proposal and
checking outputs through the shared graph. The judge runs offline and does not
approve orders or replace runtime verification.

## Implementation sequence

- [ ] Agree on the draft contracts and original-proposal capture point.
- [ ] Turn the two development examples into fixtures and reference labels.
- [ ] Implement programmatic scoring and calibrate the judge on manual examples.
- [ ] Connect a runner to `build_agent`, with fresh state for every run.
- [ ] Freeze the formal scenarios, comparison subset, versions, and run budget.
- [ ] Run comparisons, review outputs, and report per-scenario results and failures.

Until agent integration is ready, scoring can be developed against manually
authored run results. Next implementation should demonstrate one complete
scenario-to-score path before expanding the dataset.
