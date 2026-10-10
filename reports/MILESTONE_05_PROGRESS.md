# Milestone 05 progress: export request and pre-event controls

Status on 2026-10-10: **in progress, not completed**. Authenticated CRSP sample
and full pilot exports have been inspected and staged in Parquet/DuckDB. Delisting QA,
historical identity approval and independent human reviews remain pending.

## Sample-access update

The [sample evidence note](../docs/wrds_sample_exports.md) and
[file receipt](market_access_samples.json) record actual daily-stock, benchmark,
capitalization, historical Names and CCM exports. All ten files have verified
private archive copies on the owner's Mac. The pilot Names CSV was archived from
the supplied attachment; the other nine match original Mac downloads. The two
CCM files contain 62 rows with 47 columns each; 19 requested
CIKs match directly, while the XOM supplement carries a different header CIK.
SEC corporate sources now document both identities and their July 2026
reorganization; historical mapping approval remains pending.
The 20 candidate securities are an export worklist, not approved historical links.

The full historical Names export is now received: **237 records, 24 columns,
all 20 requested PERMNOs**, with matching vendor SQL. No duplicate keys, invalid
date intervals, gaps or overlaps were found. All **540** requested event boundary
dates have exactly one candidate security-description record. At **76 of 135**
controls dates, dated SIC differs from header SIC. These checks establish source
coverage and the need for dated industry joins, not approval of historical CIKs.

The full daily export is received: **36,000 rows, 20 securities, 1,800 sessions
each**, with all ten requested columns. There are no missing or duplicate
security/session rows, invalid returns or nonpositive capitalization values. The
benchmark is consistent across all securities, and every daily row joins one
dated Names record. All 135 candidate event windows have complete source coverage
(8,100 control-session, 135 entry-reference and 2,700 label-session checks).
All pilot delisting flags are `N`. The [received WFM check](../docs/wrds_delisting_check.md)
also has only N flags: ten ordinary rows ending 25 August 2017, with no terminal
payment. Its SQL or submitted parameters are needed to diagnose the omission.
The daily export's SQL, query ID and exact release date remain
unknown. Coverage checks do not approve historical CIK mappings or calculate labels.

The new [CIZ source-staging command](../docs/crsp_staging.md) converts the pilot to
36,000 return rows, 1,800 benchmark rows and 36,000 dated snapshots. It preserves
literal source flags, converts thousands to USD and joins historical SIC, while
explicitly retaining incomplete source/identity/terminal audit status. It creates
no approved CIK links or import-ready manifest. No actual event labels, fitted
models or completed human reviews are added.

The [historical identity review packet](../docs/identity_review.md) now covers all
135 events and rechecks 155 cached SEC headers, all consistent with the original
filer CIK, accession and form. Each event has one candidate security, with 10,935
required session checks covered by one dated Names record and matching PERMCO.
Seven Exxon events explicitly retain the historical/CCM-header CIK disagreement.
All 135 candidate `E` end markers and historical identity verdicts remain pending.
The [aggregate receipt](identity_pilot_summary.json) publishes counts and hashes;
the detailed HTML, source rows and review templates stay private. No returns were
loaded by this command, and no independent human review is claimed.

The [corporate-source follow-up](../docs/identity_source_evidence.md) documents
Exxon's original and successor CIKs/CUSIPs. It also checks GE's August 2021 CUSIP
transition using the existing files: ten sessions, two contiguous Names intervals,
stable permanent IDs and unchanged staged returns. Five pre-change sessions have
a current header CUSIP that differs from the dated CUSIP. The
[aggregate receipt](ge_identifier_check.json) records this passing automated case;
split-return arithmetic, historical-link approval and human review remain separate.

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

The latest cloud `make reproduce` run passes **178 tests**, Ruff, the protocol
lock and both synthetic demos. The 24 new identity-review cases cover original
CIKs and annual-pair binding, changed evidence, non-ticker candidate discovery,
interior gaps and ambiguous histories, unresolved end markers, cache/header
identity errors, holdout refusal, escaped HTML and deterministic CLI reproduction.

The preceding cloud `make reproduce` run passed **154 tests**, Ruff, the protocol
lock and both synthetic demos. The 27 additional cases cover CIZ flags, the
missing-terminal tail, unchanged terminal returns, cash after termination,
capitalization units, historical industry boundaries, rejected ambiguous data,
holdout refusal and preservation of prior staging. The actual pilot was staged
successfully with zero coverage gaps; actual-source terminal QA remains incomplete.

The prior cloud `make reproduce` run completed successfully: **127 tests passed**, Ruff
passed, the protocol lock matched and both synthetic engineering demos completed.
The 24 added cases cover independent control arithmetic, holiday boundaries,
missing/duplicate history, exact-date snapshots, permanent-ID separation, invalid
values/overflow, future-outcome isolation, holdout refusal and stable trace selection.
Four existing dependency deprecation warnings remain.

The primary protocol hash remains
`3951be086ed9a74ec69a304004ebcb5aed63bac161e043ff92ae4f51b8e325d9`.
There is no empirical prediction result. The existing market importer still accepts
three approved-input tables; the separate CIZ adapter produces source staging with
unresolved audit gates. `prepare-labels`
continues to produce engineering labels, not a model-ready dataset.

## Remaining Milestone 05 work

1. Finish source dictionaries and release/query metadata, including a development-period
   delisting case. Pilot coverage and GE's automated identifier-change check are verified;
   independent review remains pending.
2. Implement/review source normalization and historical snapshot availability,
   including return conventions, currency/units, identifier dates and industry.
3. Import the pilot data, join audited identities, calculate labels and controls,
   and complete independent human filing and 20-event arithmetic traces.
4. Resolve exclusions and document their counts before the end-to-end pilot study.

The 20-issuer sample remains a document-format pilot, not the historical investment
universe. Final-period 2022-2025 filing events remain blocked from development.
