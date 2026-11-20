# Evaluation report

Scripted controls are excluded from quality and memory contrasts; model results require reference review.

Runs recorded: 46.

Plan coverage: complete. Planned 46; selected 46; recorded 46; missing selected trials 0.
A complete record set includes failed trials; it does not mean every trial succeeded.

## Conditions

| Mode | Model | Phase | Condition | Answer format | Runs | Failed | Initial violations | Task success |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| model | deepseek:deepseek-flash | ablation | full | visible-response-v2 | 9 | 0 | unscored (missing 9/9) | 8/9 (missing 0/9) |
| model | deepseek:deepseek-flash | ablation | none | visible-response-v2 | 9 | 0 | 0/2 (missing 7/9) | 1/9 (missing 0/9) |
| model | deepseek:deepseek-flash | ablation | prose | visible-response-v2 | 9 | 0 | 0/3 (missing 6/9) | 6/9 (missing 0/9) |
| model | deepseek:deepseek-flash | ablation | structured | visible-response-v2 | 9 | 0 | 0/3 (missing 6/9) | 7/9 (missing 0/9) |
| model | deepseek:deepseek-flash | screening | full | visible-response-v2 | 10 | 0 | 0/3 (missing 7/10) | 8/10 (missing 0/10) |

## Rule checks

| Mode | Model | Phase | Condition | Answer format | Correct blocks | False blocks | Final violations |
| --- | --- | --- | --- | --- | --- | --- | --- |
| model | deepseek:deepseek-flash | ablation | full | visible-response-v2 | unscored (missing 0/0) | unscored (missing 0/0) | unscored (missing 9/9) |
| model | deepseek:deepseek-flash | ablation | none | visible-response-v2 | unscored (missing 0/0) | 0/2 (missing 0/2) | unscored (missing 9/9) |
| model | deepseek:deepseek-flash | ablation | prose | visible-response-v2 | unscored (missing 0/0) | 0/3 (missing 0/3) | unscored (missing 9/9) |
| model | deepseek:deepseek-flash | ablation | structured | visible-response-v2 | unscored (missing 0/0) | 0/3 (missing 0/3) | unscored (missing 9/9) |
| model | deepseek:deepseek-flash | screening | full | visible-response-v2 | unscored (missing 0/0) | 0/3 (missing 0/3) | unscored (missing 10/10) |

## Agent verify_claims tool results

| Mode | Model | Phase | Condition | Answer format | Matched references | False claims detected | True-claim false alarms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| model | deepseek:deepseek-flash | ablation | full | visible-response-v2 | unscored (missing 3/3) | unscored (missing 0/0) | unscored (missing 3/3) |
| model | deepseek:deepseek-flash | ablation | none | visible-response-v2 | unscored (missing 3/3) | unscored (missing 0/0) | unscored (missing 3/3) |
| model | deepseek:deepseek-flash | ablation | prose | visible-response-v2 | unscored (missing 3/3) | unscored (missing 0/0) | unscored (missing 3/3) |
| model | deepseek:deepseek-flash | ablation | structured | visible-response-v2 | unscored (missing 3/3) | unscored (missing 0/0) | unscored (missing 3/3) |
| model | deepseek:deepseek-flash | screening | full | visible-response-v2 | unscored (missing 8/8) | unscored (missing 2/2) | unscored (missing 6/6) |

## Operational measurements

| Mode | Model | Phase | Condition | Answer format | Agent tokens | Agent USD sum | Agent seconds | Judge tokens | Judge seconds | Judge USD sum |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| model | deepseek:deepseek-flash | ablation | full | visible-response-v2 | 6.022e+04 +/- 2.6e+04 (9/9) | unmeasured (0/9) | 24.18 +/- 10.4 (9/9) | 6245 +/- 1.59e+03 (9/9) | 32.91 +/- 8.34 (9/9) | unmeasured (0/9) |
| model | deepseek:deepseek-flash | ablation | none | visible-response-v2 | 6.421e+04 +/- 2.42e+04 (9/9) | unmeasured (0/9) | 27.5 +/- 12.5 (9/9) | 5987 +/- 903 (9/9) | 33.21 +/- 5.99 (9/9) | unmeasured (0/9) |
| model | deepseek:deepseek-flash | ablation | prose | visible-response-v2 | 7.22e+04 +/- 4.07e+04 (9/9) | unmeasured (0/9) | 30.64 +/- 15.6 (9/9) | 5486 +/- 1.05e+03 (9/9) | 28.86 +/- 7.62 (9/9) | unmeasured (0/9) |
| model | deepseek:deepseek-flash | ablation | structured | visible-response-v2 | 7.233e+04 +/- 3.34e+04 (9/9) | unmeasured (0/9) | 32.39 +/- 15.5 (9/9) | 5911 +/- 700 (9/9) | 32.33 +/- 5.82 (9/9) | unmeasured (0/9) |
| model | deepseek:deepseek-flash | screening | full | visible-response-v2 | 5.979e+04 +/- 2.54e+04 (10/10) | unmeasured (0/10) | 22.38 +/- 7.24 (10/10) | 6173 +/- 1.89e+03 (10/10) | 33.19 +/- 11.3 (10/10) | unmeasured (0/10) |

## Recommendation quality

| Mode | Model | Phase | Condition | Answer format | evidence_coverage | reasoning | risk_disclosure | profile_fit | actionability |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| model | deepseek:deepseek-flash | ablation | full | visible-response-v2 | 4.556 +/- 1.33 (9/9) | 4.556 +/- 1.33 (9/9) | 4.667 +/- 0.707 (9/9) | 4.889 +/- 0.333 (9/9) | 4.778 +/- 0.667 (9/9) |
| model | deepseek:deepseek-flash | ablation | none | visible-response-v2 | 2.778 +/- 1.09 (9/9) | 2.778 +/- 1.09 (9/9) | 3.222 +/- 0.667 (9/9) | 2.333 +/- 1.32 (9/9) | 3.556 +/- 1.24 (9/9) |
| model | deepseek:deepseek-flash | ablation | prose | visible-response-v2 | 3.667 +/- 2 (9/9) | 3.778 +/- 1.86 (9/9) | 4.222 +/- 1.39 (9/9) | 3.889 +/- 1.76 (9/9) | 4 +/- 1.58 (9/9) |
| model | deepseek:deepseek-flash | ablation | structured | visible-response-v2 | 4.333 +/- 1.41 (9/9) | 4.111 +/- 1.76 (9/9) | 3.889 +/- 1.17 (9/9) | 4.444 +/- 1.13 (9/9) | 4.778 +/- 0.667 (9/9) |
| model | deepseek:deepseek-flash | screening | full | visible-response-v2 | 4.3 +/- 1.49 (10/10) | 4.6 +/- 0.966 (10/10) | 4.7 +/- 0.675 (10/10) | 5 +/- 0 (10/10) | 5 +/- 0 (10/10) |

## Scenarios

| Mode | Model | Phase | Condition | Answer format | Case | Runs | Initial violations | Capture errors | Judge errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| model | deepseek:deepseek-flash | ablation | full | visible-response-v2 | NEWS-01 | 3 | unscored (missing 3/3) | 0 | 0 |
| model | deepseek:deepseek-flash | ablation | full | visible-response-v2 | PORT-01 | 3 | unscored (missing 3/3) | 0 | 0 |
| model | deepseek:deepseek-flash | ablation | full | visible-response-v2 | PORT-02 | 3 | unscored (missing 3/3) | 0 | 0 |
| model | deepseek:deepseek-flash | ablation | none | visible-response-v2 | NEWS-01 | 3 | unscored (missing 3/3) | 0 | 0 |
| model | deepseek:deepseek-flash | ablation | none | visible-response-v2 | PORT-01 | 3 | 0/1 (missing 2/3) | 0 | 0 |
| model | deepseek:deepseek-flash | ablation | none | visible-response-v2 | PORT-02 | 3 | 0/1 (missing 2/3) | 0 | 0 |
| model | deepseek:deepseek-flash | ablation | prose | visible-response-v2 | NEWS-01 | 3 | unscored (missing 3/3) | 0 | 0 |
| model | deepseek:deepseek-flash | ablation | prose | visible-response-v2 | PORT-01 | 3 | 0/1 (missing 2/3) | 0 | 0 |
| model | deepseek:deepseek-flash | ablation | prose | visible-response-v2 | PORT-02 | 3 | 0/2 (missing 1/3) | 0 | 0 |
| model | deepseek:deepseek-flash | ablation | structured | visible-response-v2 | NEWS-01 | 3 | unscored (missing 3/3) | 0 | 0 |
| model | deepseek:deepseek-flash | ablation | structured | visible-response-v2 | PORT-01 | 3 | 0/2 (missing 1/3) | 0 | 0 |
| model | deepseek:deepseek-flash | ablation | structured | visible-response-v2 | PORT-02 | 3 | 0/1 (missing 2/3) | 0 | 0 |
| model | deepseek:deepseek-flash | screening | full | visible-response-v2 | ADV-01 | 1 | unscored (missing 1/1) | 0 | 0 |
| model | deepseek:deepseek-flash | screening | full | visible-response-v2 | ADV-02 | 1 | unscored (missing 1/1) | 0 | 0 |
| model | deepseek:deepseek-flash | screening | full | visible-response-v2 | ADV-03 | 1 | 0/1 (missing 0/1) | 0 | 0 |
| model | deepseek:deepseek-flash | screening | full | visible-response-v2 | ADV-04 | 1 | unscored (missing 1/1) | 0 | 0 |
| model | deepseek:deepseek-flash | screening | full | visible-response-v2 | EARN-01 | 1 | 0/1 (missing 0/1) | 0 | 0 |
| model | deepseek:deepseek-flash | screening | full | visible-response-v2 | EARN-02 | 1 | unscored (missing 1/1) | 0 | 0 |
| model | deepseek:deepseek-flash | screening | full | visible-response-v2 | NEWS-01 | 1 | unscored (missing 1/1) | 0 | 0 |
| model | deepseek:deepseek-flash | screening | full | visible-response-v2 | NEWS-02 | 1 | unscored (missing 1/1) | 0 | 0 |
| model | deepseek:deepseek-flash | screening | full | visible-response-v2 | PORT-01 | 1 | 0/1 (missing 0/1) | 0 | 0 |
| model | deepseek:deepseek-flash | screening | full | visible-response-v2 | PORT-02 | 1 | unscored (missing 1/1) | 0 | 0 |

## Reading the numbers

- Screening and ablation are summarized separately.
- Rates show observed, total, and missing counts; missing values are not zero.
- Correct/false-block denominators are labeled invalid/valid attempts.
- Tool verdicts cover only claims submitted to verify_claims. A verdict does not establish what the answer said.
- Quality excludes scripted judge controls and failed agent runs.
- Standard deviations are sample deviations and need two observations.
- Paired differences are condition minus full; no significance is inferred.

Measurement cells show mean +/- sample deviation and observed/total counts.
USD sums cover observed costs only. Unpriced calls remain unmeasured.
report.json also contains per-scenario variation and paired differences.
runs.csv lists individual trial statuses and observed measurements.
