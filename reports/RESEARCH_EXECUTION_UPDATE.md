# Research execution update — October 10, 2026

This execution advanced three previously open tasks: the planned pilot now has
enough 2019–2021 pairs, the actual semantic checkpoint has run on real SEC text,
and full-study WRDS collection has runnable, resumable tooling. Manual downloads
now cover all requested development daily dates, with Names, combined CCM/company
metadata and the independent benchmark preserved locally. The user's earlier
20/20 numerical review is also preserved as a completed review. The development
source projection has now run successfully across all requested sessions; its
exact benchmark comparison identified 52 dates that remain unreconciled. The
revised numerical build also completed, producing 22,588,059 distinct
provisional candidate rows without creating an approved forecasting dataset.

**The empirical forecasting study remains unfinished.** Security-universe
completeness, source normalization and judgments, actual development selection,
final estimates, robustness interpretation and independent-person reproduction
are still needed.
The primary protocol is unchanged and the actual 2022–2025 evaluation remains unopened.

## Completed in this execution

| Work | Observed result | Evidence |
|---|---|---|
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
| Verify the software | Recorded verification baseline: **444 tests passed; Ruff passed; complete synthetic study completed**. New source, numerical-candidate, Names and benchmark commits passed their focused tests and CI; no updated whole-repository test total is claimed | [Recorded verification](execution_verification.json); [source-processing CI run](https://github.com/michaelbawuah/Disclosure-drift/actions/runs/38096427112) |

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
source approval or model-ready claim. Annual provisional liquidity/rank
processing is the next computable source step; its feature and production
results are still pending.

## What happens next

Resolve the 52 benchmark discrepancies using source-bound evidence, review the
completed candidate evidence, and establish the historical
security universe and source judgments. The full historical CIK query form for
product `wrdssec_common` displayed **Submit Form (Not Subscribed)** for the
current institution/session. This observation does not establish that the day
pass expired or that the institution can never access the product. No full
historical CIK export was obtained from that form; its schema and historical
availability remain unverified. See the
[source-convention evidence](../docs/wrds_source_conventions.md#7-current-company-headers-cannot-establish-historical-ciks).

| Stage | Work remaining |
|---|---|
| Historical inputs | Resolve the 52 benchmark discrepancy dates; verify security-universe completeness, historical CIK/security links, source release/vintage, units and historical availability |
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

The earlier eight-page progress PDF and four-page pilot PDF remain intact as the
original 20-issuer snapshot. This update, the current
[milestone record](MILESTONES_06_11.md), and the linked receipts describe the new work.
