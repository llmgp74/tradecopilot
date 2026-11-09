# Pilot scenario candidates

These ten cases follow the categories in the proposal. Their companies, market
data, filings, and news are synthetic. They can test the evaluation software and
support a synthetic pilot; they are not the collected-source dataset described
in the proposal. Keep that distinction in any report.

Each directory contains agent inputs and a separate reference file. The reference
file lists acceptable outcomes, rule-check candidates, and factual claim probes.
All records were specified before the first model comparison. The references
still need team review; `provenance_status` records that status.

| Case | Category | Main check |
| --- | --- | --- |
| EARN-01 | Earnings | Higher revenue with falling profit and margin |
| EARN-02 | Earnings | Improved results with little room below the position cap |
| NEWS-01 | News | A new sector exclusion supersedes an earlier preference |
| NEWS-02 | News | A proposed acquisition still needs approval and financing details |
| PORT-01 | Portfolio | A position cap changed from 8% to 4% |
| PORT-02 | Portfolio | An earlier decision to wait for a margin threshold still applies |
| ADV-01 | False claim | Claimed revenue of USD 180 million; reference value USD 150 million |
| ADV-02 | False claim | Claimed cash of USD 75 million; reference value USD 45 million |
| ADV-03 | Constraint | A request pressures the agent to exceed the saved cap |
| ADV-04 | Tool failure | A quote outage leaves the price unavailable |

The development cases remain separate. PORT-01 uses different values from
DEV-01: equity is USD 80,000, the holding is USD 2,400, the cap is 4%, and the
quote is USD 80. ADV-01 and ADV-02 use different facts from DEV-02.

## Reference checks

Candidate tickets test hard constraints. They are not required trading answers.
PORT-02 deliberately includes a ticket that passes hard constraints but conflicts
with an earlier decision; its response criteria capture that distinction.

Claim probes test the factual matcher with predefined true and false statements.
They are separate from evaluating whether the agent corrects a false statement
in the user's request. An agent may correct it before producing a claim for the
matcher. Missing or unchecked claims must remain visible in the results.

Reference evidence preserves the synthetic source label, timestamp, and record
ID. No external records, model responses, or subsequent outcomes are included.
The model-facing fixtures do not contain the reference answers or scoring rules.

## Before reporting research results

Review the reference arithmetic and acceptance criteria with another team member.
For the proposal's collected-evidence study, prepare a separately versioned set
with archived source records, availability times, and independently checked
labels. Freeze that set and the comparison plan before running it. Do not present
an offline rehearsal or synthetic pilot as a result from collected market data.
