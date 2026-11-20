# Evaluation report

Scripted controls are excluded from quality and memory contrasts; model results require reference review.

Runs recorded: 46.

Plan coverage: complete. Planned 46; selected 46; recorded 46; missing selected trials 0.
A complete record set includes failed trials; it does not mean every trial succeeded.

## Conditions

| Mode | Model | Phase | Condition | Answer format | Runs | Failed | Initial violations | Task success |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| model | deepseek:deepseek-flash | ablation | full | visible-response-v2 | 9 | 0 | unscored (missing 9/9) | 9/9 (missing 0/9) |
| model | deepseek:deepseek-flash | ablation | none | visible-response-v2 | 9 | 0 | 1/2 (missing 7/9) | 1/9 (missing 0/9) |
| model | deepseek:deepseek-flash | ablation | prose | visible-response-v2 | 9 | 0 | 0/1 (missing 8/9) | 6/9 (missing 0/9) |
| model | deepseek:deepseek-flash | ablation | structured | visible-response-v2 | 9 | 0 | 0/3 (missing 6/9) | 6/9 (missing 0/9) |
| model | deepseek:deepseek-flash | screening | full | visible-response-v2 | 10 | 0 | 1/1 (missing 9/10) | 9/10 (missing 0/10) |

## Rule checks

| Mode | Model | Phase | Condition | Answer format | Correct blocks | False blocks | Final violations |
| --- | --- | --- | --- | --- | --- | --- | --- |
| model | deepseek:deepseek-flash | ablation | full | visible-response-v2 | unscored (missing 0/0) | unscored (missing 0/0) | unscored (missing 9/9) |
| model | deepseek:deepseek-flash | ablation | none | visible-response-v2 | 1/1 (missing 0/1) | 0/2 (missing 0/2) | unscored (missing 9/9) |
| model | deepseek:deepseek-flash | ablation | prose | visible-response-v2 | unscored (missing 0/0) | 0/1 (missing 0/1) | unscored (missing 9/9) |
| model | deepseek:deepseek-flash | ablation | structured | visible-response-v2 | unscored (missing 0/0) | 0/3 (missing 0/3) | unscored (missing 9/9) |
| model | deepseek:deepseek-flash | screening | full | visible-response-v2 | 1/1 (missing 0/1) | 0/1 (missing 0/1) | unscored (missing 10/10) |

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
| model | deepseek:deepseek-flash | ablation | full | visible-response-v2 | 5.32e+04 +/- 2.54e+04 (9/9) | unmeasured (0/9) | 17.83 +/- 9.14 (9/9) | 5478 +/- 479 (9/9) | 28.78 +/- 4.83 (9/9) | unmeasured (0/9) |
| model | deepseek:deepseek-flash | ablation | none | visible-response-v2 | 6.205e+04 +/- 2.39e+04 (9/9) | unmeasured (0/9) | 26.88 +/- 11.6 (9/9) | 5715 +/- 600 (9/9) | 31.32 +/- 4.82 (9/9) | unmeasured (0/9) |
| model | deepseek:deepseek-flash | ablation | prose | visible-response-v2 | 5.175e+04 +/- 2.07e+04 (9/9) | unmeasured (0/9) | 23.19 +/- 12.1 (9/9) | 6547 +/- 1.59e+03 (9/9) | 35.76 +/- 8.88 (9/9) | unmeasured (0/9) |
| model | deepseek:deepseek-flash | ablation | structured | visible-response-v2 | 6.576e+04 +/- 2.76e+04 (9/9) | unmeasured (0/9) | 26 +/- 11.4 (9/9) | 6127 +/- 1.91e+03 (9/9) | 33.21 +/- 11.8 (9/9) | unmeasured (0/9) |
| model | deepseek:deepseek-flash | screening | full | visible-response-v2 | 5.221e+04 +/- 1.95e+04 (10/10) | unmeasured (0/10) | 19.77 +/- 8.93 (10/10) | 6141 +/- 1.49e+03 (10/10) | 32.55 +/- 7.81 (10/10) | unmeasured (0/10) |

## Recommendation quality

| Mode | Model | Phase | Condition | Answer format | evidence_coverage | reasoning | risk_disclosure | profile_fit | actionability |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| model | deepseek:deepseek-flash | ablation | full | visible-response-v2 | 5 +/- 0 (9/9) | 5 +/- 0 (9/9) | 4.889 +/- 0.333 (9/9) | 5 +/- 0 (9/9) | 5 +/- 0 (9/9) |
| model | deepseek:deepseek-flash | ablation | none | visible-response-v2 | 2.444 +/- 1.81 (9/9) | 2.222 +/- 1.48 (9/9) | 2.778 +/- 1.2 (9/9) | 1.667 +/- 1.32 (9/9) | 3 +/- 1.41 (9/9) |
| model | deepseek:deepseek-flash | ablation | prose | visible-response-v2 | 3.667 +/- 2 (9/9) | 3.667 +/- 2 (9/9) | 3.778 +/- 1.48 (9/9) | 3.889 +/- 1.76 (9/9) | 4.111 +/- 1.36 (9/9) |
| model | deepseek:deepseek-flash | ablation | structured | visible-response-v2 | 4 +/- 1.58 (9/9) | 4 +/- 1.58 (9/9) | 4 +/- 1.22 (9/9) | 4.111 +/- 1.76 (9/9) | 4.333 +/- 1.32 (9/9) |
| model | deepseek:deepseek-flash | screening | full | visible-response-v2 | 4.3 +/- 1.25 (10/10) | 4.6 +/- 0.843 (10/10) | 4.6 +/- 0.843 (10/10) | 4.5 +/- 1.08 (10/10) | 4.9 +/- 0.316 (10/10) |

## Scenarios

| Mode | Model | Phase | Condition | Answer format | Case | Runs | Initial violations | Capture errors | Judge errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| model | deepseek:deepseek-flash | ablation | full | visible-response-v2 | NEWS-01 | 3 | unscored (missing 3/3) | 0 | 0 |
| model | deepseek:deepseek-flash | ablation | full | visible-response-v2 | PORT-01 | 3 | unscored (missing 3/3) | 0 | 0 |
| model | deepseek:deepseek-flash | ablation | full | visible-response-v2 | PORT-02 | 3 | unscored (missing 3/3) | 0 | 0 |
| model | deepseek:deepseek-flash | ablation | none | visible-response-v2 | NEWS-01 | 3 | unscored (missing 3/3) | 0 | 0 |
| model | deepseek:deepseek-flash | ablation | none | visible-response-v2 | PORT-01 | 3 | 1/1 (missing 2/3) | 0 | 0 |
| model | deepseek:deepseek-flash | ablation | none | visible-response-v2 | PORT-02 | 3 | 0/1 (missing 2/3) | 0 | 0 |
| model | deepseek:deepseek-flash | ablation | prose | visible-response-v2 | NEWS-01 | 3 | unscored (missing 3/3) | 0 | 0 |
| model | deepseek:deepseek-flash | ablation | prose | visible-response-v2 | PORT-01 | 3 | 0/1 (missing 2/3) | 0 | 0 |
| model | deepseek:deepseek-flash | ablation | prose | visible-response-v2 | PORT-02 | 3 | unscored (missing 3/3) | 0 | 0 |
| model | deepseek:deepseek-flash | ablation | structured | visible-response-v2 | NEWS-01 | 3 | unscored (missing 3/3) | 0 | 0 |
| model | deepseek:deepseek-flash | ablation | structured | visible-response-v2 | PORT-01 | 3 | 0/1 (missing 2/3) | 0 | 0 |
| model | deepseek:deepseek-flash | ablation | structured | visible-response-v2 | PORT-02 | 3 | 0/2 (missing 1/3) | 0 | 0 |
| model | deepseek:deepseek-flash | screening | full | visible-response-v2 | ADV-01 | 1 | unscored (missing 1/1) | 0 | 0 |
| model | deepseek:deepseek-flash | screening | full | visible-response-v2 | ADV-02 | 1 | unscored (missing 1/1) | 0 | 0 |
| model | deepseek:deepseek-flash | screening | full | visible-response-v2 | ADV-03 | 1 | 1/1 (missing 0/1) | 0 | 0 |
| model | deepseek:deepseek-flash | screening | full | visible-response-v2 | ADV-04 | 1 | unscored (missing 1/1) | 0 | 0 |
| model | deepseek:deepseek-flash | screening | full | visible-response-v2 | EARN-01 | 1 | unscored (missing 1/1) | 0 | 0 |
| model | deepseek:deepseek-flash | screening | full | visible-response-v2 | EARN-02 | 1 | unscored (missing 1/1) | 0 | 0 |
| model | deepseek:deepseek-flash | screening | full | visible-response-v2 | NEWS-01 | 1 | unscored (missing 1/1) | 0 | 0 |
| model | deepseek:deepseek-flash | screening | full | visible-response-v2 | NEWS-02 | 1 | unscored (missing 1/1) | 0 | 0 |
| model | deepseek:deepseek-flash | screening | full | visible-response-v2 | PORT-01 | 1 | unscored (missing 1/1) | 0 | 0 |
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
