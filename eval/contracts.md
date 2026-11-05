# Evaluation inputs and run records

[docs/eval-contract.md](../docs/eval-contract.md) defines how to call the agent.
This document maps that interface to the records needed for scoring. `RunResult`
fields below are proposed evaluation-side fields, not additional graph state.
The runner and run-result serialization still need implementation.
The first input format is implemented in
[DEV-01](scenarios/dev_01_position_cap/README.md), with reference answers stored
separately from agent inputs.

## Calling the shared agent

1. Create a fresh run directory. Use a `MemoryStore` implementation scoped to that
   run, or reuse `tradecopilot_agent.store.Store` with a database in that directory.
   Seed the confirmed profile and pre-decision journal before building the graph.
2. Supply a fixture `DataSource` and choose `none`, `prose`, `structured`, or `full`
   through `MemoryConfig`. Keep the true profile available to runtime checks.
3. Call `build_agent(config, source, as_of, checkpointer=saver, model=model_id)`.
   Use a run-local saver, or `None` for a single-shot case.
4. Call `graph.ainvoke` with the new `HumanMessage` and a unique `thread_id`.
   Save the returned messages, state, and run metadata before scoring.

The library route does not use the HTTP API or require the web server. Follow the
shared contract for signatures rather than maintaining a second set here.
If reusing `Store`, create its parent directory first; it also creates a
`settings.key` beside the database. Keep the entire run directory isolated.

## Scenario inputs and fixtures

| Field | Meaning |
| --- | --- |
| `scenario_id`, `split` | Stable identifier; development or formal evaluation |
| `decision_time` | Evaluation-side timestamp with timezone; see cutoff limits below |
| `request` | Same current request for all memory conditions |
| `portfolio` | Holdings, equity, cash, buying power, and valuation assumptions |
| `profile` | Confirmed constraints and preferences at decision time |
| `journal_before_decision` | Earlier decisions and information then available |
| `evidence_catalog` | Frozen evidence records with stable IDs |
| `tool_fixtures` | Responses indexed by data-source method and normalized arguments |

DEV-01 stores its portfolio and evidence records inside `tool_fixtures`.

Reference fact labels, expected rule outcomes, and acceptance criteria stay on
the evaluation side. Do not send them to the agent as prompts or tool responses.

Implement the methods in [DataSource](../agent/src/tradecopilot_agent/data.py).
For the initial fixture source, return `alpaca`, `edgar`, `fmp`, `finnhub`, and
`fred` from `capabilities()`, but exclude `order_execution`. Keep this set fixed
across conditions. Missing fixtures and planned tool failures return a
`ToolOutput` with `error` and a useful `summary`; they do not raise or fetch live
data. Do not rely on a missing checkpointer alone to disable execution.

Use [ToolOutput and EvidenceRecord](../agent/src/tradecopilot_agent/state.py)
directly. The evidence key is `id`, not `evidence_id`. Include `tool`, `args`,
`source`, `published_at`, `fetched_at`, `stale`, `url` when available, and `payload`.
Mark synthetic sources explicitly. Required payload fields are listed in the
[shared contract](../docs/eval-contract.md#4-data-source-and-cutoff).

Portfolio fixtures use the tool's account payload: `kind="account"`, `equity`,
`cash`, `buying_power`, and `positions`. Each position includes `ticker`, `qty`,
and `market_value`. The trading tools read this from the first evidence record.
Do not pass the HTTP portfolio response with its nested `account` object.
Quote fixtures use `kind="quote"`, `ticker`, and `price`.

For store seeding, follow [MemoryStore](../agent/src/tradecopilot_agent/memory.py).
The concrete `Store` supports `patch_profile` and `append_journal`; journal events
use `decision_id`. Supply the complete `execution` object when patching it.
`position_cap_pct=5.0` means 5 percent, not 0.05 percent.

## Mapping a run result

| Evaluation field | Source and handling |
| --- | --- |
| `run_id`, `scenario_id`, `condition`, `repetition` | Set by the runner |
| `raw_proposal` | First `propose_ticket` call arguments in the current user turn; capture rule below |
| `final_response` | Last assistant response plus user-visible state: recommendation, portfolio impact, verification, and todos |
| `evidence`, `claim_verdicts` | Graph evidence ledger and scoped `verification` results; retain tool artifacts for earlier attempts |
| `constraint_result` | Outcome of the matching proposal tool call, including `error="blocked"`; not a named graph-state field |
| `approval_result`, `execution_result` | Not exercised in fixture runs; do not infer approval or a fill from an accepted proposal |
| `status`, `errors` | Completion state, tool failures, missing output, or timeout |
| `model_id`, `prompt_version`, `code_revision`, `settings` | Reproduction metadata with credentials excluded |
| `tokens`, `cost`, `latency` | Measured usage; leave missing measurements null |
| `trace` | Messages, tool calls, results, and artifacts needed to reconstruct the run |

Messages are LangChain objects. Preserve `AIMessage.tool_calls` and each
`ToolMessage`'s `tool_call_id`, `content`, and `artifact` when exporting them.
Trading tools put their serialized `ToolOutput` in the artifact; content is the
model-facing summary. Match calls and results by ID, not their list positions.

`verification` includes `draft` and `answer` scopes and may contain `unchecked`
or `unverifiable` verdicts. Extraction failures can instead carry
`status="unavailable"`. Preserve these distinctions. A final response has
annotations, but its text has not necessarily been corrected.

### First-proposal capture

Use the first `propose_ticket` call after the current user message as the proposed
capture point. Save its call ID and unchanged `legs`, `thesis`, and `horizon`
arguments, including blocked or invalid attempts. Keep later attempts separately.
Tickets already support multiple legs; the first development case uses one leg.

Do not use `draft_recommendation` as the original proposal. The tool checks
constraints before producing that state. A blocked attempt has no proposal
artifact and is not written to the journal; a later corrected attempt can become
the final draft. Scoring only that draft would miss the original violation.

If no proposal tool is called, record that fact and the response. Distinguish a
justified no-trade answer, a request for information, and an unstructured trading
recommendation. Missing capture data is not evidence of zero violations.

The blocked artifact contains `error="blocked"` and reasons in `summary`, not a
structured violations list. A separate call to `check_ticket` can produce rule
details, but label it as an evaluation replay, not the original tool result.
Score both against independently checked reference labels.

## Cutoff and isolation

The agent currently accepts an `as_of` date. Keep `decision_time` for the reference
case, but do not claim that the graph enforces an intraday cutoff. For initial
cases, freeze the eligible evidence in advance and pass the agreed scenario date.

The fixture source must filter both summaries and payloads. The middleware's
date filter only covers evidence added to the ledger. Evidence must have been
available at decision time; `fetched_at` may be later when archiving an older
public filing. Exclude later revisions and outcomes not yet knowable.

Reset the database, thread, caches, and other writable state between runs. Keep
the same confirmed profile, holdings, evidence, and execution safeguards in all
conditions. Only the agent-visible memory changes. Record model, prompt, fixture,
and rubric versions; fixed inputs do not guarantee identical model outputs.

Keep agent errors, tool errors, invalid outputs, and judge errors separate. Report
unscored runs and denominators rather than dropping failures or filling scores
with zero. Evaluate fills, approvals, and market-hours enforcement separately;
fixture runs disable execution, and `check_ticket(..., live=False)` skips hours.

## Before the first comparison

- Confirm the first-call capture rule, including parallel calls and responses
  that recommend a trade without calling `propose_ticket`.
- Align prose and structured profile contents. The current prose renderer omits
  execution permissions that are present in the structured version.
- Agree on scenario-time handling for journal retrieval. The current 90-day
  lookback uses the wall clock, and `recent_journal` has no upper cutoff argument.
- Agree on a fixed rendering of user-visible state for the [judge](judge.md).
