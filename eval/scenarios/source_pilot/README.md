# Primary-source development cases

This collection starts the real-evidence work with one earnings case and one news
case. It is separate from the ten synthetic pilot scenarios and is not the full
dataset promised in the proposal. Both cases still need independent review.

| Case | Evidence | What the response must distinguish |
| --- | --- | --- |
| [REAL-EARN-01](apple_2024_q4/README.md) | Apple FY2024 Q4 release and financial tables | GAAP profit, adjusted profit, operating performance, and missing investment evidence |
| [REAL-NEWS-01](google_wiz_2025_03/README.md) | Google announcement of the proposed Wiz acquisition | Agreement versus completion, conditions, and expected versus established benefits |

Company facts come from official publications. User profiles and portfolios are
invented and labeled as assumptions. Historical prices were not collected, so
neither case supports a validated order size. The quote fixtures record that gap
instead of substituting a made-up price. These two cases do not test the complete
market-data path or establish memory effects.

## Archive and provenance

Each case has `inputs.json`, `reference.json`, and `provenance.json`. The manifest
records publication dates, conservative availability proxies, actual retrieval
times, URLs, file hashes, evidence locations, and assumed records. Original HTML
and PDF files stay in an external local archive. Pass its root explicitly; no
private absolute path is stored in a tracked fixture or run manifest.

The loader rejects missing or changed archives, mismatched IDs, unmapped records,
invalid source URLs, inconsistent times, and paths outside the supplied archive.
It preserves the original manifest in run and review outputs. A passing check
establishes file and metadata consistency, not the accuracy of a source or a
human-reviewed reference label. Review and approval state remains pending.

The snapshots were downloaded after the historical scenario dates. Only dated
publication content enters the inputs. Exact first-publication times were not
established; the next-day cutoff is an explicit study assumption. SEC excerpts
were checked in the browser, but their direct downloads returned 403. The stored
originals are the corresponding issuer files. Receipts preserve these outcomes.

## Local checks

Set `TRADECOPILOT_EVIDENCE_ROOT` to the directory containing the three archived
issuer files named in the manifests. From `eval/`, validate without network calls:

```sh
uv run --locked --offline python -m tradecopilot_eval validate \
  --suite suites/source-pilot.json \
  --evidence-root "$TRADECOPILOT_EVIDENCE_ROOT"
```

The following runs each of the two cases once with full memory and predefined
responses. The schedule has no ablation trials. Choose a new output directory:

```sh
uv run --locked --offline python -m tradecopilot_eval run \
  --suite suites/source-pilot.json \
  --evidence-root "$TRADECOPILOT_EVIDENCE_ROOT" \
  --mode scripted --output /tmp/tradecopilot-source-smoke
```

To export the two source cases with DEV-01, DEV-02, and the existing four blind
calibration responses:

```sh
uv run --locked --offline python -m tradecopilot_eval reference-review \
  --suite suites/source-pilot.json \
  --evidence-root "$TRADECOPILOT_EVIDENCE_ROOT" \
  --output /tmp/tradecopilot-source-review
```

Development model checks can run with explicit model-call opt-in while source
review is pending. Keep their results and reference labels provisional. Before
freezing the ten-case study, review source locations, transcription, timing
assumptions, and acceptable outcomes, and collect the missing evidence needed
for the final scenario design. Another team member can provide an independent
check; preserve original reviews and record revisions. AI checks can assist,
but do not count as human review.
