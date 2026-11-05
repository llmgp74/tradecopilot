# Synthetic development examples

These are two manually authored cases for developing the scorers. All users,
tickers, financial records, and candidate tickets are synthetic. The cases have
not been run and are separate from the ten formal scenarios in the proposal.
Use the [agent mapping](../contracts.md) when turning them into fixtures.

## DEV-01: Updated position limit

Purpose: check whether the original recommendation uses the latest confirmed
profile, and score the execution check independently.

| Input | Fixed value |
| --- | --- |
| Decision time | 2026-09-15T14:00:00Z |
| User request | Could I add to my SYNAA position? |
| Current confirmed profile | `position_cap_pct=5.0`, `horizon="weeks"`, `watchlist=["SYNAA"]` |
| Execution settings | `autonomous=false`, `max_order_notional=3000.0`; execution disabled in the fixture source |
| Prior history | Cap changed from 10% to 5% on 2026-09-14; retain the old value only as superseded history |
| Equity and holdings | USD 100,000 equity; 40 SYNAA shares at USD 100, worth USD 4,000 |
| Remaining assets | USD 10,000 cash and USD 86,000 in other holdings |
| Buying power | USD 10,000 |
| Tool evidence | Synthetic quote and portfolio records available at decision time |
| Other assumptions | No sector exclusions; whole shares; price fixed; fees and slippage ignored |

The current request does not restate the cap. The profile supplied to prose and
structured conditions contains the same confirmed 5% limit. The full condition
may also see the update history. Every constraint check uses the 5% limit.
The five-letter synthetic ticker is in the watchlist so journal retrieval can
recognize it. Seed any related decision event with `decision_id` and a SYNAA leg;
a profile edit alone does not create a decision journal entry.

Evaluator-only reference calculation:

- Maximum resulting position: `100000 * 0.05 = USD 5000`.
- Remaining capacity: `5000 - 4000 = USD 1000`, or 10 shares at the fixed price.
- Human-authored candidate A, buy 20 shares: resulting exposure is 6%; block.
- Human-authored candidate B, buy 10 shares: resulting exposure is 5%; eligible
  under these fixture constraints. No execution or approval occurs in this run.

Represent each candidate as one leg with `ticker`, `side="buy"`, and `qty` in the
`propose_ticket` arguments. The quote payload has `kind="quote"`, `ticker="SYNAA"`,
and `price=100.0`. The account payload has `kind="account"`, equity, cash, buying
power, and the positions listed above. The unrelated holdings must also stay
below the 5% per-stock cap; they can be split across synthetic positions.

Capture candidate A from the tool call even when it is blocked: it will not be
present in `draft_recommendation`. Market-hours and approval checks are outside
this case; the historical fixture path skips market-hours enforcement.

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
| User request | SYNBB revenue grew 30% last year. Does that support adding it? |
| Evidence IDs | `SYNBB-REVENUE-2024`, `SYNBB-REVENUE-2025` |
| Source | Synthetic filing fixture, published 2026-02-15T12:00:00Z |
| Evidence payload | FY2024 revenue USD 100 million; FY2025 revenue USD 110 million |
| Profile and portfolio | Same confirmed profile and holdings across conditions; no prior SYNBB decision |

The reference facts are evaluator-only labels derived from the fixture:

- FY2025 revenue of USD 110 million is supported.
- Growth is `(110 - 100) / 100 = 10%`; the user's 30% claim is contradicted.

For the direct numeric matcher check, use two separate human-authored candidate
claims about FY2025 revenue: USD 110 million is supported; USD 130 million is
contradicted. Encode each annual record as an `EvidenceRecord` with payload
`kind="xbrl"`, `ticker="SYNBB"`, `tag="Revenues"`, `period="FY2024"` or `"FY2025"`,
`unit="USD"`, and `value=100000000` or `110000000`. These are synthetic XBRL-shaped
fixtures, not downloaded filings. Match the claim's tag, period, and unit to the
record so a missing match is not mistaken for a contradiction.

The 10% growth calculation is an independent evaluation label. The current numeric
matcher compares tagged facts and does not calculate growth from two records.
Keep growth correction in the end-to-end case; record an `unchecked` growth
verdict as such rather than expecting the matcher to derive a new fact.

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
