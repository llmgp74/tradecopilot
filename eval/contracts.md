# Evaluation inputs and run records

The local runner, trace capture, deterministic scorers, and judge interface are
implemented. [The shared contract](../docs/eval-contract.md) defines the agent
boundary. Scripted runs exercise the real graph and tools without provider or
broker calls. They do not establish model quality or a memory-condition benefit.

## Calling the shared agent

`run_case(case, output_dir, config, condition=...)` creates a new directory and
seeds a `ScenarioStore` with the confirmed profile and pre-decision journal. It
constructs a `FrozenSource`, a new model instance, and a shared `build_agent`
graph. The graph receives the scenario date and precise `decision_time`, then
streams state with a unique thread ID. No web server is required.

The default `RunConfig` selects the local `ScriptedAgent`. It gathers fixtures,
tries 20 shares, then one share, and emits control text. Its extractor returns
no claims. It reads scenario inputs only and behaves the same in all conditions.
The scripted judge returns fixed control scores and unknown acceptance results.
These outputs are kept separate from empirical model results in reports.

Model mode requires explicit `allow_model_calls=True`. Judge mode and recorded
agent identity must match the run. Calls are bounded by the configured timeout,
output-token limit, and graph recursion limit; the shared graph also limits
agent model calls to 20. Provider cancellation can depend on its own timeout.
Real provider behavior, model quality, and human judge calibration remain unrun.

## Scenario inputs and fixtures

The implemented `Scenario` fields are:

| Field | Meaning |
| --- | --- |
| `schema_version` | Input schema version, currently 1 |
| `scenario_id`, `split` | Identifier and development/evaluation designation |
| `synthetic` | Explicit synthetic-data flag; currently required to be true |
| `decision_time` | Timezone-aware decision timestamp |
| `request` | The same current request across memory conditions |
| `profile` | Confirmed constraints and preferences at decision time |
| `journal_before_decision` | Earlier decision snapshots with `decision_id` |
| `tool_fixtures` | Frozen data-source calls, outputs, and availability times |

Portfolio and evidence records are inside `tool_fixtures`; they are not separate
top-level input fields. Each fixture contains `method`, normalized `arguments`,
`available_at`, and a shared `ToolOutput`. Reference labels, expected ticket
outcomes, claim probes, and acceptance criteria live in separate `reference.json`.
The evaluator reads these labels; the blind judge receives reference evidence
and response criteria. The trading agent receives neither labels nor criteria.

The source uses [DataSource](../agent/src/tradecopilot_agent/data.py) and
[ToolOutput and EvidenceRecord](../agent/src/tradecopilot_agent/state.py). Evidence
uses `id`, `tool`, `args`, `source`, `published_at`, `fetched_at`, `stale`, `url`,
and `payload`. Synthetic sources are marked explicitly. The
[shared contract](../docs/eval-contract.md#4-data-source-and-cutoff) lists payloads.

Portfolio tools read the first evidence record's flat `kind="account"` payload:
`equity`, `cash`, `buying_power`, and `positions`. Each position has `ticker`,
`qty`, and `market_value`. This differs from the HTTP portfolio response's nested
`account` object. Quote fixtures have `kind="quote"`, `ticker`, and `price`.

Capabilities remain `alpaca`, `edgar`, `fmp`, `finnhub`, and `fred` in every
condition. `order_execution` is absent, and direct `place_leg` calls are refused.
Missing fixtures return `fixture_missing`; planned outages return their recorded
error. Neither path fetches live data. Duplicate fixture keys are rejected, and
response copies prevent one caller from mutating later replays.

## Saved RunRecord fields

The implemented [RunRecord](src/tradecopilot_eval/records.py) is written to
`run.json`. Each run also saves its inputs and independent reference file.

| Field | Source and handling |
| --- | --- |
| `schema_version`, `run_id`, `scenario_id` | Record version and identifiers |
| `condition`, `phase`, `repetition` | Memory condition and trial placement |
| `mode`, `model_id`, `model_family` | Explicit scripted/model configuration |
| `status`, `errors` | `ok`, `agent_error`, `timeout`, or `invalid_output` |
| `initial_proposal_ids` | All proposal IDs in the first proposing assistant message |
| `proposals` | Every captured call, original arguments, matching artifact, and capture error |
| `final_response` | Text, draft recommendation, portfolio impact, verification, and todos |
| `trace` | Serialized messages, including tool-call IDs and artifacts |
| `evidence` | Latest graph evidence ledger |
| `tool_errors` | Tool-call IDs and errors from returned artifacts |
| `usage` | Observed model-call counts, tokens, cost estimate, and elapsed seconds |
| `metadata` | Input/reference/code/prompt hashes, settings, versions, and provenance |
| `scores` | Independent rule results and explicitly observed claim checks |
| `judge` | Separate judge result and attempts, or null when not run |

The stable visible-response projection is versioned in metadata. Judge input is
saved separately and contains that projection, request, confirmed context,
reference evidence, and acceptance criteria. It omits condition labels, model
identity, raw proposal attempts, and private traces. Agent annotations remain
visible but are not reference labels. See [judge.md](judge.md).

Metadata includes the exact input/reference file hashes, local Python-source and
dependency-file digest, agent prompt hash, runtime package versions, Python
version, settings, and `execution_enabled=false`. Judge results record their
prompt and rubric versions. The source digest includes uncommitted local edits;
it is not a Git commit identifier.

Usage totals remain null unless every counted model call supplies token usage.
Cost is calculated only with complete tokens and both explicitly supplied token
prices. It is an estimate, not a billing receipt. Scripted calls have observed
call counts but no fabricated token counts or zero-dollar cost.

### Original proposals and tool feedback

Capture all `propose_ticket` calls after the latest user message. The first
assistant message containing proposals defines the initial batch, including
parallel calls. Preserve unchanged `legs`, `thesis`, and `horizon` arguments for
each attempt, even when the tool rejects them. Later revisions stay separate.

Match `AIMessage.tool_calls` to `ToolMessage.artifact` by call ID. The artifact is
the serialized `ToolOutput`; `content` is only its model-facing summary. Missing
IDs, duplicate IDs, missing/duplicate results, and absent artifacts are explicit
capture errors. They do not imply a successful or blocked tool decision.

`draft_recommendation` is the final accepted draft, not the raw proposal. A
blocked result still has a tool artifact with `error="blocked"`, but its
`proposal` field is null and no draft is written to the journal. A later accepted
ticket can replace the visible draft without erasing the earlier attempt.
Acceptance does not imply approval, execution, or a fill.

## Deterministic scoring and missing observations

`score_ticket` computes constraints independently with `Decimal`, using the
frozen account, prices, sectors, and confirmed profile. It does not call the
agent's `check_ticket` or copy the candidate reference labels. Tests compare its
results with separately authored labels and boundary arithmetic. This oracle
covers the frozen rule study, not market-hours checks, fills, or changing prices.

Each attempt records independent violation status and observed blocking. The
blocked artifact supplies its decision and textual reasons; the evaluator's
rule codes are a separate computation. Correct-block observations apply only to
violating proposals; false-block observations apply only to compliant proposals.
Unknown artifact feedback remains null in both measurements.

`initial_violation` is true if any initial parallel proposal violates a rule,
false if all are scorable and compliant, and null if there is no proposal or
required data is missing. The final draft is scored separately. No proposal is
not evidence of zero violations. A justified no-trade response, missing evidence,
and an unstructured recommendation require response-level assessment.

Verification keeps `draft` and `answer` scopes distinct. Run-level claim
observations use only `answer` entries whose claim text matches a reference probe
after case and whitespace normalization. Omitted checks, paraphrases, unavailable
extraction, and conflicting verdicts remain unobserved. This narrow matching rule
does not measure semantic correction of every false claim in the final text.

Direct `verifier_probes` test the existing matcher against labeled true and false
claims and fixed evidence. Their results are reported separately from graph-run
observations. A matcher test passing does not prove that an agent noticed or
corrected the claim. Derived growth calculations are independently labeled; the
direct numeric matcher checks individual facts rather than arbitrary formulas.

The runner populates task success only from a valid model judge's acceptance
results and allowed outcome, subject to independent final-ticket checks. An
unscorable final ticket cannot support a success claim. Scripted judge scores
are workflow controls. Agent failures, tool errors, invalid
outputs, missing data, and judge errors remain separate; report denominators and
unscored counts rather than dropping failures or replacing missing scores with 0.

## Cutoff and isolation

`FrozenSource` refuses an entire response before exposing its summary or payload
if availability or any publication timestamp is after `decision_time`. Fixture
publication timestamps must be timezone-aware. `fetched_at` can be later when
archiving a previously published record. Later revisions and unavailable outcomes
must not appear in the decision inputs.

The shared graph receives `decision_time` for the 90-day journal window and an
inclusive upper bound. Historical `Store` retrieval chooses eligible snapshots
before limiting results. Legacy custom stores need the optional `until` keyword
for this historical path; live calls still use their existing signature.
`as_of` remains the tool API's date cutoff, so the fixture source is responsible
for the stricter intraday data boundary.

Each run gets its own database, settings key, thread, graph, and model instance.
`ScenarioStore.get_profile` exposes the fixed confirmation timestamp from inputs;
SQLite's operational write timestamp is separate. All conditions share profile
facts, account, fixtures, and runtime safeguards. Prose and structured views now
contain the same profile facts; only full memory adds historical journal entries.

Timeouts and agent errors retain the latest streamed state for trace capture and
scoring. Fixed inputs and limits support comparison but cannot guarantee identical
provider outputs. Real-model screening, repeated comparisons, human calibration,
and any empirical claim that memory improves quality remain pending.
