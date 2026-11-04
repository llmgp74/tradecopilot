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
- `as_of`: the scenario date. Tools and outcome computation must not use data dated
  after it.
- `checkpointer`: `None` for a single-shot run, or a saver bound to the run's own
  database.
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
  `portfolio_impact`.
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
