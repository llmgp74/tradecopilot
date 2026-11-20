# Eval run 2026-11-20T10:08:22+0800

Full pilot suite on `main`, model mode, sequential with no retries. Frozen copy
of `~/.tradecopilot/eval/main-full-20261120T0923`.

## Provenance

| Field | Value |
| --- | --- |
| Suite | `pilot-v1`, 10 scenarios |
| Provenance status | `synthetic_pending_review` |
| Suite SHA-256 | `f5a9365a9b4c5905b953a3f6bd81fcfb311178a55bb6f3bbd2fc73a581057aa0` |
| Code SHA-256 | `8ab7da90f2532576f84aec45c3148290b3cfcad7ed4f32d39469992cbc7b2c46` |
| Agent | `deepseek:deepseek-flash`, official API |
| Judge | `openai:qwen3.7-flash` via DashScope, temperature 0 |
| Runs | 46 planned, 46 recorded, 0 missing, 0 failed |
| Judge errors | 0 |
| Report generated | 2026-11-20T10:08:22+0800 |
| Seed | 74 |

One code hash covers all 46 runs, so every paired comparison is valid (27 of
27). A 3-case smoke run preceded this run and passed with the same hash.

## Ablation, 9 scenarios per condition

| Condition | Task success | Evidence | Reasoning | Risk | Profile fit | Actionability |
| --- | --- | --- | --- | --- | --- | --- |
| full | 8/9 | 4.56 | 4.56 | 4.67 | 4.89 | 4.78 |
| structured | 7/9 | 4.33 | 4.11 | 3.89 | 4.44 | 4.78 |
| prose | 6/9 | 3.67 | 3.78 | 4.22 | 3.89 | 4.00 |
| none | 1/9 | 2.78 | 2.78 | 3.22 | 2.33 | 3.56 |

## Paired differences against full

All 27 pairs are valid. Mean differences (condition minus full):

| Condition | Task success | Evidence | Reasoning | Risk | Profile fit | Actionability | Tokens | Seconds |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| none | -0.78 | -1.78 | -1.78 | -1.44 | -2.56 | -1.22 | +3,990 | +3.3 |
| prose | -0.22 | -0.89 | -0.78 | -0.44 | -1.00 | -0.78 | +11,977 | +6.5 |
| structured | -0.11 | -0.22 | -0.44 | -0.78 | -0.44 | 0.00 | +12,109 | +8.2 |

Memory remains the largest factor. Structured output without memory is close to
full on most dimensions but still costs about 12k more tokens and 8 more
seconds per case.

## Screening, 10 cases

Task success 8/10. Quality: evidence 4.30, reasoning 4.60, risk 4.70, profile
fit 5.00, actionability 5.00.

## Operational measurements

- Agent: 59.8k to 72.3k tokens per case, 22.4 to 32.4 seconds.
- Judge: 5.5k to 6.2k tokens per case, 28.9 to 33.2 seconds.
- Cost is unmeasured. Provider responses carried no pricing.

## Caveats

- `unscored (missing)` is not zero. Initial-violation and `verify_claims`
  metrics stayed unscored for most cases because the fixtures contain no
  violating draft and no verifier probes for the selected candidates.
- Two task failures in the ablation `full` condition and two in screening need
  reading in `report.json`; the aggregate rates do not show which cases.
- Fixtures remain `synthetic_pending_review`, so results need reference review
  before they are treated as research evidence.

## Files

| File | Contents |
| --- | --- |
| `report.md` | Generated report, the authoritative tables |
| `report.json` | Full report with per-scenario rows and paired differences |
| `runs.csv` | One row per trial with status and measured metrics |
| `plan.json` | Suite, model, and judge configuration |
| `validation.json` | Fixture and verifier probe validation |
