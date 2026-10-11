# Research execution update — October 11, 2026 (UTC)

**Latest result: two specific Names-history questions are resolved.** The Mac
run at `16ca9e5fb1b76fa5fb149c58e64976b8b88935a1` scanned all **191,048 original
Names rows** and found unique descriptors at all **16,974 role/date observations**
for the **207 existing filing discoveries**. All **15 January-snapshot date gaps**
have applicable records in the complete history. The run finished in
**2.272097 seconds**, preserving all original discovery rows and **215 filing
coverage rows**, including **eight unmatched original Exxon filings**.

The separate **1.464616-second** lifetime check explains all **1,341 liquidity-only
annual observations**: every matching Names occurrence reports a security
lifetime ending before selection. That includes **490 numerical-minimum passes**
and **851 failures**; prior-window liquidity does not imply a January descriptor.
The original rows remain preserved, with no approved exclusions or historical
availability inference. The [measured results](../docs/dated_names_results.md),
[execution bindings](names_history_execution.json) and
[verification](names_history_verification.json) document these conclusions.
The complete software reproduction passed **974 tests**, Ruff and the full
synthetic study; implementation CI also passed.

The [public SEC source demonstration](../docs/public_historical_identity_sources.md)
adds dated issuer-corroboration routes, and the
[recovered CRSP manuals](../docs/benchmark_primary_definitions.md) identify the
native benchmark specification to check against the saved WRDS views. Neither
investigation establishes an approved historical crosswalk or source vintage;
**all 52 benchmark discrepancy causes remain unresolved**. The **46,359
observations with one usable current-header CIK** and **3,871 other rank-eligible identity cases**
remain as recorded in the foundation. Empirical milestones **5–11 remain pending**.

The new [local filing-review page](filing_review/index.html) now brings the fixed
30 pairs and all 24 matching reference cases into one 73-filing queue. It retains
the original sample and evidence IDs, saves portable drafts and exports explicitly
recorded decisions for the existing source audit. The production build created
zero human reviews. See the [Mac guide](../docs/filing_review.md),
[bound execution receipt](filing_review/execution.json) and
[implementation verification](filing_review/verification.json).

**October 11 assistant-review completion:** With Michael Baffour Awuah's
authorization, assistant boundary/timing review now covers all **73 filings**.
The [completion folder](filing_review/assistant/README.md) preserves the 63 prior
records without changing their eight audit fields or review times and adds ten
new source-backed passes. Separate source/timing inspection verifies 73 clocks,
30 annual-pair relationships within the preserved cohort and 152 cached source
bodies. No human review was created. The original pending packet and generation
receipt remain unchanged; the user does not need to repeat these assistant
checks manually. The existing 20/20 user numerical review remains credited.
The [new source-audit execution](filing_review/assistant/execution.json) then
reopened the original 155-filing cohort: 155 automated consistency passes,
73 accepted assistant reviews, zero blocking issues, all 155 evidence IDs
unchanged, and a byte-identical fixed 30-pair selection. It completed at
`2026-10-11T09:55:36.521815+00:00` in 107.833 seconds.
The completed bundle was also copied to the Mac, where its 15 portable file
hashes, 73 assistant records and 63 preserved prior records matched. Actual
isolated Chrome checks passed at 1440 and 390 pixels, including expandable
review notes and no page-level horizontal overflow. Source tables were absent
from that Mac checkout, so the original-byte audit is credited to the research
workspace, not the Mac. The [completion verification](filing_review/assistant_verification.json)
preserves this distinction and the evidence-commit CI status.

**October 11 historical-foundation reconciliation:** The full saved-data run on
the Mac completed at **10:38:20.651697 UTC** in **48.393520 seconds**, under commit
`710fa6833055c13224805bf28dbb445f24af976d`. It retains **87,405 annual security
observations**, including all **86,064 identity rows** and **1,341 liquidity-only
rows**. The latter include **490 numerical-minimum passes**; the subsequent
full-history check explains their absent January descriptors by recorded
security lifetimes ending before selection. The foundation run verifies
**110,124 CCM source occurrences** and **100,261 existing Names/CCM relationships**,
binds **207 discoveries** to the previously
verified SEC report, and preserves all **215 filings**, including eight unmatched
original Exxon filings. The original 73 assistant and 20/20 user review receipts
remain byte-identical.

The new [identity/liquidity cross-tab](historical_foundation_aggregate.json)
partitions the **50,230 rank-eligible annual observations** into **46,359** with
one usable current-header CIK, **1,315** with one missing/unsupported header CIK,
**2,489** with multiple/ambiguous candidates, **37** with dated context but no
January 1 candidate and **30** without a related CCM record. Thus **3,871 (7.71%)**
need basic candidate resolution, while all single-header cases still require
historical identity and availability evidence. The [foundation guide](../docs/historical_foundation.md)
explains finite/open bounds, the 627 class-observation records (including 130
explicit no-inline-fact placeholders), and the 15 January descriptors that do
not cover their later filing dates. Their full-history descriptor coverage is
now resolved in the separate [dated Names result](dated_names_aggregate.json).
The sole literal ticker difference was traced to a leading line feed in
[Tesla's original TradingSymbol tag](tesla_symbol_clarification.json); the raw
comparison and all source observations remain unchanged.

A separate [public revision check](historical_revision_case.json) verifies that
all four saved 2016–2019 January snapshots in the selected vendor correction
interval disagree with at least one corrected classification literal. That
finding supplies no source-version identification or automatic correction.
The [availability assessment](../docs/historical_availability_evidence.md)
specifies the historical-CIK, version and date-semantics evidence needed next.
Seven additional [original filing-cover inspections](sec_cover_cases_summary.json)
retain common stock, debt, share classes and co-filers separately.

The earlier [foundation implementation verification](historical_foundation_verification.json)
records **949 passing tests**, Ruff, the unchanged protocol and the complete
synthetic study. These validate the software and source reconciliation; they do
not complete the empirical milestones or supply an investment-universe approval.

**The empirical forecasting study remains unfinished.** Security-universe
completeness, source normalization and judgments, actual development selection,
final estimates, robustness interpretation and independent-person reproduction
are still needed.
The primary protocol is unchanged and the actual 2022–2025 evaluation remains unopened.

## Completed in this execution

| Work | Observed result | Evidence |
|---|---|---|
| Resolve complete-history filing descriptors | **207 discoveries / 16,974 role/date observations**, all with unique records; **15/15** snapshot-date questions resolved; 65 original source occurrences retained | [Dated aggregate](dated_names_aggregate.json) |
| Explain liquidity-only annual metadata | All **1,341 annual observations** have saved security lifetimes ending before selection; **7,683** source-row references retained; no exclusion approved | [Lifetime aggregate](liquidity_only_names_aggregate.json) |
| Expand the SEC pilot | 60 additional original filings from 15 issuers; 45 new consecutive annual pairs | [Collection receipt](pilot_expansion/expansion_ingestion_summary.json) |
| Meet the planned time-window count | **104 pairs accepted in 2019–2021**, within the planned 100–150 range | [Expanded checkpoint](pilot_expansion/pilot_checkpoint.json) |
| Rebuild the combined source audit | **215 filings, 180 pairs, 35 issuers; 215 automated passes and zero blocking findings** | [Combination receipt](pilot_expansion/combination_receipt.json) |
| Preserve existing work | Original 155 extracted texts, counts, statuses and versions unchanged; all original 135 pairs retained | [Parser impact](pilot_expansion/parser_impact.json) |
| Record the completed user review | **20/20 independent arithmetic and printed-timing passes**, tied to the exact original packet | [User review receipt](review_progress/user_arithmetic_receipt.json) |
| Execute actual MiniLM | **155 real filing texts, 135 pairs, 1,459,865 WordPiece tokens, 5,828 chunks, zero truncation** | [Semantic execution report](semantic_validation/report.md) |
| Reproduce actual inference | Two independent processes produced identical vectors for every document and identical pair features | [Replication receipt](semantic_validation/independent_replication.json) |
| Prepare full historical collection | Account-catalog inspection, explicit source bindings, bounded monthly exports, source hashes, resumable checkpoints and offline assembly | [WRDS execution guide](../docs/wrds_full_export.md) |
| Preserve development market sources | Four daily batches cover the requested dates 2009-10-07–2022-02-02; Names, combined CCM/company metadata and the independent benchmark are saved locally | [Manual export and inventory guide](../docs/wrds_daypass_export.md); private byte-preserving source copies and inventory receipts |
| Execute development source staging | **23,007,130 daily source rows preserved; 22,593,113 within the requested window; all 3,103 expected sessions covered**. Exact benchmark reconciliation remains false on 52 dates | [Source-stage contract](../docs/wrds_manual_stage.md); private production receipt for code `e431818`, completed `2026-10-10T23:29:19.102375Z` |
| Build provisional development numerics | **22,588,059 distinct 13-field candidate rows; 5,054 repeated-record excesses; zero conflicting security/date keys**. Return, capitalization and price-volume candidates remain unapproved | [Numerical candidate contract](../docs/wrds_manual_candidates.md); private `development-v2` receipt for code `0d555a3`, completed `2026-10-10T23:53:20.954933Z` |
| Build dated Names evidence | **86,064 annual record/year snapshots; 50,777 narrow ordinary-corporate-common candidates; zero ambiguous security/year groups**. Every `known_at` remains null | [Listing-candidate contract](../docs/wrds_listing_candidates.md); private production receipt for code `1418e0e`, completed `2026-10-10T23:55:34.077882Z` |
| Audit the benchmark discrepancies | The formal audit confirms **52 dates**, each with an absolute decimal difference of **0.000001**; source cause and reconciliation remain unresolved | Private benchmark-audit receipt for code `1418e0e`, completed `2026-10-10T23:56:11.211984Z` |
| Execute annual liquidity processing | **87,405 security/year records; 84,530 meet the numerical minimum; 50,230 receive provisional security ranks**. No issuer grouping or 500-issuer selection | [Liquidity-candidate contract](../docs/wrds_liquidity_candidates.md); private production receipt for code `ae4e0c`, completed `2026-10-11T00:10:00.938349Z` |
| Bind benchmark source evidence | **All five audited sources retained; one saved SQL source and one source with supplied query-display evidence**. Exact discrepancy diagnostics reproduced; 52 dates remain unresolved | [Aggregate execution record](wrds_benchmark_source_evidence_execution.json); code `5bbfa2c`, completed `2026-10-11T00:55:20.317245+00:00` |
| Organize annual historical-identity evidence | **110,124 CCM records retained; 100,261 Names/CCM relationships; 86,064 annual security records; all 215 SEC manifest rows accounted for**. Header-CIK matches are discovery only | [Aggregate execution record](wrds_identity_evidence_execution.json); code `5f9a451`, completed `2026-10-11T00:58:52.177677+00:00` |
| Corroborate original SEC identities | **215 primary/header/acceptance checks; 218 filer observations; three co-filings; 1,494 lexical cover facts from 79 filings**. No approved security links | [Execution and reconciliation record](sec_identity_evidence_execution.json); [complete compressed evidence](sec_identity_evidence.json.gz); code `3a5b368`, completed `2026-10-11T01:49:28.800315+00:00` |
| Inspect unmatched discovery context | **All 215 manifest records verified; 207 discovery matches; eight unmatched original Exxon filings**, subsequently bound to the original-source report | [Public discovery context](sec_identity_discovery_context.json); code `3a5b368`, completed `2026-10-11T01:51:48.599817+00:00` |
| Build the portable filing-review page | **30 fixed pairs / 58 fixed filings; 24 matching reference cases; nine shared cases; 73 distinct filings**. Complete extracted risk text and original SEC links; no decisions created | [Packet receipt](filing_review/receipt.json); code `677eff5`, completed `2026-10-11T02:40:22.581723+00:00` |
| Verify the review-page software checkpoint | **893 tests passed; Ruff passed; complete synthetic study completed**. The 44 new filing-review cases preserve source and review gates. Actual isolated Mac Chrome checks passed for draft/export behavior and desktop/mobile layouts | [Review-page verification](filing_review/verification.json); [earlier verification baseline](execution_verification.json) |

The combined pilot preserves 19 source-specific reference resolutions and 104
API/header timestamp differences. The original SGML acceptance timestamp remains
the event clock. Counts and source reproduction do not approve historical market
identity or public dissemination assumptions.

## What real-source execution corrected

The added filings exposed layout errors that were invisible in the earlier sample.
Ford prints continuation headings on each risk page. Treating those as fresh
sections retained only the last page: for example, the 2018 filing grew from 846
to 4,036 extracted tokens after the correction. The revised path preserves the
unchanged normalizer and records a new extraction version only when a continuation
heading is present.

Mastercard repeats unmarked Item 1A running headers. Its two flagged filings now
use exact source-bound ranges through the first substantive Item 1B boundary.
McDonald's places the risk section separately from its form index; the recorded
scope selects the labeled Risk Factors block and excludes a separate general
cautionary statement. Honeywell's index gives a page-24 pointer; its complete
risk block ends before the following quantitative market-risk section on page 32.

All five new registered ranges have independently inspected assistant records,
with original URLs, file hashes, offsets and resulting text hashes. These are
explicit extraction and assistant-review records. The remaining human boundary
review can assess the documented scope decisions. See
[the source correction guide](../docs/pilot_expansion.md) and
[five-case review receipt](review_progress/expansion_scope_review_v2.json).

Independent code review also found that a combination helper could copy an
unexpected market-data column. It now checks an explicit SEC-only schema before
deserializing tables, and dates, text and hashes come from the same immutable
byte snapshot. Regression tests reproduce both accidental outcome columns and
source mutation after the date check.

## Your completed numerical review

The prior 20/20 verdict is a completed user judgment about arithmetic and printed
packet structure. The unchanged submitted script reproduces the saved results,
with maximum absolute difference `1.27675647831893e-15`, and catches a return
changed by 0.0001. Its exact original timestamp was not recovered; the recorded
review time remains unknown, separately from the assistant's later recording time.

The new record does not ask for those 20 checks again. It also does not silently
extend that verdict to security identity, vendor vintage, source-row inspection,
or filing boundaries. Assistant investigation separately checked 63 original
filing boundaries and all 155 original SGML clocks, recovered the supplied Names
SQL, and added original registration evidence for seven flagged Exxon filings.
Historical CIK discrepancies, CCM open-end interpretation and release evidence
remain unresolved. See [review progress](../docs/review_progress.md).

## Actual semantic validation and its limits

The exact pinned MiniLM weights and all five tokenizer/configuration artifacts
matched their prescribed hashes. Every content token was processed in chunks
of at most 254 tokens plus two special tokens. The actual run used CPU float32,
evaluation mode and one thread; unique-document inference took 468.774 seconds
on this machine. That runtime is an observed execution measurement.

Three source documents selected before inference passed repeated-encoding and
batch-size checks. The largest coordinate difference between batches of one
and sixteen was `4.74e-9`, below the preset `1e-6` tolerance. Two independent
Python processes then agreed exactly on all document vectors and pair features.
The actual execution exposed and fixed the Transformers 5 tokenizer interface
change without decoding and retokenizing chunk IDs.

The median semantic distance was **0.00632819**, with a 10th–90th percentile
range of **0.00268151–0.01756768**. These are descriptive text distances without
a calibrated economic interpretation. The semantic validation uses the original
135-pair pilot; the expanded 180-pair text checkpoint is a separate artifact.
This retrospective checkpoint has unverified training-data cutoffs and supplies
no evidence that it was available during the historical investment period.
Named human semantic judgments and any empirical semantic comparison remain open.

Sources: [actual semantic report](semantic_validation/report.md),
[all 135 pair distances](semantic_validation/all_pair_distances.csv), and
[exact runtime/source receipt](semantic_validation/validation_receipt.json).

Execution used the working-tree implementation recorded by its per-file hashes.
The semantic receipt's `code_commit` records the parent Git HEAD present during
the run; the then-uncommitted validator was not yet part of that parent commit.
The delivered implementation files match the recorded execution hashes.

## Actual development source staging

The local production stage using code `e431818` completed at
**2026-10-10T23:29:19.102375Z**, with exit status **0** after **172.8 seconds**.
The private execution receipt records the following aggregate results. No licensed
source rows or security identifiers are reproduced here.

| Check | Observed result |
|---|---:|
| Preserved daily rows, including repeated records | 23,007,130 |
| Extra early rows preserved outside the requested window | 414,017 |
| Daily rows within 2009-10-07–2022-02-02 | 22,593,113 |
| Expected XNYS sessions covered | 3,103 / 3,103 |
| Parquet parts / total bytes | 1,277 / 506,932,005 |
| Overlap between requested batch dates | 0 |
| Attached benchmark rows exactly matching the independent benchmark | 22,216,260 |
| Attached benchmark rows with unequal values | 376,853 across 52 dates |
| Invalid benchmark cells / missing benchmark observations / within-date conflicts | 0 / 0 / 0 |

The stage completed its preservation and checks, but
`requested_window_numerically_reconciled` remains **false**. The formal audit
below confirmed an absolute benchmark difference of exactly **0.000001** on
each of the 52 dates. The cause has not been established, and no rounding or
tolerance policy has been accepted. This comparison concerns the benchmark
attached to daily records; it does not establish an error in any individual
stock return. The independent source has not been silently replaced.

### Completed provisional numerical build

The revised [numerical consumer](../docs/wrds_manual_candidates.md), code
`0d555a373b6de54e86914af70ae1c87cb02f9852`, completed successfully from
`2026-10-10T23:47:07.796699Z` to `2026-10-10T23:53:20.954933Z`: **373.15 seconds**,
exit status **0**. Its private bundle is
`data/private/wrds-candidates/development-v2`; the successful receipt SHA-256 is
`b1d6b92ca73f4a087d1ed5e19ab09c37d98e9d16c418a17a315b58f4ea012e60`.

| Candidate production check | Observed result |
|---|---:|
| Requested source rows consumed | 22,593,113 |
| Distinct exact 13-field candidate rows | 22,588,059 |
| Exact repeated-record excesses removed from the candidate projection | 5,054 |
| Conflicting security/date keys | 0 |
| Expected sessions covered / missing / unexpected | 3,103 / 0 / 0 |
| Output parts / total bytes | 91 / 1,587,431,523 |
| Calendar-month partitions | 149 |
| DuckDB memory limit / threads | 1 GB / 2 |

The **414,017 extra early rows remain preserved upstream** and do not enter the
requested numerical candidates. Deduplication compares only the 13 required
raw fields; it does not certify equality over the wider delivered files.

| Numerical candidate | Values produced | Rows withheld and reason |
|---|---:|---|
| Total return | 22,363,175 | 224,884 with unresolved return flags |
| Market capitalization in USD | 22,366,433 | 221,626 with missing capitalization |
| Closing-price × volume proxy in USD | 22,366,383 | 50 with missing input and 221,626 with unsupported price flags |

The return-withholding count includes **80 `MV` rows**, which remain unresolved
even when a numeric value is present. **5,413 `Y` delisting-flag rows** still
require payoff/termination review; no terminal event or post-delisting cash
behavior was inferred. These are applications of the documented
[candidate policies](../docs/wrds_source_conventions.md), not vendor-release or
source-availability approvals. Benchmark reconciliation remains **false**. The
output creates no CIK mapping, historical availability timestamp, labels,
forecasts, or final-period access, and remains `model_ready: false`.

The first production attempt, using `e5e206`, ran from
`2026-10-10T23:35:16.453460Z` to `2026-10-10T23:35:57.835092Z` and failed after
**41.38 seconds** with an `OutOfMemoryException` under the 1 GB DuckDB memory
limit. It produced no successful candidate bundle. The successful rerun uses
bounded monthly grouping and streaming source-record uniqueness checks. The
earlier failed run remains part of the execution record.

The earlier **2016-01-01–2022-02-02** daily inventory covered all
**1,533 expected XNYS sessions**: **11,790,771 rows**,
**12,259 distinct PERMNOs**, and **96 delivered columns** in **7,092,279,548 bytes**.
Its SHA-256 is
`c5609c9375fca7cd8138efac54ef6e94ab1d53bd6b615479f041ec96c34d1a06`.
The required 13-field projection contains **2,406 exact repeated-row excesses**
across **2,322 repeated security/date keys**, with **zero conflicting keys**.
Those checks compare the required projection, not all 96 delivered columns;
the original bytes and extra columns remain preserved.
Separate private reconciliation records associate the 2016–2022 daily and
combined CCM exports with matching query-result row counts; they do not
independently match query-output bytes or verify source vintage.

Together, the four daily batches cover the requested development dates
**2009-10-07 through 2022-02-02**. Date coverage does not establish that every
eligible historical security is present. Names, combined CCM/company metadata
and the independent benchmark have also been saved locally. The
[manual guide](../docs/wrds_daypass_export.md) describes their separate offline
inventories; source meaning, release/vintage and historical CIK judgments remain
unresolved, and these raw files are not yet an approved normalized research dataset.

### Completed annual Names snapshots

The [Names candidate builder](../docs/wrds_listing_candidates.md), introduced
in `6dac026` and executed at `1418e0e370c8878dd85a7143bbb7a52b899a32da`, completed
from `2026-10-10T23:55:30.881286Z` to `2026-10-10T23:55:34.077882Z`: **3.2 seconds**,
exit status **0**. The private bundle is
`data/private/wrds-listing-candidates/development-v1`; its receipt SHA-256 is
`698e3b280ac18a42bf11c0bc3b1cb2ecd10c701cfb4e1ab6f283066ecd28afc6`.

The original source contains **191,048 Names records**. Of these, **23,606**
cover at least one requested January 1, yielding **86,064 annual record/year
snapshots** in **18 parts**. The narrow ordinary-corporate-common predicate
identifies **50,777 candidate snapshots**:

| January 1 | Dated snapshots | Narrow ordinary-corporate-common candidates |
|---|---:|---:|
| 2010 | 6,683 | 4,491 |
| 2011 | 6,705 | 4,361 |
| 2012 | 6,799 | 4,219 |
| 2013 | 6,747 | 4,107 |
| 2014 | 6,883 | 4,116 |
| 2015 | 7,143 | 4,279 |
| 2016 | 7,319 | 4,268 |
| 2017 | 7,248 | 4,129 |
| 2018 | 7,350 | 4,101 |
| 2019 | 7,547 | 4,161 |
| 2020 | 7,640 | 4,155 |
| 2021 | 8,000 | 4,390 |
| **Total** | **86,064** | **50,777** |

Every year has **zero ambiguous security/year groups** and **zero exact
24-field duplicate excesses within these snapshots**. All original records
remain preserved, and other classification/scope-review categories remain in
the output. Every one of the **86,064 `known_at` values is null**. These counts
describe dated source predicates; historical CIK evidence, information
availability, liquidity qualification and issuer selection remain open. No
universe memberships, ranks, final exclusions or source approvals were created.

### Completed formal benchmark audit

The audit at `1418e0e370c8878dd85a7143bbb7a52b899a32da` completed from
`2026-10-10T23:55:34.099643Z` to `2026-10-10T23:56:11.211984Z`: **37.11 seconds**,
exit status **0**. Its private bundle is
`data/private/wrds-benchmark-audit/development-v1`; the receipt SHA-256 is
`593366dca43cdb299efcc41efd8705304df244b365043e47d61d24d49218cafc`.

The audit compared all **22,593,113 requested daily rows** with **3,103
independent market rows**; both sources cover every expected session. It
confirmed **22,216,260 exact text and numeric matches** and **376,853 mismatched
daily records across 52 dates**, also forming 52 source/date and raw-text groups.
There were **zero numeric-equal/text-different rows** and **zero dates with
different attached daily benchmark texts**.

Each mismatch has an absolute exact-decimal difference of **0.000001**. The
daily-attached value minus the independent value is positive on **21 dates**
and negative on **31**. Both source literals have exponent **-6** in all 52
mismatch groups. That describes the received text; it does not establish vendor
storage precision, a rounding rule, source vintage, or the cause of disagreement.

| Diagnostic half-even rounding | Equal benchmark values among the 52 mismatch dates |
|---|---:|
| 4 decimal places | 51 / 52 |
| 5 decimal places | 47 / 52 |
| 6, 7, 8, 10 or 12 decimal places | 0 / 52 |

These comparisons are diagnostics only. **No tolerance was accepted**, and
reconciliation and `discrepancy_explained` remain false. There was no benchmark
replacement or fallback, no inferred individual-stock return error, and no new
source approval or model-ready claim.

### Completed annual provisional liquidity processing

The [annual liquidity consumer](../docs/wrds_liquidity_candidates.md) is
published in `ae4e0c4456706c810f6a2863ee4fd9e364b8a477`, following **41 focused
tests**, independent code review and a passing
[CI run](https://github.com/michaelbawuah/Disclosure-drift/actions/runs/38097330436).
Its actual run completed from `2026-10-11T00:08:07.835069Z` to
`2026-10-11T00:10:00.938349Z`: **113.1 seconds**, exit status **0**. The private
bundle is `data/private/wrds-liquidity-candidates/development-v1`; its receipt
SHA-256 is `0be9983b192e2d15a32abe5c29240638d75fcfd639e19cbacb12ed48d977ce20`.

The annual table contains **87,405 security/year records** in **22 parts**
totaling **4,943,947 bytes**. Exact copies of the 18 Names detail parts preserve
all **86,064 Names snapshots**. Each of the twelve annual windows has all
**60 expected XNYS sessions globally covered**; individual securities can still
have absent or withheld observations. At least **40 numerically valid sessions**
are required for the numerical minimum. Provisional rank eligibility also
requires the unambiguous narrow ordinary-common Names predicate.

| Selection year | Observed security/year records | Meet numerical minimum | Provisional security ranks |
|---|---:|---:|---:|
| 2010 | 6,804 | 6,515 | 4,447 |
| 2011 | 6,817 | 6,558 | 4,315 |
| 2012 | 6,899 | 6,678 | 4,191 |
| 2013 | 6,881 | 6,639 | 4,089 |
| 2014 | 6,978 | 6,735 | 4,067 |
| 2015 | 7,257 | 7,026 | 4,224 |
| 2016 | 7,419 | 7,224 | 4,233 |
| 2017 | 7,360 | 7,158 | 4,099 |
| 2018 | 7,462 | 7,219 | 4,051 |
| 2019 | 7,654 | 7,461 | 4,132 |
| 2020 | 7,773 | 7,551 | 4,122 |
| 2021 | 8,101 | 7,766 | 4,260 |
| **Total** | **87,405** | **84,530** | **50,230** |

These totals count **security/year records**, not distinct securities across
the full period or approved issuers. The observed annual union includes 39
Names-only records and 1,341 daily-only records, and both unmatched subsets
remain preserved. The later [full Names-history check](../docs/dated_names_results.md)
explains the absent January descriptors for all 1,341 by recorded security
lifetimes ending before selection; it approves no exclusion. Of 50,777 ordinary
listing candidates, 50,230 satisfy provisional rank conditions. Repeated source
records never weight the mean, and missing sessions are never filled with zero.
Detailed session and classification breakdowns remain in the private receipt.

Ranks compare observed securities; they do not group share classes by issuer
or apply the final 500-issuer limit. Both `known_at` and `available_at` remain
null for all **87,405** rows. Benchmark reconciliation remains false, and this
processing creates no historical CIK link, approved universe, source approval,
forecast or final-period access. The completed 20/20 arithmetic review is
unchanged.

A final local check confirmed private directories and read-only files across
the five completed processing bundles, `model_ready: false` and zero source
approvals in every receipt, and no `data/private` files tracked in Git.

### Completed benchmark source-evidence packet

The [source-evidence consumer](../docs/wrds_benchmark_source_evidence.md) was
published as `5bbfa2c8b5a7933f56d3bded3363baf28c999087` after independent
assistant code review, **33 focused synthetic tests** and Ruff; its
[GitHub integrity workflow](https://github.com/michaelbawuah/Disclosure-drift/actions/runs/38100007026)
also passed. Review found
and corrected a Python-API case that could omit the required caller receipt
hash; the production CLI supplied the recorded hash explicitly. The Mac run
completed from `2026-10-11T00:55:19.769187+00:00` to
`2026-10-11T00:55:20.317245+00:00` in **0.548 seconds**, exit status **0**.

The private bundle is
`data/private/wrds-benchmark-source-evidence/development-v1`. Its receipt
SHA-256 is `527d04bb6760be5b692a6fcecd9e459612408ffa9055fe83e7c51398dd505294`.
The manifest contains **16 evidence/output files totaling 1,841,344 bytes**,
excluding the receipt itself. The
[aggregate execution record](wrds_benchmark_source_evidence_execution.json)
preserves the run timing, code commit, receipt hash, evidence counts and exact
diagnostics without licensed per-date values or security identifiers.

All **four daily source bindings and the independent market source** are
retained. The bundle copies and verifies the saved audit, source-stage and
inventory receipts, the complete small discrepancy Parquet, the market SQL,
and the supplied daily-query observation, reconciliation and screenshots. One
source has preserved SQL and one has supplied query-display evidence; four
sources have no supplied query display. The display association remains a
recorded row-count comparison, not certified query-to-CSV byte provenance.
All five sources still lack verified release/vintage and schema-version
evidence.

The packet recomputed the complete small mismatch table's Decimal diagnostics
and confirmed the original **52 dates / 376,853 repeated daily rows**, all with
absolute differences of **0.000001**. The original daily CSVs and source-stage
Parquet were not reread; their full comparison remains bound to the earlier
successful audit. The packet also creates an aggregate-only **unsent vendor
question draft** asking for the actual benchmark definition, dividend treatment,
calculation path, vintage and output-format explanation. No cause, tolerance,
replacement or source approval was accepted. The completed 20/20 review and
final-period gate remain unchanged.

### Completed annual Names/CCM identity evidence

The [identity-evidence consumer](../docs/wrds_identity_candidates.md) was
published as `5f9a451215cbb8c8c42156bcd96ae1b178b8e563` after independent
assistant code review, **41 focused synthetic tests** and Ruff; its
[GitHub integrity workflow](https://github.com/michaelbawuah/Disclosure-drift/actions/runs/38100186671)
also passed. Review corrected
a nonblank-GVKEY diagnostic to apply the inventory's exact Python whitespace
semantics; raw identifiers and matching behavior remain unchanged. The Mac run
completed from `2026-10-11T00:58:44.887293+00:00` to
`2026-10-11T00:58:52.177677+00:00` in **7.290 seconds**, exit status **0**.

The private bundle is `data/private/wrds-identity-candidates/development-v1`;
its receipt SHA-256 is
`093605e17f0358bd6477899ea1a2e5995a6960124438c7fc5d0046c8ef784099`.
The six tables contain **98 Parquet parts totaling 17,659,833 bytes**. The
[aggregate execution record](wrds_identity_evidence_execution.json) includes
table sizes, per-year counts, source-bound diagnostics and the post-run check.

Every one of the **110,124 CCM source records** is represented with its source
ordinal, 12 required raw fields and full-delivered-row fingerprint. The complete
47-column source remains unchanged in its existing inventory. **41,233** CCM
records have positive ASCII security identifiers and **68,891** have blank
linked security identifiers; these describe the downloaded metadata, not
missing study companies. Exact copies preserve all **86,064 Names snapshots**.
No ordinary-share, link-type, primary-link or share-class filter is applied to
the relationships.

The join enumerated **100,261 Names-record/year × CCM-record relationships**:
**34,122** have finite inclusive bounds compatible with January 1; **52,812**
have unresolved open-marker bounds without a finite contradiction; **9,523**
are earlier dated context and **3,804** are later dated context. All are
retained. Open markers never become invented dates, and future or expired
relationships cannot promote January 1 candidates. Multiple relationships can
refer to one annual security; these totals are not approved identity-link counts.

The annual summary preserves all **86,064 security/year records**. A separate
aggregate read of the completed table also reports the existing ordinary-listing
diagnostic subset, to distinguish its evidence needs from the rest of Names:

| Evidence status | All annual security records | Ordinary-listing candidates |
|---|---:|---:|
| Single candidate with a header CIK; historical identity evidence still required | 61,636 | 46,784 |
| Single candidate with missing or unsupported header CIK | 19,968 | 1,360 |
| Multiple or ambiguous candidate evidence | 2,665 | 2,518 |
| Dated context only; no January 1 candidate | 1,003 | 63 |
| No related CCM record | 792 | 52 |
| **Total** | **86,064** | **50,777** |

These counts refer to annual records, not distinct longitudinal securities,
approved issuers, or the final most-liquid-share-class selection. A single
current header match is still insufficient historical evidence. The ordinary
column retains a provisional listing diagnostic, not accepted universe membership.

All **215 public SEC manifest rows** are accounted for: **207** have a same-year
header-CIK discovery relationship and **8** have none. This run reads the
preserved manifest metadata; it does **not** reread original filing/header
bytes or certify their recorded hashes against those documents. The private
detail records acceptance-date interval diagnostics and preserves unmatched
filings. No discovery match becomes a historical security/issuer link, and
no unmatched filing becomes an automatic exclusion.

All derived `known_at` and `available_at` values remain null. The run creates
zero approved security links, zero source approvals, no universe membership,
no market outcomes and no final-period access. A post-run check reverified
both new receipt hashes, **102 declared identity files** and **16 declared
benchmark files**, private directory/read-only file modes, and the absence of
tracked licensed private files. The completed 20/20 review remains unchanged.

## Original SEC corroboration and discovery reconciliation

The offline collector at `3a5b368211fa134c637562cc4e312fd11e5024c9` ran from
`2026-10-11T01:48:59.240355+00:00` to
`2026-10-11T01:49:28.800315+00:00`: **29.560 seconds**, exit status **0**.
It reread the original primary filing and SGML header bytes in the local research
workspace, separately from the Mac's earlier manifest-only identity run. The
manifest SHA-256 is
`2658b7adfa03ea3c1800afd4107fa74c5348387533abde87cc30c0472b670fb1`.

| Source observation | Actual count |
|---|---:|
| Primary filing sources and headers independently reverified | 215 each |
| Unique original-manifest filer matches | 215 |
| Recorded acceptance clocks matching the manifest | 215 |
| All retained SGML filer observations | 218 |
| Filings containing multiple legitimate filers | 3 |
| Filings containing selected lexical cover facts | 79 |
| Filings without supported inline cover facts, retained explicitly | 136 |
| Selected fact occurrences / facts inside hidden elements | 1,494 / 106 |
| Facts retaining one or more lexical issue flags | 474 |

The three multi-filer filings are Comcast accessions
`0001166691-18-000004`, `0001166691-19-000005` and
`0001166691-20-000008`. Each preserves Comcast CIK `0001166691` and
NBCUniversal Media, LLC CIK `0000902739`, with exactly one manifest match.
The 2020 cover facts additionally retain the legal-entity dimension distinguishing
NBCUniversal while the context entity identifier remains Comcast. This is why
the reader preserves all filers and contexts instead of flattening them into a
single security identity.

The lexical report does not interpret XBRL values. Of the 474 flagged facts,
442 retain an uninterpreted `ixt-sec:exchnameen` exchange-name transformation;
47 have the year-only `http://xbrl.sec.gov/dei/2021` namespace that this version's
dated-namespace recognizer conservatively flags; 15 facts have both flags.
Those 47 namespace declarations were found and retained. The flag denotes a
recognizer limitation, not missing source text. Referenced contexts, dimensions,
and parsed serialization remain available for review; 136 untagged or unsupported
filings do not become identity exclusions. See the [reader contract](../docs/sec_identity_evidence.md)
and the execution record for the post-run diagnostic inspection and its limits.

That independent inspection reverified all 215 original primary files and
reproduced **6,457 retained HTML parser diagnostics**: 3,520 unexpected or
mismatched end tags, 2,529 duplicate HTML IDs and 408 misplaced document tags.
A separate standard-library HTML tokenizer matched every filing's selected
concept-family counts, exact QName/context-reference counts and referenced
context-ID occurrence counts, accounting for all **1,494 selected facts**.
No gross loss of those selected occurrences was detected. **Forty-one parser
logs reach 100 entries**, so these are retained diagnostic counts, not proof
that every underlying condition was logged. Count agreement does not establish
correct tree recovery, complete text interpretation or XBRL semantic validity.
The execution record embeds the complete diagnostic audit and its limitations;
the original lexical report remains unchanged.

The complete JSON contains **7,011,313 bytes**, SHA-256
`70260a8a1e17dd37a2df0c99cf66a8eefcb1a33608336d3f238c5a42fac997f0`.
The [published gzip](sec_identity_evidence.json.gz) contains **406,675 bytes**,
SHA-256 `acdb65f51f0a4e72a2db7356c6093628c6c73dfd8d8d837d8f01d8c12583be1e`;
decompression reproduces the complete JSON byte for byte. Python 3.12.14,
lxml 6.1.3.0 and libxml2 2.14.6 were recorded. The feature passed **80 focused
tests**, Ruff and two independent code reviews; its exact-commit
[CI run passed](https://github.com/michaelbawuah/Disclosure-drift/actions/runs/38103009529).

The separate Mac discovery inspection ran at the same commit from
`2026-10-11T01:51:48.144780+00:00` to
`2026-10-11T01:51:48.599817+00:00`: **0.455 seconds**, exit status **0**.
It checked the pinned identity receipt, source-file hashes and complete manifest
accounting while reading only six discovery-ledger fields. All **eight unmatched
filings** are original Exxon CIK `0000034088`, accepted in 2014–2021. Eight
filings produce seven consecutive annual pairs, consistent with the earlier
seven flagged pair cases. No vendor identifiers or market returns were exported.

The [public Mac report](sec_identity_discovery_context.json) has SHA-256
`526364f9530918f222fdad42638c1c0d680213fe8461548f4cb632698669e376`.
A subsequent local check bound all **215 original-source records** to the
manifest by ordinal, accession, original CIK, date, URLs and hashes, and bound
all **eight unmatched discovery records** to that report. Both executions retain
their own provenance: the Mac inspector did not reread original SEC bytes.
No historical availability, source approval, human review or security link was
created, and the actual final period remains unopened.

## What happens next

Make a source-backed, reviewed benchmark choice on the protocol's identical
sessions, retain the 52 unexplained cross-view differences, review the completed
candidate evidence, and establish the historical security universe and source
judgments. The [benchmark source decision proposal](../docs/benchmark_source_decision.md)
sets out the evidence for reviewing the saved independent series; it does not
enact a source selection or require equality between exports. The full historical
CIK query form for
product `wrdssec_common` displayed **Submit Form (Not Subscribed)** for the
current institution/session. This observation does not establish that the day
pass expired or that the institution can never access the product. No full
historical CIK export was obtained from that form; its schema and historical
availability remain unverified. See the
[source-convention evidence](../docs/wrds_source_conventions.md#7-current-company-headers-cannot-establish-historical-ciks).

The new documented alternative is **CRSP/Compustat Company History**, whose
[official dictionary](https://www.crsp.org/wp-content/uploads/ccm_files/CompanyHistory.html)
lists historical CIK (`HCIK`) and effective description bounds
(`HCHGDT`/`HCHGENDDT`). Request its authorized schema/export, coverage, release
and availability semantics. The dictionary alone does not prove this account's
access or that the supplied records will satisfy the historical contract. The
[access evidence and unsent request](../docs/historical_identity_access_evidence.md)
make that request concrete. The benchmark packet separately contains the
unsent source-definition/vintage question for the 52 differences; no external
message has been sent.

The [public SEC demonstration](../docs/public_historical_identity_sources.md)
offers an additional corroboration route through issuer observations and
original subject-company CUSIP/class evidence. The
[native CRSP definition](../docs/benchmark_primary_definitions.md) narrows the
benchmark question to the saved views' actual index mapping, expression, release
and export conventions. These new source leads do not fill the outstanding
historical availability fields or supply a reviewed source choice.

| Stage | Work remaining |
|---|---|
| Historical inputs | Approve a source-backed benchmark choice while preserving the 52 unexplained differences; verify security-universe completeness, historical CIK/security links, source release/vintage, units and historical availability |
| Pilot closure | Remaining source and filing judgments, followed by the approved controls-only smoke |
| Full dataset | Reviewed normalization, historical universe selection, predecessor filings and full-sample source audit |
| Development | Run actual 2016–2021 comparisons; complete semantic example review; freeze actual primary and secondary choices |
| Final evaluation | Open the separate approved 2022–2025 inputs and produce the measured annual predictions and intervals |
| Robustness and final paper | Run the prespecified diagnostics, interpret actual cases and limitations, complete independent-person reproduction and publish the final research package |

Default population collection covers selection years 2010–2021, with the first
liquidity window beginning October 7, 2009. Development return coverage ends
February 2, 2022 for late-2021 labels. Both holdout population price/volume and
holdout returns require completed development prerequisites; final label coverage
extends through February 3, 2026. Development sources are now preserved locally;
no historical availability timestamp or human approval has been inferred from
their acquisition. The final-period source gate remains unchanged.

The [empirical completion guide](../docs/research_completion_gates.md) identifies
the exact existing review packet, acceptable evidence fields and the commands
that follow approval. Milestones 1–4 are completed engineering/source-verification
checkpoints; empirical milestones 5–11 remain pending. The static
`disclosure status` checklist does not validate private production bundles. The guide
preserves the completed 20/20 review and the protocol's explicitly reviewed
filing-availability proxy without inventing historical listing or liquidity
availability timestamps.

The earlier eight-page progress PDF and four-page pilot PDF remain intact as the
original 20-issuer snapshot. This update, the current
[milestone record](MILESTONES_06_11.md), and the linked receipts describe the new work.
