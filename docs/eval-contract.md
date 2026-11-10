# Evaluation contract

The evaluation harness calls the same graph builder as the live application.
The implemented runner and saved records are described in
[eval/contracts.md](../eval/contracts.md).

## 1. Construct a run

Build one graph with a separate store and thread for each run:

```python
from tradecopilot_agent import MemoryConfig, build_agent

config = MemoryConfig(condition="full", store=store)
graph = build_agent(
    config,
    source,
    scenario.as_of,
    model=chat_model,
    decision_time=scenario.decision_time,
)
```

- `condition`: `none`, `prose`, `structured`, or `full`.
- `store`: a run-local `MemoryStore` with the confirmed profile and journal.
- `source`: a caller-supplied `DataSource` replaying frozen fixtures. Evaluation
  excludes `order_execution` from its capabilities.
- `as_of`: optional scenario date for historical tools and the evidence ledger
  filter. Omit it for live use. This date alone is not an intraday cutoff.
- `checkpointer`: optional saver bound to the run's own database. The evaluation
  runner uses no saver for single-turn trials. Execution also requires a saver,
  but omitting one is not a substitute for disabling the execution capability.
- `model`: a `provider:model` string or a constructed `BaseChatModel` that supports
  tool binding. Omission falls back to `AGENT_MODEL`. Injecting a local model
  avoids provider construction.
- `decision_time`: optional timezone-aware timestamp for journal retrieval. The
  historical window ends at this instant and starts 90 days earlier. Without
  it, `as_of` uses the end of that UTC date; with neither argument, live retrieval
  uses the current time. A naive timestamp raises `ValueError`.

Supply both the scenario date and timestamp for historical evaluation. The
timestamp does not change the date-based tool API; `FrozenSource` separately
enforces the exact timestamp before exposing either summaries or evidence.

The explicit model mode may construct a provider client from environment
credentials. The evaluation runner requires `allow_model_calls=True` before
that path. Its default scripted mode needs no API key and uses no provider.

### Checkpointer

Applications that need persisted turns can pass a run-local saver:

```python
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

async with AsyncSqliteSaver.from_conn_string(str(run_db)) as saver:
    await saver.setup()
    graph = build_agent(config, source, scenario.as_of, checkpointer=saver)
```

## 2. Invoke

The graph is async:

```python
from langchain_core.messages import HumanMessage

result = await graph.ainvoke(
    {"messages": [HumanMessage(content=scenario.request)]},
    {"configurable": {"thread_id": run_id}},
)
```

The runner uses `astream(..., stream_mode="values")` to retain the latest state
if a later step fails or times out. A checkpointer retains prior turns when one
is supplied; send the new user message rather than duplicating stored history.

State includes `messages`, `verification`, `todos`, `draft_recommendation`, and
`portfolio_impact`, plus loop internals such as `evidence` and `pending_ticket`.
The user-visible projection is the last assistant answer and those four visible
state fields. They reset at a new user turn, not an approval resume. A failure
before initialization can leave fields absent; the runner records missing output.

Each verification verdict carries `scope` (`answer`) and a verdict such as
`supported`, `contradicted`, `unchecked`, or `unverifiable`. Verdicts come only
from the model's `verify_claims` calls; a verdict does not mean the answer text
was corrected.

Trading tools return the model-facing summary in `ToolMessage.content` and the
serialized `ToolOutput` in `ToolMessage.artifact`. Pair proposal calls and results
by `tool_call_id`, preserving blocked attempts and parallel calls.

## 3. Memory conditions

| Condition | Injected content |
| --- | --- |
| `none` | Nothing |
| `prose` | Profile rendered as ordinary text |
| `structured` | The same profile facts as structured fields |
| `full` | Structured profile plus relevant journal entries |

Prose and structured views include source preferences and execution settings.
Every condition uses the same confirmed profile for runtime constraints, even
when no profile is injected into the model prompt. Only `full` retrieves the
journal. Historical retrieval excludes later events and selects each decision's
latest eligible snapshot before applying the result limit.

## 4. Data source and cutoff

`DataSource` supplies `capabilities` and async `quote`, `bars`, `portfolio`,
`positions`, `fundamentals`, `filings`, `xbrl_fact`, `news`, `macro`, and
`place_leg` methods. Data methods return `ToolOutput` with `summary`, `evidence`,
and `error`. Expected provider failures return an error output rather than raising.

The evaluation `FrozenSource` exposes `alpaca`, `edgar`, `fmp`, `finnhub`, and
`fred`; it never exposes `order_execution`. Direct `place_leg` calls also return
`execution_disabled`. An unrecorded call returns `fixture_missing` without a live
fallback. The exact method and normalized arguments identify a fixture.

It refuses the whole response before exposing any text or payload if
`available_at` or an evidence `published_at` exceeds `decision_time`. All fixture
publication times must be timezone-aware; missing or invalid times are refused.
The graph's `as_of` ledger filter is a separate date-based check.

Evidence payloads carry `kind` and the fields expected by the trading tools:

- `quote`: `ticker`, `price`
- `account`: `equity`, `cash`, `buying_power`, `positions`
- `fundamentals`: `ticker`, `sector`
- `filing`: `ticker`, `accession`, `filing_type`, `date`
- `xbrl`: `ticker`, `tag`, `period`, `unit`, `value`, optional `fiscal_period`
- `news`: `ticker`, `date`, `headline`
- `macro`: `series`, `date`, `value`

Execution and order payloads are outside frozen evaluation. Account positions
include `ticker`, `qty`, and `market_value`; portfolio tools use the first
evidence record's account payload.

## 5. Memory store

`MemoryStore` provides these methods:

```python
def get_profile(self) -> dict: ...
def recent_journal(
    self,
    tickers: list[str],
    since: str,
    limit: int,
    *,
    until: str | None = None,
) -> list[dict]: ...
def append_journal(self, event: dict) -> None: ...
```

`since` is an inclusive date or timestamp lower bound. Historical `until` is an
inclusive timezone-aware upper bound. The concrete `Store` supports bounded
snapshot selection. A custom store used for historical journal retrieval must
accept the new keyword; legacy live calls still omit it and remain compatible.

Evaluation `seed_store` creates a separate `ScenarioStore`, database, and
`settings.key` per run. The profile view uses the confirmation timestamp from
the frozen scenario; SQLite's operational write timestamp is separate. Journal
seed timestamps are preserved. Reusing a run directory raises `FileExistsError`.
