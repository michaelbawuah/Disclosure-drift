# Pilot market export and trace review

The initial [Cornell entitlement check](data_access_checklist.md) has passed for
the [observed sample query outputs](wrds_sample_exports.md). Broader data coverage
and historical identity verification remain pending.
The published [request summary](../reports/pilot_market_request/export_plan.json)
and CSV files describe required dates, not completed CRSP exports.

Generate a fresh request from the Milestone 04 audit-bound event queue:

```bash
uv run --locked disclosure plan-market-export \
  --events data/processed/pilot-resolved/label_events.parquet \
  --output outputs/pilot-market-request
```

The output directory must be new. The command checks development-year events,
retains source-evidence fingerprints and binds the request to the event-file hash
and frozen protocol. It does not rerun the filing audit or certify the input's
provenance declarations. Recreate the queue with `export-label-events` after any
source or review change.

| Output | Use |
|---|---|
| `event_windows.csv` | Each filing's exact control, entry and label dates |
| `issuer_requests.csv` | Per-CIK date envelope for a convenient pilot export |
| `trace_reviews.template.csv` | 20 outcome-independent event traces, all pending |
| `export_plan.json` | Counts, source/protocol fingerprints and output hashes |

The issuer envelopes include intervening dates between events. The event file is
the precise list of needed windows. This purposive 20-issuer parser pilot is not
a historical investment universe; successful checks do not establish survivorship
or full-universe coverage.

## What to obtain once the sample query works

Use the subscription's actual dictionary to identify these fields; no unverified
WRDS table names or source-field aliases are assumed:

- Permanent security identifiers and historically dated issuer/CIK links, with
  share-class eligibility and link validity. A current ticker match is insufficient.
- Daily total returns from each control-history start through each label end,
  plus delisting events/payoffs and original missing/quality flags.
- Daily market total returns from the first label session through label end,
  from the declared value-weighted benchmark.
- Market cap (or documented price and shares), currency/units, and historically
  dated industry records sufficient to construct the exact controls-day snapshot.
- Source release, query specification, extraction time, table dictionary and
  normalization decisions, including whether delisting is already in returns.

The documented **development-period delisting** and historical identifier-change
examples now pass automated vendor-adapter QA: [WFM's cash merger](wrds_delisting_check.md)
and [GE's CUSIP transition](identity_source_evidence.md). They do not replace
independent review or approve the pilot's historical links. Broader year-start
liquidity-universe exports are a later request and also require historical price,
volume, security-type and listing data.

## Controls calculation now available

`controls.make_controls` accepts normalized returns for one permanent security
and dated snapshots with `security_id`, `session`, `market_cap_usd`, `industry`,
and `industry_scheme`. It produces:

- `momentum_20` and `momentum_60`: compounded total returns over exactly 20/60
  XNYS sessions, ending at the close before the reference session.
- `volatility_20`: unannualized sample standard deviation of those last 20
  daily total returns (`ddof=1`).
- `log_market_cap`: natural log of positive historical capitalization in USD.
- `industry`: the exact controls-date category, retaining its scheme for audit.

No missing return or snapshot is filled. The function rejects duplicate history,
mixed security IDs and already terminated securities. It does not inspect future
return values to calculate controls. Tests compare against independent arithmetic
and deliberately alter future returns, terminal events and classifications.

This is a standalone normalized-input calculator. The separate [CIZ adapter](crsp_staging.md)
now stages actual capitalization and dated-industry snapshots, with unit conversion.
Source-release/availability and historical identity approval remain pending. The
three-table market importer has not gained a fourth table, and `prepare-labels`
still stages labels only.

## Human trace audit

Copy the 20-row template to a working file; generated `pending` values are not
review completion. For each event, independently check the SEC acceptance evidence,
historical CIK/security link, calendar boundaries, all 60 control returns, exact-date
snapshot, 20 subsequent label returns, benchmark and any delisting payoff. Record
the raw export/row references and independent arithmetic in review notes.

The template is a work queue, not an executable approval gate. No command currently
accepts it as authorization to model. Complete the separate 30-pair filing review
and registered-reference review as well; retain failed examples and exclusions.
No development experiment or final-period evaluation is authorized by this packet.

The [pilot arithmetic command](pilot_arithmetic_review.md) now generates the actual
20-case reading packet, independent calculations, raw row references and new
evidence-bound JSONL review templates. Its optional `--reviews` input records human
and assistant declarations separately and rejects stale evidence. Those declarations
do not approve historical identities or authorize modeling.
