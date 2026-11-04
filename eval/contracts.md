# Draft evaluation contracts

These are proposed data boundaries, not implemented Python models or APIs.
They support the [evaluation plan](README.md) and need agreement with the agent
owner before implementation. The existing `DataSource` and `MemoryStore` protocols
do not yet define methods; this document does not introduce a second agent.

## Scenario and reference data

| Field | Meaning |
| --- | --- |
| `scenario_id`, `split` | Stable identifier; development or formal evaluation |
| `decision_time` | Time at which the decision is made, including timezone |
| `request` | Current user request, identical across memory conditions |
| `portfolio` | Holdings, account equity, buying power, and valuation assumptions |
| `profile` | Confirmed user constraints and preferences at decision time |
| `journal_before_decision` | Relevant earlier decisions and information then available |
| `evidence_catalog` | Frozen evidence records with stable IDs |
| `tool_fixtures` | Fixed tool responses keyed by tool name and normalized arguments |

Keep reference fact labels, expected rule outcomes, and acceptance criteria in
an evaluator-only section. Do not include them in agent prompts or tool responses.
Profile and journal visibility depends on the memory condition. Execution checks
retain the same true profile in every condition.

Each evidence record should include `evidence_id`, `source`, `url` when applicable,
`published_at` or `available_at`, `fetched_at`, and `payload`. Mark synthetic evidence
explicitly. Availability at decision time governs eligibility; downloading an old
public filing later does not by itself make its contents future information.
Future revisions and outcomes that were not yet knowable must be excluded.

Missing fixture responses must produce an explicit failure, not a live-data
fallback. The exact data-source method and normalization rules remain open.

## Run result

| Field | Meaning |
| --- | --- |
| `run_id`, `scenario_id`, `condition`, `repetition` | Identity and comparison metadata |
| `status`, `errors` | Completion state and explicit agent, tool, or timeout failures |
| `raw_proposal` | Original recommendation and ticket captured before verification or constraint feedback |
| `final_response` | The checked response shown to the user, if one exists |
| `evidence_ids`, `claim_verdicts` | Cited records and runtime fact-check decisions |
| `constraint_result` | Runtime allow/block decision and rule reasons |
| `approval_result`, `execution_result` | Available outcomes; distinguish pending, allowed, submitted, and filled |
| `model_id`, `prompt_version`, `code_revision`, `settings` | Reproduction metadata, excluding secrets |
| `tokens`, `cost`, `latency` | Measured usage; missing measurements stay null |
| `trace` | Messages and tool events sufficient to inspect failures |

For the initial single-ticket cases, a proposed ticket needs a ticker, side,
quantity, and price/equity references sufficient to recompute exposure.
Use an explicit action such as `propose_order`, `no_trade`, or `needs_information`;
absence of a ticket must not be mistaken for an automatically successful task.
Multi-ticket output and execution-status details need agreement before expanding.

## Scoring and isolation

Score original rule adherence against independent reference calculations, not the
production validator's verdict. Separately compare the validator's verdict with
the expected allow/block label. Check fact-verification results against the
reference facts. The [judge](judge.md) evaluates recommendation quality separately.

Preserve run failures, invalid outputs, and judge failures as distinct statuses.
Do not silently omit them or turn missing scores into zero. Report denominators
and the number of unscored runs with every summary.

Use an isolated database and thread for each run; reset caches and any other
writable state that could carry information across conditions. Preserve scenario,
fixture, model, prompt, and rubric versions. Fixed evidence does not guarantee
identical model output or remove knowledge acquired during model training.

## First integration decisions

- Confirm where the graph exposes `raw_proposal` and `final_response`.
- Confirm the fixture lookup and profile/journal read interfaces.
- Resolve timestamp semantics: the existing builder accepts an `as_of` date,
  while intraday scenarios need a timezone-aware cutoff.
- Agree on error/status values and the first supported ticket shape.
