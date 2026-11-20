# Eval run 2026-11-20T07:55:13+0800

Full pilot suite, model mode, sequential with no retries. Artifacts in this
directory are a frozen copy of `~/.tradecopilot/eval/or-full-official`.

## Provenance

| Field | Value |
| --- | --- |
| Suite | `pilot-v1`, 10 scenarios |
| Provenance status | `synthetic_pending_review` |
| Suite SHA-256 | `f5a9365a9b4c5905b953a3f6bd81fcfb311178a55bb6f3bbd2fc73a581057aa0` |
| Agent | `deepseek:deepseek-flash`, official API, temperature from plan |
| Judge | `openai:qwen3.7-flash` via DashScope, temperature 0 |
| Judge family check | deepseek agent, qwen judge |
| Runs | 46 planned, 46 recorded, 0 missing, 0 failed |
| Report generated | 2026-11-20T07:55:13+0800 |
| Seed | 74 |

Code hashes observed during the run:

- Runs 1 to 11: `be4172692fbf3b33b797670bb61135a6acaa6f1c8030545d73732eac9422776c`
- Runs 12 to 46: `1e11af6c369bcde7eae617baa9ab86ba7ee4e2ca8b7397ebf107930a4eb9a8bb`

The tree changed mid-run, which invalidates one paired comparison (NEWS-01,
condition `none`). Treat the run as two code states, not one.

## Ablation, 9 scenarios per condition

| Condition | Task success | Evidence | Reasoning | Risk | Profile fit | Actionability |
| --- | --- | --- | --- | --- | --- | --- |
| full | 9/9 | 5.00 | 5.00 | 4.89 | 5.00 | 5.00 |
| structured | 6/9 | 4.00 | 4.00 | 4.00 | 4.11 | 4.33 |
| prose | 6/9 | 3.67 | 3.67 | 3.78 | 3.89 | 4.11 |
| none | 1/9 | 2.44 | 2.22 | 2.78 | 1.67 | 3.00 |

Quality values are judge scores on a 1 to 5 scale. Sample deviations are in
`report.md`.

## Paired differences against full

26 of 27 pairs are valid. Mean differences (condition minus full):

| Condition | Task success | Evidence | Reasoning | Risk | Profile fit | Actionability | Tokens | Seconds |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| none | -0.88 | -2.38 | -2.62 | -1.88 | -3.25 | -1.88 | +11,854 | +9.8 |
| prose | -0.33 | -1.33 | -1.33 | -1.11 | -1.11 | -0.89 | -1,458 | +5.4 |
| structured | -0.33 | -1.00 | -1.00 | -0.89 | -0.89 | -0.67 | +12,551 | +8.2 |

Removing memory costs success, quality, tokens, and time. Formatting without
memory recovers about half the quality gap.

## Screening, 10 cases

Task success 9/10. Quality: evidence 4.30, reasoning 4.60, risk 4.60, profile
fit 4.50, actionability 4.90.

## Operational measurements

- Agent: 52.2k to 65.8k tokens per case, 17.8 to 26.9 seconds.
- Judge: 5.5k to 6.5k tokens per case, 28.8 to 35.8 seconds.
- Cost is unmeasured. Provider responses carried no pricing, so `cost_usd` is
  null in every row.

## Caveats

- `unscored (missing)` is not zero. Initial-violation and `verify_claims`
  metrics were unscored for most cases because those fixtures contain no
  violating draft and no verifier probes for the picked candidates.
- The judge is slower than the agent. End to end is roughly 50 to 65 seconds
  per case.
- One pair (NEWS-01, `none`) is `mismatched_inputs` because the code hash
  differs between the two runs it compares.
- Results describe the agent prompt, tools, and memory conditions at the
  recorded code hashes. They do not describe later chat UI changes.

## Files

| File | Contents |
| --- | --- |
| `report.md` | Generated report, the authoritative tables |
| `report.json` | Full report with per-scenario rows and paired differences |
| `runs.csv` | One row per trial with status and measured metrics |
| `plan.json` | Suite, model, and judge configuration |
| `validation.json` | Fixture and verifier probe validation |
