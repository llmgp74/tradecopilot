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
connections. Direct rule and tool checks use a local claim-extraction stub;
runner tests also build the real graph with a scripted local model. No provider
model or broker API is called, and no API key is needed.

The checks cover asset totals, independent reference arithmetic, current agent
schemas, accepted and blocked proposals, isolated stores, missing fixtures,
cutoff handling, and disabled execution. They do not measure agent or judge
performance.

## Agent interface

The fixture follows [docs/eval-contract.md](../../../docs/eval-contract.md)
and the current shared agent interface.
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
times return `fixture_invalid`. The graph takes a date cutoff for tools and a
precise `decision_time` for historical memory retrieval. The source enforces the
exact data-availability timestamp.

## Before a model run

`ScenarioStore` presents the fixed profile confirmation time from inputs.json;
the operational database write time remains separate. Seeded journal dates are
preserved. The graph uses the scenario timestamp for its 90-day window and upper
cutoff. Prose and structured memory contain the same profile facts, including
source preferences and execution settings.

The runner now captures the first proposal batch and later attempts separately.
Its real-graph rehearsal tries 20 shares, retains the blocked result, then tries
one share and captures the accepted draft. The independent scorer checks the
original violation and final compliance separately. Scripted judge scores only
test the workflow and do not measure recommendation quality.

The manual tickets above remain evaluator-only arithmetic checks. Provider model
runs, empirical memory comparisons, and human calibration remain pending; their
outputs belong in separate run records. See [the runner guide](../../README.md)
and [record contracts](../../contracts.md).
