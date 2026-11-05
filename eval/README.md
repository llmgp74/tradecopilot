# Evaluation framework

Evaluation plan, judge rubric, and development cases for
[the proposal](../proposal/main.tex). The agent's calling interface is defined in
[docs/eval-contract.md](../docs/eval-contract.md). DEV-01 has frozen inputs, a
fixture source, and local checks. The runner and judge are not implemented yet.

## Agent integration

Use the shared `tradecopilot_agent` package from the uv workspace. Each run builds
its own graph with `MemoryConfig`, a fixture data source, and an isolated memory
store, then calls `graph.ainvoke`. Evaluation does not need the FastAPI server.

The fixture source keeps `order_execution` disabled. This lets the agent propose
tickets and use fixed account data without placing orders or needing Alpaca keys.
Real agent and judge calls still need model-provider credentials.
The [result mapping](contracts.md) explains what to save from the graph.

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
The prose and structured versions must contain the same profile facts. The current
renderer omits execution permissions from prose; this needs to be aligned before
the formal comparison. Other integration questions are listed in
[contracts.md](contracts.md#before-the-first-comparison).

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

- [Run records and agent mapping](contracts.md): scenario inputs, fixtures, and
  the fields collected for scoring.
- [Judge rubric](judge.md): quality scoring and human calibration.
- [Development examples](scenarios/development.md): two synthetic cases with
  human-authored expectations, not model outputs or evaluation results.
- [DEV-01 fixed data](scenarios/dev_01_position_cap/README.md): inputs, separate
  reference labels, and offline checks for the updated position cap.

Evaluation owns fixtures, reference labels, scoring, the runner, and reporting.
The agent package owns the graph and runtime checks. We use its existing messages
and state, and record any gaps that need an interface change. The judge scores
completed runs offline.

## Implementation sequence

- [x] Map the evaluation records to the shared agent interface.
- [ ] Confirm first-proposal capture, memory inputs, and scenario-time handling.
- [x] Add DEV-01 fixtures, reference labels, and local agent-interface checks.
- [ ] Turn DEV-02 into fixtures and reference labels.
- [ ] Implement programmatic scoring and calibrate the judge on manual examples.
- [ ] Connect a runner to `build_agent`, with fresh state for every run.
- [ ] Freeze the formal scenarios, comparison subset, versions, and run budget.
- [ ] Run comparisons, review outputs, and report per-scenario results and failures.

Next, connect DEV-01 to first-proposal and final-response capture, then save the
rule scores. Its local tests currently use manual candidates and no model calls.
Manual candidate responses can be used to develop judge scoring in parallel.
