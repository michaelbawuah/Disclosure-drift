# Proposed primary benchmark source

**Status: proposal for review, 11 October 2026. No source decision or approval has
been enacted.**

Propose using the **already preserved independent `vwretd` export from
`crsp_a_stock.wrds_dailyindexret_query`** as the primary development benchmark,
subject to the source and normalization checks below. Keep the benchmark attached
to the daily stock exports and all **52 discrepant dates** as comparison evidence.
The cause of those differences remains unresolved; this proposal does not declare
either delivered number correct merely because its view is preferred.

## Rationale and protocol boundary

The [frozen protocol](../protocol.md#question-and-target) requires compounded stock
total return minus compounded value-weighted market return over identical label
sessions. It does not require two vendor export views to agree on every value.
The [normalized importer](../src/disclosure_research/market_data.py), through
`validate_manifest`, requires an explicit `value_weighted_total_return`
convention, benchmark description, source release/documentation and normalization
provenance. Its declarations are not independent certification of the source.
[Import instructions](market_import.md#import-a-mapped-development-sample) and
the [market contract](market_data_contract.md#returns-and-benchmark) require a
declared benchmark, one unique record per needed session and no filling.

Two official WRDS implementations support the proposed source's intended role:

- The [CIZ beta macro](https://wrds-www.wharton.upenn.edu/pages/wrds-research/macros/wrds-macros-betas-ciz/)
  defaults to `VWRETD`, reads daily index data from
  `crsp.wrds_dailyindexret_query`, and joins it to stock data by date.
- The [CIZ event-study macro](https://wrds-www.wharton.upenn.edu/pages/wrds-research/macros/run-an-event-study-ciz-format-macro/)
  obtains `dlycaldt` and `vwretd` from that index view separately from security
  returns, then merges them by date.

These examples support selecting a dedicated market series independently of the
stock-row export. They do not establish the downloaded file's vintage, the
`crsp`/`crsp_a_stock` library relationship, the stock view's benchmark join, or
equivalence between the two exports. The proposed choice follows the benchmark
definition and provenance; it must not depend on which source improves model
results. WRDS's example event-study calculations do not replace this project's
fixed compounding and timing rules.

## Exact evidence under review

The [public execution record](../reports/wrds_benchmark_source_evidence_execution.json)
records the completed private packet and its unchanged closed gates. The
[execution report](../reports/RESEARCH_EXECUTION_UPDATE.md#completed-formal-benchmark-audit)
records comparison of 22,593,113 requested daily rows against 3,103 independent
market rows with every expected session covered.

| Evidence | SHA-256 |
| --- | --- |
| Independent market CSV: 3,103 rows, 63,455 bytes | `dcc1dae8e0ceaab6e22635c6144002424fe052bf16bbb9f2e336431287e0ada7` |
| Preserved market SQL: 260 bytes | `2351cc54ebf4bec297122c6990883a2b6a6167ba8cd303ed2a1f014b69166113` |
| Successful benchmark audit receipt | `593366dca43cdb299efcc41efd8705304df244b365043e47d61d24d49218cafc` |
| Successful source-evidence packet receipt | `527d04bb6760be5b692a6fcecd9e459612408ffa9055fe83e7c51398dd505294` |
| Frozen protocol | `3951be086ed9a74ec69a304004ebcb5aed63bac161e043ff92ae4f51b8e325d9` |

The CSV and SQL metadata above are recorded from the previously verified private
run; this document did not reopen them. Use the pinned packet's market-source
entry for the exact inventory-receipt hash and its preserved snapshot. No new
receipt hash is inferred. Hashes identify evidence bytes; they do not prove
vendor correctness.

The saved SQL selects `DlyCalDt` and `vwretd` from the named independent view
with a date filter. No daily-export SQL was secured. The large daily query's
recorded display names `crspa` and `wrds_dsfv2_query`; its matching displayed and
inventoried row counts are an association, not certified query-to-CSV provenance.
The [packet contract](wrds_benchmark_source_evidence.md#observed-query-evidence-and-its-limits)
preserves that distinction. All five source entries still lack verified release/
vintage and schema-version evidence. The vendor question draft remains unsent.

## What the discrepancies establish

The pinned audit records 52 discrepant dates affecting 376,853 repeated daily
stock records. Every absolute exact Decimal difference is `0.000001`; attached
daily minus independent market is positive on 21 dates and negative on 31.
Both literals have exponent `-6` in all discrepant groups. There are 22,216,260
exact text and numerical matches, no numerical-equality/text-only differences,
and no conflicting attached benchmark values within a date. These are benchmark
comparisons, not findings about the correctness of individual-stock returns.

**Precision remains a mathematical possibility, not an established mechanism.**
For example, the invented values `0.01234549999` and `0.01234550001` differ by
`0.00000000002`; rounding each to six decimal places produces `0.012345` and
`0.012346`. Thus a smaller pre-export difference can cross a rounding boundary.
The observed `0.000001` scale alone can neither rule precision in nor rule it out.
The two six-decimal literals do not reveal their pre-export values or storage
precision. Coarser rounding diagnostics do not establish equality or acceptability.

The official [2019 CRSP Historical Indexes Guide, pages 34–35](https://wrds-www.wharton.upenn.edu/documents/397/CRSP_1925_historical_indexes_guide.pdf#page=34)
lists `REAL`, `E13.6` and an `F10.6` suggested alternative for `VWRETD` in legacy
formatted index-file layouts. This is **no proof about either CIZ WRDS view** or
its CSV serializer. Likewise, the [CRSP migration appendix](https://www.crsp.org/wp-content/uploads/appendix/FlagType_MU.html)
describes possible calculation/pass-through and machine-precision differences
without tying them to these files. [WRDS's public output-format help](https://wrds-www.wharton.upenn.edu/demo/step_support/outputformat/)
does not specify a CSV rounding rule. Public checks of the annual dictionary,
CIZ FAQ and index overview reached sign-in pages; their unseen contents were
not treated as evidence. **No discrepant date has been explained by this review.**

The subsequent [complete-manual review](benchmark_primary_definitions.md)
recovered the native `IndDlySeriesData` definition: `INDNO = 1000200`,
`DlyCalDt`, distribution-inclusive `DlyTotRet`, and preceding-period
capitalization weights. The three exact PDF downloads and inspected pages are
bound in its retrieval ledger. This makes the intended native-series check
specific; it does not yet bind either saved WRDS view to that series or explain
any of the 52 discrepancies.

The [subsequent public-catalog follow-up](benchmark_source_followup.md) confirms
that WRDS labels `crsp_a_stock` as its annual stock product. Its advertised
dictionary requires sign-in. This narrows the product identification but leaves
the actual view expression, alias mapping and saved-export release unbound;
zero discrepancy causes were resolved.

## Evidence needed for a decision

| Review question | Required evidence and action before use |
| --- | --- |
| Is this the intended benchmark? | Bind an applicable dictionary or vendor explanation to the independent view, underlying index/field, value weighting, distribution treatment, units and session dates. Establish the relevant library mapping. The macros support the role but do not complete this file-specific check. |
| Which release produced the saved file? | Supply credible release/schema and extraction evidence tied to the CSV, saved SQL and inventory receipt. Preserve timezone uncertainty. Do not use a guide date, current catalog timestamp or local receipt creation time as the data vintage. |
| Does normalization faithfully preserve it? | Reverify source bindings and complete permitted dates before numeric conversion; map `dlycaldt` to `session` and `vwretd` to `total_return` with a recorded numeric representation and code hash. Require unique XNYS dates, finite values at least -1, no missing required sessions, no replacement/filling and no silent rounding. Retain raw text and original bytes upstream. |
| Does it satisfy every retained label? | Verify exactly the same next 20 sessions as the stock leg, excluding the reference-day return. Keep development acceptance years 2010–2021 and the permitted late-2021 outcome tail; do not open 2022–2025 filing outcomes. Complete stock-return/delisting and label reviews separately. |
| Can the remaining source risk be accepted? | A named human review must assess the bound evidence and explicitly accept, defer or reject the proposed independent source while acknowledging the 52 unresolved comparisons. The [empirical evidence contract](historical_dataset.md#3-evidence-and-review-contract) still requires substantive label and normalization reviews. This proposal supplies neither review nor approval. |

For the discrepancy investigation itself, obtain the two relevant view
definitions and typed benchmark expressions, base index identifiers and releases,
any casts/SAS formats, and the actual export precision/rounding path. A documented
reproduction of the preserved discrepancy evidence would distinguish a formatting
effect from differing source values or revisions. That would resolve the cause;
it is distinct from establishing that a particular dedicated series satisfies
the primary benchmark contract.

Accept the proposed source only when its identity, convention, provenance and
normalization are sufficiently substantiated and the required review is recorded.
Defer if evidence remains insufficient. Reject if it identifies the wrong series,
an unsupported transformation, an irreconcilable source binding or incomplete
required coverage. Universal agreement with the attached export is not a new
prerequisite; unresolved risk must still be assessed explicitly.

## Alternatives and remaining project gates

| Option | Assessment |
| --- | --- |
| Review the saved independent series as primary | Recommended proposal: matches WRDS's documented CIZ workflow and gives a dedicated session-level source. File-specific evidence and review remain required. |
| Use the stock-attached benchmark | Possible only with its own source/convention evidence and explicit review. Its stock-view placement and repeated values do not prove superiority; saved daily SQL is absent. |
| Defer selection pending vendor evidence | Appropriate if the independent source cannot yet be substantiated. Preserve the existing evidence packet and continue unrelated development preparation. |

Averaging the two sources, choosing values date by date, or silently accepting a
tolerance is not proposed. Any later independently sourced comparison must be a
new bound artifact with a declared purpose, not a replacement of these originals.
The original audit's exact-equality and numerical-reconciliation fields remain
false even if a future source review accepts the dedicated benchmark for use.

Historical identity is a separate obstacle. The
[identity evidence execution record](../reports/wrds_identity_evidence_execution.json)
still reports no historical CIK source and zero approved security links. Current
company-header CIKs and dated candidate relationships remain discovery/context
evidence. Historical identity, availability, universe selection, source population
coverage, stock normalization and filing audits cannot be approved by this
benchmark decision. The [research completion gates](research_completion_gates.md)
describe the remaining requirements and their evidence boundaries.

This document changes no code, protocol, data, receipt or gate. `model_ready`
remains false, new source approvals remain zero, the previous arithmetic review
remains unchanged, and the final period remains closed.
