# Milestone 05 progress: pilot labels, controls and review evidence

Status on 2026-10-10: **in progress, not completed**. Authenticated CRSP sample
and full pilot exports have been inspected and staged in Parquet/DuckDB. Automated
WFM terminal-return and GE identifier-change cases pass. Historical identity
approval, source-release/availability and independent human reviews remain pending.
The new arithmetic/review workflow runs end to end: **135 of 135 provisional
candidate cases pass**, with **20 fixed review traces** and zero calculation
failures. Milestone 05 is not fully signed off while the reviews below are pending.

## Sample-access update

The [sample evidence note](../docs/wrds_sample_exports.md) and
[file receipt](market_access_samples.json) record actual daily-stock, benchmark,
capitalization, historical Names and CCM exports. All eleven CSV/SQL files have verified
private archive copies on the owner's Mac. The pilot Names CSV was archived from
the supplied attachment; the other ten match original Mac downloads. The two
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
All pilot delisting flags are `N`. The [WFM check](../docs/wrds_delisting_check.md)
now passes with a separate PERMNO export: the same ten ordinary rows plus the
28 August 2017 terminal observation. Original query 11769187 confirms the requested
dates and ticker filter; the added row has a blank ticker. Independent cash-return
arithmetic agrees within delivered rounding, and two 20-session QA windows verify
cash continuation. The incomplete original export remains a negative control.
The daily export's SQL, query ID and exact release date remain
unknown. Coverage checks do not approve historical CIK mappings or calculate labels.

The new [CIZ source-staging command](../docs/crsp_staging.md) converts the pilot to
36,000 return rows, 1,800 benchmark rows and 36,000 dated snapshots. It preserves
literal source flags, converts thousands to USD and joins historical SIC, while
explicitly retaining incomplete source/identity/terminal audit status. It creates
no approved CIK links or import-ready manifest. Staging itself adds no labels,
fitted models or completed human reviews. The separate conditional arithmetic
workflow below now calculates candidate labels and controls for review.

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

- A source-bound [pilot arithmetic workflow](../docs/pilot_arithmetic_review.md)
  combining event clocks, dated candidate identities, returns and control snapshots.
  All 135 cases reconcile seven numeric measures to independent Decimal calculations
  from the original CSV values. Maximum absolute difference: **1.43e-15**, against
  a **1e-12** tolerance. Dated industry matches too. No reference-day label leakage,
  benchmark filling, missing-return filling or automatic identity approval is used.
- Twenty readable trace cases with 60 control sessions, 20 label sessions, exact
  CSV record numbers, historical snapshot evidence and pending review templates.
  Optional review ingestion rejects unknown, duplicate or stale evidence and
  counts human and assistant declarations separately. The existing filing and
  identity reviews remain distinct requirements.
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

The latest cloud `make reproduce` passes **190 tests**, Ruff, the frozen protocol
and both synthetic demos. Eleven new cases cover independent source arithmetic,
changed evidence, holdout refusal, ambiguous candidates, incorrect units, preserved
outputs and review-declaration handling.

The [aggregate arithmetic receipt](pilot_arithmetic_summary.json) records the actual
135-case run, zero blocked calculations, fixed review selection and source/output
hashes. Seven Exxon header-CIK differences and all 135 unresolved link end markers
remain explicit. Detailed values, source rows, Parquet/DuckDB and HTML stay private.

The WFM source script verifies all 11 observations, unchanged delivered returns,
missing terminal capitalization and two independently compounded QA windows. The
28 CIZ tests pass, including a new invented-data regression for a blank ticker and
zero DA price. The original staging receipt is unchanged; terminal follow-up
evidence is recorded separately in [wfm_terminal_check.json](wfm_terminal_check.json).

The preceding cloud `make reproduce` run passed **178 tests**, Ruff, the protocol
lock and both synthetic demos. The 24 new identity-review cases cover original
CIKs and annual-pair binding, changed evidence, non-ticker candidate discovery,
interior gaps and ambiguous histories, unresolved end markers, cache/header
identity errors, holdout refusal, escaped HTML and deterministic CLI reproduction.

The preceding cloud `make reproduce` run passed **154 tests**, Ruff, the protocol
lock and both synthetic demos. The 27 additional cases cover CIZ flags, the
missing-terminal tail, unchanged terminal returns, cash after termination,
capitalization units, historical industry boundaries, rejected ambiguous data,
holdout refusal and preservation of prior staging. The actual pilot was staged
successfully with zero coverage gaps; actual-source terminal QA was incomplete at
that checkpoint and is now documented in the WFM follow-up above.

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

1. Finish exact source dictionaries and release/query metadata. Pilot coverage,
   WFM terminal cash handling and GE's identifier-change case pass automated checks;
   independent review remains pending.
2. Review the implemented daily/Names normalization and historical snapshot
   availability; finish approved historical CIK/CCM links and explicit end-marker bounds.
3. Complete independent human filing and 20-event arithmetic reviews. The source-bound
   calculations and review-ingestion code now exist; no human verdict has been supplied.
4. After identities/source assumptions are approved, promote the reviewed inputs
   through the normalized importer. Finalize study exclusions and their reasons;
   zero arithmetic failures does not imply zero final research exclusions.

The 20-issuer sample remains a document-format pilot, not the historical investment
universe. Final-period 2022-2025 filing events remain blocked from development.
