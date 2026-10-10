# Milestone 05 progress: export request and pre-event controls

Status on 2026-10-09: **in progress, not completed**. Authenticated CRSP sample
exports have now been inspected. Full pilot returns, vendor normalization,
historical identity approval and independent human reviews remain pending.

## Sample-access update

The [sample evidence note](../docs/wrds_sample_exports.md) and
[file receipt](market_access_samples.json) record actual daily-stock, benchmark,
capitalization, historical Names and CCM exports. File hashes match the owner's
Mac downloads. The two CCM files contain 62 rows with 47 columns each; 19 requested
CIKs match directly, while the XOM supplement carries a different header CIK.
That mismatch is unresolved and has not been rewritten into an approved mapping.
The 20 candidate securities are an export worklist, not approved historical links.

This update changes documentation and provenance receipts only. No vendor adapter,
actual event labels, fitted models or completed human reviews are added.

## Delivered

- A concrete [Cornell WRDS entitlement check](../docs/data_access_checklist.md):
  use the published student day-pass route and attempt a small daily-return export
  for AAPL in January 2021. Access to other required tables must be checked separately.
- [Exact export windows](pilot_market_request/event_windows.csv) for 135 audited-source
  filing events, plus [20 issuer envelopes](pilot_market_request/issuer_requests.csv).
  The pilot's combined date envelope is 2014-11-04 through 2021-12-28.
- A deterministic [20-event trace work queue](pilot_market_request/trace_reviews.template.csv),
  chosen without outcomes. Every verdict is pending. It supplements the existing
  30-pair filing sample and registered-reference reviews; it does not replace them.
- A standalone normalized-input control calculator: 20/60-session compounded
  momentum, 20-session sample daily volatility, logged historical USD market cap
  and an exact-date historical industry category. Missing history is rejected.

The [request manifest](pilot_market_request/export_plan.json) binds the published
files to the same Milestone 04 event queue:
`fb684e79c47928c1d4023fa3fd4e2ac5cc43b61a93ed925f81a32b658005dc0d`.
No new SEC retrieval or filing-audit run was needed because the source inputs did
not change. Request generation does not certify the queue's provenance or record
a human review.

## Verification

The cloud `make reproduce` run completed successfully: **127 tests passed**, Ruff
passed, the protocol lock matched and both synthetic engineering demos completed.
The 24 added cases cover independent control arithmetic, holiday boundaries,
missing/duplicate history, exact-date snapshots, permanent-ID separation, invalid
values/overflow, future-outcome isolation, holdout refusal and stable trace selection.
Four existing dependency deprecation warnings remain.

The primary protocol hash remains
`3951be086ed9a74ec69a304004ebcb5aed63bac161e043ff92ae4f51b8e325d9`.
There is no empirical prediction result. The existing market importer still accepts
three tables; a real snapshot adapter is not yet implemented. `prepare-labels`
continues to produce engineering labels, not a model-ready dataset.

## Remaining Milestone 05 work

1. Expand the verified samples to the pilot windows and finish source dictionaries,
   including a development-period delisting and historical identifier-change QA case.
2. Implement/review source normalization and historical snapshot availability,
   including return conventions, currency/units, identifier dates and industry.
3. Import the pilot data, join audited identities, calculate labels and controls,
   and complete independent human filing and 20-event arithmetic traces.
4. Resolve exclusions and document their counts before the end-to-end pilot study.

The 20-issuer sample remains a document-format pilot, not the historical investment
universe. Final-period 2022-2025 filing events remain blocked from development.
