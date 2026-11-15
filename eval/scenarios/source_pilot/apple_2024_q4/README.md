# Apple FY2024 Q4 source case

REAL-EARN-01 is a development case built from Apple's October 31, 2024 earnings
release and financial statements. It asks whether higher revenue and lower GAAP
net income support a purchase. The reference checks whether the response explains
the tax adjustment, distinguishes GAAP from non-GAAP, and uses operating income
when interpreting the reported decline.

The user profile and cash-only portfolio are invented. No historical quote was
collected, so the quote fixture returns `not_collected`. An order quantity cannot
be validated from this case. The reference allows a reasoned decision to wait or
to obtain more information.

## Sources and timing

- [Apple release](https://www.apple.com/newsroom/2024/10/apple-reports-fourth-quarter-results/):
  dated October 31, 2024; links the financial statements.
- [Apple financial statements](https://www.apple.com/newsroom/pdfs/fy2024-q4/FY24_Q4_Consolidated_Financial_Statements.pdf):
  page 1 contains the quarterly GAAP figures; page 4 contains the tax adjustment
  and GAAP/non-GAAP reconciliation.

The local archive holds these two original files and their download receipts.
`provenance.json` records their relative archive paths, URLs, retrieval times,
hashes, and the location supporting each evidence record. Raw files stay outside
the repository. SEC's matching exhibit was checked in the browser; its direct
download returned HTTP 403, so no SEC snapshot is claimed here.

The source date has no confirmed public release time. Availability and
`published_at` use `2024-11-01T07:00:00Z`, a conservative proxy for midnight the
next day in Los Angeles. The decision cutoff is `2024-11-01T08:00:00Z`. These are
evaluation choices, not observed publication timestamps. `fetched_at` retains the
actual later download time. The inputs exclude the later 10-K, earnings-call
content, subsequent performance, and current website navigation.

## Facts and reference checks

The three-month columns, in USD millions, contain:

| Item | FY2024 Q4 | FY2023 Q4 |
| --- | ---: | ---: |
| Revenue | 94,930 | 89,498 |
| GAAP net income | 14,736 | 22,956 |
| Operating income | 29,591 | 26,969 |
| Income tax provision | 14,874 | 4,042 |

Page 4 adds the USD 10,246 million tax adjustment to reported net income to obtain
USD 24,982 million of adjusted non-GAAP net income. The reference independently
calculates revenue growth of about 6.1%, GAAP net income decline of about 35.8%,
and operating income growth of about 9.7%.

The records are manual document and table transcriptions returned by `filings`.
They are not XBRL-tagged records, and there are no numeric matcher probes or ticket
labels. Both the tool summary and evidence contain source facts; derived growth
rates and response criteria stay in `reference.json`.

The archived PDF's first and fourth pages were rendered and checked against the
transcription during preparation. Independent team review of the transcription,
timing assumptions, and acceptance criteria is still pending. Tests check internal
consistency and record hashes; they do not establish source authenticity or replace
that review.
