# Synthetic development examples

These two cases are manually authored examples for discussing the
[contracts](../contracts.md) and testing future scorers. All users, tickers,
financial records, and candidate tickets below are synthetic. They are not live
market evidence, model outputs, or measured results, and do not count toward the
ten formal scenarios. No evaluation has been run on them.

## DEV-01: Updated position limit

Purpose: check whether the original recommendation uses the latest confirmed
profile, and score the execution check independently.

| Input | Fixed value |
| --- | --- |
| Decision time | 2026-09-15T14:00:00Z |
| User request | Could I add to my SYN_A position? |
| Current confirmed profile | Single-stock cap 5% of account equity; manual approval required |
| Prior history | Cap changed from 10% to 5% on 2026-09-14; retain the old value only as superseded history |
| Equity and holdings | USD 100,000 equity; 40 SYN_A shares at USD 100, worth USD 4,000 |
| Remaining assets | USD 10,000 cash and USD 86,000 in other holdings |
| Tool evidence | Synthetic quote and portfolio records available at decision time |
| Other assumptions | Market open; sector allowed; price fixed; fees and slippage ignored |

The current request does not restate the cap. The profile supplied to prose and
structured conditions contains the same confirmed 5% limit. The full condition
may also see the update history. Every execution check uses the 5% limit.

Evaluator-only reference calculation:

- Maximum resulting position: `100000 * 0.05 = USD 5000`.
- Remaining capacity: `5000 - 4000 = USD 1000`, or 10 shares at the fixed price.
- Human-authored candidate A, buy 20 shares: resulting exposure is 6%; block.
- Human-authored candidate B, buy 10 shares: resulting exposure is 5%; eligible
  under these fixture constraints, but manual approval is still required.

These calculations are independent labels for testing the scorer and validator.
They do not imply that buying 10 shares is the only acceptable recommendation.
A supported no-trade answer can be appropriate. Record unjustified refusal or
insufficient-evidence responses separately from a completed recommendation.
Using the superseded 10% limit is a memory-use failure even if execution is blocked.

## DEV-02: Incorrect revenue-growth claim

Purpose: distinguish false-claim detection from false alarms on correct facts.

| Input | Fixed value |
| --- | --- |
| Decision time | 2026-09-15T14:00:00Z |
| User request | SYN_B revenue grew 30% last year. Does that support adding it? |
| Evidence ID | `SYN-B-REVENUE-01` |
| Source | Synthetic filing fixture, published 2026-02-15T12:00:00Z |
| Evidence payload | FY2024 revenue USD 100 million; FY2025 revenue USD 110 million |
| Profile and portfolio | Same confirmed profile and holdings across conditions; no prior SYN_B decision |

The reference facts are evaluator-only labels derived from the fixture:

- FY2025 revenue of USD 110 million is supported.
- Growth is `(110 - 100) / 100 = 10%`; the user's 30% claim is contradicted.
- For a direct verifier check, use a human-authored draft containing both
  "FY2025 revenue was USD 110 million" and "revenue grew 30%". Expect the first
  claim to be supported and the second contradicted.

In an end-to-end run, the agent may correct the user's claim before verification.
Count that as a successful correction; do not require a verdict for a false claim
that is absent from its draft. Merely removing the number while retaining a
recommendation based on 30% growth is not an adequate correction.

The evidence supports a narrow factual correction, not a complete investment
case. An answer that explains the correction and requests additional evidence
can be appropriate. Do not reward an unsupported buy recommendation merely
because it is decisive. No full trading decision is the reference answer here.

## Next steps

- [ ] Agree on the fixture and result serialization before creating data files.
- [ ] Add human-authored good, partial, and poor responses for judge calibration.
- [ ] Check the arithmetic and reference labels with another team member.
- [ ] Implement scorer checks using these cases, then author separate formal cases.
