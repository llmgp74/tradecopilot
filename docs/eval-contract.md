# Evaluation Contract

The library boundary used by the evaluation harness.

## 1. Construct a run

One graph per run. Build it inside the run's own scope.

```python
from tradecopilot_agent import MemoryConfig, build_agent

config = MemoryConfig(condition="full", store=store)
graph = build_agent(
    config,
    source,
    scenario.as_of,
    checkpointer=saver,
    model="anthropic:claude-sonnet-5",
)
```

- `condition`: `none`, `prose`, `structured`, or `full`.
- `store`: the harness `MemoryStore` implementation.
- `source`: the harness `DataSource` implementation, replaying frozen fixtures.
  It reports every capability except `order_execution`, so `execute_ticket` is
  unavailable and no run pauses on an approval it cannot resume. A fixture that
  needs to fail returns an error `ToolOutput`; it must not raise.
- `as_of`: the scenario date. Tools and outcome computation must not use data dated
  after it. The fixture source is constructed with this date; the middleware also
  drops any evidence record published after it.
- `checkpointer`: `None` for a single-shot run, or a saver bound to the run's own
  database. Without a saver, `execute_ticket` is unavailable.
- `model`: `provider:model` override. Falls back to `AGENT_MODEL`.

The provider key comes from the environment (`DEEPSEEK_API_KEY`, `ANTHROPIC_API_KEY`,
and so on). The harness sets it before building, or sets `MODEL_API_KEY` in the
environment.

### Checkpointer

```python
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

async with AsyncSqliteSaver.from_conn_string(str(run_db)) as saver:
    await saver.setup()
    graph = build_agent(config, source, scenario.as_of, checkpointer=saver)
    ...
```

## 2. Invoke

The graph is async.

```python
from langchain_core.messages import HumanMessage

result = await graph.ainvoke(
    {"messages": [HumanMessage(content=scenario.request)]},
    {"configurable": {"thread_id": run_id}},
)
messages = result["messages"]
```

- Pass only the new user message on the first turn. The checkpointer holds history on
  later turns.
- State keys: `messages`, `verification`, `todos`, `draft_recommendation`,
  `portfolio_impact`, plus the loop internals `evidence`, `pending_ticket`, and
  `gather_calls`.
- `verification` is a list of verdicts, each carrying `scope` (`draft` or `answer`)
  and `verdict` (`supported`, `contradicted`, `unchecked`, or `unverifiable`).
- `draft_recommendation` holds the ticket id, legs, thesis, and horizon.
  `portfolio_impact` holds before and after weights, net notional, and equity.
- All five contract keys exist after every run. They are cleared at the start of a
  new user turn, not on an approval resume.
- The proposal shown to a user is the last assistant message plus those state fields.

## 3. Memory conditions

| Condition | Injected content |
| --- | --- |
| `none` | Nothing |
| `prose` | Profile rendered as ordinary text |
| `structured` | Profile as typed constraints and preferences |
| `full` | Structured profile plus relevant journal entries |

## 4. Data source and cutoff

`DataSource` is supplied by the caller. `as_of` is the cutoff: tools and outcome
computation must not use data dated after it.

The source implements `capabilities`, `quote`, `bars`, `portfolio`, `positions`,
`fundamentals`, `filings`, `xbrl_fact`, `news`, `macro`, and `place_leg`. Each returns
`ToolOutput` with `summary`, `evidence`, and `error`. Evidence payloads carry a `kind`
and the fields the matcher expects:

- `quote`: `ticker`, `price`
- `account`: `equity`, `cash`, `buying_power`, `positions`
- `fundamentals`: `ticker`, `sector`
- `filing`: `ticker`, `accession`, `filing_type`, `date`
- `xbrl`: `ticker`, `tag`, `period`, `unit`, `value`, optional `fiscal_period`
- `news`: `ticker`, `date`, `headline`
- `macro`: `series`, `date`, `value`
- `order`: `status`, `fill_price`, `fill_at`

## 5. Memory store

The `MemoryStore` passed in `MemoryConfig` must implement:

```python
def get_profile() -> dict
def recent_journal(tickers: list[str], since: str, limit: int) -> list[dict]
def append_journal(event: dict) -> None
```

The runtime store is `tradecopilot_agent.store.Store`. The harness can reuse it
against its own database path.
