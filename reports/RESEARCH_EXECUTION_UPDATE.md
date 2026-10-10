# Research execution update — October 10, 2026

This execution advanced three previously open tasks: the planned pilot now has
enough 2019–2021 pairs, the actual semantic checkpoint has run on real SEC text,
and full-study WRDS collection has runnable, resumable tooling. The user's earlier
20/20 numerical review is also preserved as a completed review.

**The empirical forecasting study remains unfinished.** Full historical vendor
exports, remaining source judgments, actual development selection, final estimates,
robustness interpretation and independent-person reproduction are still needed.
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
| Verify the software | **444 tests passed; Ruff passed; complete synthetic study completed** | [Execution verification](execution_verification.json) |

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

## What happens next

The immediate dependency is the actual full historical source export. For a
website Access Pass/Daypass, follow the
[manual browser-export guide](../docs/wrds_daypass_export.md) and retain the
original files and query evidence locally. With authenticated database access,
the [WRDS guide](../docs/wrds_full_export.md) provides a separate sequence:
inspect the account's catalog, verify five source bindings, collect development
population windows, collect development market sources, then verify and assemble
the monthly files. Its authentication remains in the user's local WRDS prompt.

| Stage | Work remaining |
|---|---|
| Historical inputs | Actual dated population, liquidity, CIK/security links, returns, benchmark, size and industry sources; documented release, units and availability |
| Pilot closure | Remaining source and filing judgments, followed by the approved controls-only smoke |
| Full dataset | Reviewed normalization, historical universe selection, predecessor filings and full-sample source audit |
| Development | Run actual 2016–2021 comparisons; complete semantic example review; freeze actual primary and secondary choices |
| Final evaluation | Open the separate approved 2022–2025 inputs and produce the measured annual predictions and intervals |
| Robustness and final paper | Run the prespecified diagnostics, interpret actual cases and limitations, complete independent-person reproduction and publish the final research package |

Default population collection covers selection years 2010–2021, with the first
liquidity window beginning October 7, 2009. Development return coverage ends
February 2, 2022 for late-2021 labels. Both holdout population price/volume and
holdout returns require completed development prerequisites; final label coverage
extends through February 3, 2026. No full WRDS source rows were retrieved during
this execution, and no historical availability timestamp or human approval was invented.

The earlier eight-page progress PDF and four-page pilot PDF remain intact as the
original 20-issuer snapshot. This update, the current
[milestone record](MILESTONES_06_11.md), and the linked receipts describe the new work.
