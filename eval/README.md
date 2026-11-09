# Evaluation and judge

This package runs frozen cases through the shared agent, saves original proposals
and final responses, checks measurable rules, and sends a blind response view to
a separate judge. It also exports human review forms and summary reports.

The implementation follows [the proposal](../proposal/main.tex). The included
data is synthetic and pending review. Scripted runs test the software; they do
not establish agent quality, memory improvements, or judge accuracy.

## Workflow

1. Validate fixed inputs and independent reference labels.
2. Freeze case hashes, the comparison subset, settings, and the run schedule.
3. Run each trial with a fresh store and identical execution checks.
4. Save all proposal attempts, tool results, the visible response, evidence,
   errors, usage, and timing.
5. Score rules with independent arithmetic, then judge response quality and
   acceptance against the reference context.
6. Sample outputs for blind human review and report results with missing counts.

The source supplies frozen data and never enables order execution. Neither
Alpaca credentials nor the web server are needed.

## Run locally

From `eval/`:

```sh
uv sync --locked
uv run --locked --offline python -m tradecopilot_eval validate
uv run --locked --offline pytest
uv run --locked --offline python -m tradecopilot_eval run \
  --mode scripted --output /tmp/tradecopilot-pilot
```

The first command may download dependencies. Subsequent commands work offline.
The scripted command blocks network connections and uses the real agent graph,
tools, middleware, store, and scorers with predefined model responses. The
scripted judge returns fixed control scores and leaves task acceptance unknown.
Reports exclude those control scores from quality comparisons.

The default [pilot schedule](suites/pilot.json) runs all ten cases once with full
memory, then three selected cases with all four memory conditions, repeated
three times. That is 46 trials. `--limit 2` runs a short smoke check and marks its
manifest as partial. Choose a new output directory for each experiment; existing
runs are never overwritten. Keep output directories outside the repository.

## Saved results

Each output directory contains:

- `plan.json`: the complete schedule, selected trial count, hashes, and settings.
- `validation.json`: reference checks, including separate direct verifier probes.
- `runs/NNNN/`: frozen inputs and references, isolated state, `run.json`, and judge
  input/output when the agent completed.
- `report.json`, `report.md`, and a per-run CSV: summaries and individual results.

The first proposing assistant message defines the initial proposal batch;
parallel proposals remain in the same batch. Blocked attempts are retained even
when a later ticket succeeds. Missing artifacts and failed calls remain visible.

Agent and judge failures have separate counts. Missing token usage and prices
remain null. Agent costs use supplied per-million token rates when usage is
complete; they are estimates, excluding billing adjustments. Judge usage and
timing are recorded separately. Fills, approvals, market hours, and investment
returns are outside these runs.

## Human review

```sh
uv run --locked --offline python -m tradecopilot_eval review \
  --input /tmp/tradecopilot-pilot --output /tmp/tradecopilot-review
```

This exports `ratings.csv` with about 20 percent of scored outputs, balanced for
condition and scenario coverage. `--disputed RUN_ID` adds a disputed case. Give
reviewers the CSV and [rubric](judge.md). Keep `selection-private.json` private:
it contains experiment labels and judge scores. The CSV contains blank score
columns, the candidate, and reference context without condition labels.

After reviewers fill the CSV:

```sh
uv run --locked --offline python -m tradecopilot_eval agreement \
  --input /tmp/tradecopilot-pilot \
  --reviews /tmp/tradecopilot-review/ratings.csv \
  --output /tmp/tradecopilot-review/agreement.json
```

Agreement includes exact agreement, agreement within one point, mean absolute
score difference, and observed/missing pairs for each dimension. Blank forms do
not produce agreement scores. Reviews of scripted controls are marked as such.
Original judge scores remain unchanged.

## Model experiments

Real calls require `--mode model --allow-model-calls`, explicit agent and judge
IDs and family labels, and provider credentials in the environment. The judge
must use a different model family. Temperature is zero where the adapter
supports it. The runner records output-token limits, timeouts, and source,
fixture, and prompt hashes. The graph allows up to 20 agent calls; claim-extraction
calls are additional and included in the agent usage totals. Judge usage is
recorded separately. Judge calls retry malformed structured output once.

The included cases need `--allow-unreviewed-fixtures` for a model pilot. Before
reporting the proposal's empirical study, replace or supplement synthetic data
with frozen real-source evidence, review the labels and rubric, and record that
review. [Calibration examples](calibration/README.md) are provisional discussion
anchors. Provider behavior and rating quality still need a small real-model pilot.

## Files and checks

- [Run contracts](contracts.md): inputs, capture rules, and scoring limits.
- [Judge](judge.md): rubric, validation, retries, and calibration.
- [Development examples](scenarios/development.md): DEV-01 and DEV-02.
- [Ten pilot cases](scenarios/evaluation/README.md): categories and reference labels.

Python checks from `eval/`:

```sh
uv run --locked --offline ruff check src tests
uv run --locked --offline ruff format --check src tests
uv run --locked --offline mypy src tests
uv run --locked --offline pytest
```

The historical-clock and memory-format changes have agent tests too. Run
`uv run --locked --offline pytest` from `agent/` for those checks.
