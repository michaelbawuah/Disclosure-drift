# Full Names history: measured results and remaining limits

The October 11, 2026 Mac runs resolved two specific source-coverage questions:
the 15 filing-date gaps in the January snapshots, and the absence of January
descriptors for 1,341 liquidity-only annual observations. The original
foundation records remain unchanged. Neither result supplies historical CIK
approval, contemporaneous availability or a model-ready research dataset.

The [execution record](../reports/names_history_execution.json) binds both runs
to code commit `16ca9e5fb1b76fa5fb149c58e64976b8b88935a1` and the preserved source
files. [Verification](../reports/names_history_verification.json) records the
separate output checks and successful implementation CI. The full reproduction
passed **974 tests**, Ruff and the complete synthetic study; these checks do not
establish empirical forecasting performance.

## Filing-date descriptor coverage

The complete-history run finished in **2.272097 seconds**. It inspected all
**191,048 original Names records**, then checked the existing 207 discoveries at
acceptance, reference, 60 control sessions and 20 label sessions. Acceptance is
its own role, so it can repeat a control date or fall on a non-trading day.

| Measured result | Count |
| --- | ---: |
| Original discovery rows retained unchanged | 207 |
| Original filing-coverage rows retained unchanged | 215 |
| Original Exxon filings still without a discovery | 8 |
| Role/date observations with one exact-identifier Names record | 16,974 |
| Discoveries with all 82 required observations covered unambiguously | 207 |
| January snapshot gaps with a unique full-history acceptance-date record | 15 of 15 |
| Discoveries with descriptor-text changes | 18 |
| Missing, ambiguous or identifier-variant observations | 0 |
| PERMCO text changes from the original January Names record | 0 |
| Distinct original Names occurrences retained for inspection | 65 |

The [aggregate](../reports/dated_names_aggregate.json) records these counts. A
separate verifier reopened the original CSV, checked every point against its
complete applicable history, reconstructed the exchange-calendar dates and
aggregate counts, and compared the original discovery/coverage tables exactly.
The 12 output Parquet parts contain **530,874 bytes**; the complete private
bundle contains **1,006,243 bytes**.

The earlier statement remains true about its specific source rows: 15 January
descriptors end before acceptance. The new evidence locates the applicable
records elsewhere in the full history. It does not extend the old intervals.
Raw CUSIP, share class, SIC, NAICS, ticker and other descriptor changes are
preserved for inspection. A literal change does not by itself establish a
corporate event, and the PERMCO comparison concerns Names records, not CCM.
See the [consumer contract](dated_names_evidence.md).

## Why 1,341 liquidity-only records lack January descriptors

The separate lifetime diagnostic finished in **1.464616 seconds** and scanned
the same **191,048 original Names records**. All **1,341 annual observations**
fall in `ALL_RECORDED_SECURITY_LIFETIMES_END_BEFORE_SELECTION`: every matching
source occurrence reports a security lifetime ending before that year's
selection. This includes **490 numerical-minimum passes** and **851 failures**.

The [aggregate](../reports/liquidity_only_names_aggregate.json) accounts for all
**7,683 annual-observation-to-source-row references**. The independent check also
found **7,683 distinct source records** in this particular result; the two counts
describe different units. The private observations file contains **2,170,858
bytes**; its receipt is bound in the execution record.

This explains the missing January descriptors within the saved export. Some
earlier observations can satisfy the preceding liquidity-window minimum even
when the recorded security lifetime ends before selection. The 1,341 records
therefore should not be described as unexplained missing Names history.
They remain in the foundation; no research exclusion, rank change or historical
knowledge claim has been approved. See the [diagnostic contract](liquidity_only_names.md).

## What remains open

The original identity breakdown is unchanged: among **50,230 provisionally
rank-eligible annual observations**, **46,359** have one usable current-header
CIK and **3,871** have missing or ambiguous candidate evidence. Complete
descriptor coverage does not convert those header identifiers into historical
CIK intervals or establish `known_at`/`available_at`.

Two source investigations now make further work more specific. The
[public SEC demonstration](public_historical_identity_sources.md) preserved
2019 Q4 ownership-submission issuer metadata and an original Schedule 13G/A
issuer/CUSIP/class observation; it supplies corroboration routes, not an
approved continuous security crosswalk. The
[recovered CRSP manuals](benchmark_primary_definitions.md) identify native
value-weighted index **`INDNO=1000200`** and daily total-return field
**`IndDlySeriesData.DlyTotRet`**. Mapping the saved WRDS views to that definition,
their release/vintage and export conventions still requires evidence. **Zero
of the 52 benchmark discrepancy causes were resolved.**

Historical identity, source availability, normalization and remaining human
judgments still block the empirical study. The frozen protocol, 73 completed
assistant filing reviews and user's 20/20 arithmetic review retain their scope.
Empirical milestones **5–11 remain pending**, and the actual 2022–2025 final
evaluation remains unopened. The [completion guide](research_completion_gates.md)
identifies the remaining requirements.
