# Google-Wiz announcement case

REAL-NEWS-01 uses Google's March 18, 2025 announcement of an agreement to buy Wiz.
The case checks whether the response distinguishes a signed agreement from a
completed acquisition, recognizes cash consideration and closing conditions, and
keeps expected business benefits separate from established financial results.

The [issuer announcement](https://blog.google/company-news/inside-google/company-announcements/google-agreement-acquire-wiz/)
was archived as HTML. Its transaction facts were cross-checked against
[SEC Exhibit 99.1](https://www.sec.gov/Archives/edgar/data/1652044/000165204425000027/googexhibit99131825.htm).
Direct downloading from SEC returned HTTP 403; the local snapshot is the issuer
page, and the receipt records that distinction.

## Frozen context

The reference uses the announced USD 32 billion cash consideration, subject to
closing adjustments, and pending regulatory and customary closing conditions.
The inputs contain only the dated announcement facts. Current navigation,
recommendations, subsequent deal developments, and the model's outside knowledge
do not belong to this historical snapshot.

The announcement provides a publication date. `published_at` and `available_at`
use `2025-03-19T07:00:00Z`, midnight the following day in Los Angeles, as an explicit
conservative proxy. It is not a verified first-publication timestamp. The chosen
decision time is one hour later. The actual download time remains in `fetched_at`
and the provenance manifest.

The user profile and USD 100,000 cash-only portfolio are scenario assumptions.
No historical quote or valuation series was collected; `quote` returns
`not_collected`. The case has no order-size labels. A reasoned decision to wait
or request missing evidence is acceptable.

## Review requirements

`provenance.json` binds each primary record to the archived document, a locator,
and a hash. It labels the invented account separately. These checks preserve the
collection record; they do not approve the transcript or guarantee historical
availability. Reference criteria remain `primary_source_pending_review`.

The shared news matcher checks ticker and date, not the truth of an acquisition's
completion or benefits. There are no direct matcher probes in this case. The
response criteria and later independent review assess those semantic claims.
