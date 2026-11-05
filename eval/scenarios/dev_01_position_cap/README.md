# DEV-01: Updated position limit

The user lowered the single-stock cap from 10% to 5%. Their new request asks
whether to add SYNAA without repeating the cap. All records are synthetic.
This development case is separate from the proposal's formal evaluation set.

## Files

- [inputs.json](inputs.json) contains the request, confirmed profile, prior
  decision, and frozen `quote`, `portfolio`, and `positions` responses.
- [reference.json](reference.json) contains evaluator-only calculations,
  manually authored tickets, and response criteria. The input loader and data
  source never read this file.

The account has USD 100,000 equity, USD 10,000 cash, and 40 SYNAA shares worth
USD 4,000. Twenty other synthetic positions hold USD 4,300 each. All positions
are within the current cap before the proposed trade.

| Manual candidate | Buy quantity | Resulting SYNAA weight | Expected rule outcome |
| --- | --- | --- | --- |
| A | 20 | 6% | Block: position cap |
| B | 10 | 5% | Eligible |
| C | 11 | 5.1% | Block: position cap |
| D | 9 | 4.9% | Eligible |

Eligible means the ticket passes the constraints in this fixture. It does not
mean the trade is recommended, approved, or filled. A reasoned no-trade answer
may also be appropriate.

## Local checks

From `eval/`, install the locked dependencies once and run the tests:

```sh
uv sync --locked
uv run --locked --offline pytest
```

Dependency installation may download packages. The tests block network
connections and call the existing rule checker and proposal tools with a local
claim-extraction stub. They do not build a model graph or use API keys.

The checks cover asset totals, independent reference arithmetic, current agent
schemas, accepted and blocked proposals, isolated stores, missing fixtures,
cutoff handling, and disabled execution. They do not measure agent or judge
performance.

## Agent interface

The fixture follows [docs/eval-contract.md](../../../docs/eval-contract.md)
and the agent code at `2e820b0a00417d7ea902a2850c1cb819b7f31d38`.
`load_scenario` reads only inputs. `FrozenSource` supplies the `DataSource`
methods, and `seed_store` creates a new directory with the current profile and
historical journal. Reusing a run directory is an error.

The source exposes the five data capabilities and omits `order_execution`.
Unrecorded calls return `fixture_missing`; they never fall back to a provider.
Fixture arguments must match exactly, including defaults such as `limit=10`.
Each replay returns a separate copy so callers cannot alter later responses.

The source rejects a whole response, including its summary, if `available_at`
or any evidence publication time exceeds the decision timestamp. This initial
fixture format requires timezone-aware publication times; missing or invalid
times return `fixture_invalid`. The agent itself still accepts a date cutoff.

## Before a model run

The current store stamps profile writes with the actual write time. The fixed
confirmation time remains in inputs.json, and seeded journal dates are retained.
The retrieval test supplies the scenario's 90-day lower bound, 2026-06-17,
directly. Agent middleware still calculates that bound from the wall clock.
Scenario-clock support and equal prose/structured profile content remain open.

Next, connect this case to a runner that captures the first proposal even when
it is blocked. Keep the manual tickets here as reference checks; actual model
outputs and judge scores belong in separate run records.
