# Milestones 6–11: implementation and empirical progress

**Date:** October 10, 2026

**Researcher:** Michael Baffour Awuah

**Status:** The software and reporting work has advanced through the final
evaluation and secondary-analysis stages. The actual empirical milestones are
not complete. Development daily exports now cover the required source dates,
and Names, combined CCM/company metadata and the independent benchmark are saved
locally. Security-universe completeness, normalization and required source
judgments remain outstanding. The user's 20/20 numerical review is complete.

The frozen primary protocol has not changed. Its hash is
`3951be086ed9a74ec69a304004ebcb5aed63bac161e043ff92ae4f51b8e325d9`.
The original ten-week plan is superseded where it differs: retain unranked
20-session market-adjusted targets, development in 2016–2021, final evaluation
in 2022–2025, and paired three-/six-month reference-month blocks.

## What each milestone now contains

| Milestone | Delivered | Empirical requirement still open |
|---|---|---|
| **6: pilot checkpoint** | 215 source-verified filings / 180 pairs; 104 pairs in 2019–2021 meet the count criterion; user's 20/20 numerical review recorded; descriptive exhibits, source examples and audited controls-smoke command | Reviewed identities, source availability and remaining filing/trace judgments; real controls smoke; independent person's reproduction |
| **7: full dataset** | Historical year-start selector; resumable WRDS exporter and offline manual inventories; locally preserved development daily, Names, CCM/company and market exports; universe-bound SEC ingestion; audited assembly; separated final features/targets and exclusions | Verified security-universe completeness, reviewed normalization, source vintage/availability and historical CIK links; predecessor filings; additional full-sample 30-pair filing audit; explained full-sample coverage |
| **8: development and freeze** | Eight primary configurations over six development folds; six ablation subsets; actual MiniLM execution on 155 real filings / 135 pairs with full token coverage and numerical checks; code/data/review/selection freeze | Approved empirical development, human semantic example review, and a freeze of actual choices/evidence |
| **9: final evaluation** | Four annual mature-label refits; paired incremental R-squared; 2,000-draw three-/six-month intervals; exact prediction artifacts; durable access ledger and changed-freeze refusal | Execute the approved freeze on the actual 2022–2025 observations; report the measured result |
| **10: robustness** | Year/month/leave-one-year-out diagnostics; fixed size/industry groups; six frozen ablations; source-linked failures; independent delay rebuild APIs; descriptive paragraph comparison; verified-run orchestration | Execute all declared checks on empirical predictions and independently rebuilt delay data; inspect real cases; interpret limitations |
| **11: research package** | Locked code and tests; full synthetic reproduction; eight-page progress report; figures; public overview page; data request and handoff guides | Actual results and final interpretation; another person's reproduction; final portfolio publication/update |

No generated template has been turned into a person's approval. No synthetic
prediction has been presented as a market result. No primary final score exists.

## Observed pilot evidence

The expanded checkpoint contains **215 original filings, 180 annual pairs and
35 issuers**. Acceptance years 2015–2021 contain 19, 19, 19, 19, 34, 35 and 35
pairs. Its **104 pairs in 2019–2021 meet the original 100–150-pair count criterion**.
The additional 15 issuers were selected without market outcomes. This purposive
document-format sample does not establish the historical investment universe.

All 215 source checks reproduce. The audit retains 19 registered reference
resolutions and 104 differences between API timestamps and original SGML headers.
The original header determines the event clock; dissemination/availability
assumptions remain explicit.

The original 155 filings and 135 pairs are preserved. New-source execution
corrected Ford continuation headings, Mastercard running headers, McDonald's
labeled risk block, and Honeywell's page-index pointer. All five new registered
ranges have assistant source inspections. McDonald's scope explicitly excludes
a separate general cautionary statement for the remaining human review to assess.
The parser change leaves all original 155 texts, counts, status values and versions
unchanged. See the [extraction guide](../docs/pilot_expansion.md).

All 135 provisional candidate label/control calculations independently reconcile
to raw CSV decimal arithmetic within `1e-12`. The maximum absolute difference is
`1.429412144204889e-15`. The original candidate-calculation and independent-trace
artifact hashes reproduce. DuckDB files may differ in container metadata; no
whole-bundle byte-equivalence claim is made.

The user's **20/20 independent arithmetic and printed-timing review is recorded**
against the exact original packet. The submitted script reproduces all saved
results and catches the reported fourth-decimal mutation. No repeat numerical
review is requested. Human filing and full-source trace approvals remain
outstanding. Seven candidate events
retain header-CIK differences, and 135 historical candidate links retain an
unresolved open-ended marker. These arithmetic successes do not approve the
identity, share class, source release or historical information availability.

Sources: [expanded checkpoint](pilot_expansion/pilot_checkpoint.json),
[completed user review](review_progress/user_arithmetic_receipt.json),
[five source-scope reviews](review_progress/expansion_scope_review_v2.json),
[candidate arithmetic receipt](pilot_arithmetic_summary.json), and
[review follow-up](review_followup_summary.json).

### Descriptive text results

| Measure | Observations | Median | 10th–90th percentile |
|---|---:|---:|---:|
| Current section tokens | 180 | 7,555 | 3,679–13,430 |
| Log length change | 180 | 0.05103 | −0.02476–0.19866 |
| Jaccard distance | 180 | 0.10156 | 0.03520–0.22200 |
| TF-IDF cosine distance | 161 | 0.004177 | 0.001121–0.01668 |

TF-IDF vocabulary is fitted only on earlier acceptance years for these descriptive
exhibits. The first 19 pairs have no prior pilot vocabulary and remain unavailable.
This is a text description, not evidence that the variables predict returns.
Source: [expanded public text features](pilot_expansion/text_features.csv).

## What the software verification establishes

The [build receipt](build_verification.json) records the actual test results and
full-demo status. The original baseline had 196 passing tests. New tests exercise
historical information cutoffs, class selection, source/review fingerprints,
orphan/duplicate joins, source arithmetic, changed code/data, schema-first target
refusal, immature labels, frozen selections, persistent final access records,
undefined statistics and independently rebuilt delay windows.

The full demonstration selects **192 invented annual memberships**, builds
**144 development** and **48 final** observations, and runs eight primary
configurations, six development folds and four final-year fits. Six proper text
feature subsets require 24 development configurations and produce 288 final
secondary predictions. Delay-source arithmetic is separately rebuilt for 1, 2
and 5 sessions. All outcomes are invented and all human approvals remain zero.

The verified-run secondary wrapper consumes the completed primary run's saved
predictions. It checks the original freeze and persistent access receipts, does
not deserialize the final target table again, and cannot choose new penalties.
Unit tests retain an explicitly synthetic toy encoder. Separately, the actual
pinned MiniLM backend has executed on the original 155 SEC filings and 135 annual
pairs: 1,459,865 WordPiece tokens, 5,828 chunks and zero truncation. Numerical
checks cover dimensions, unit norms, repeated encoding and batch-size agreement.
This retrospective text description is separate from the return model; human
semantic judgments and any empirical semantic comparison remain pending. See
the [actual execution report](semantic_validation/report.md).

These are automated and assistant checks. They do not complete the plan's
independent-person reproduction requirement.

## Reproduction and artifacts

```bash
make reproduce-full
make research-report
```

The first command works with public code and invented data. The second builds
the progress PDFs from the public SEC-only exhibits and saved audit receipts.
`make pilot-expand` additionally needs the recovered private source cache
and matching source audit. Licensed market rows remain excluded from Git.

- [Latest execution update](RESEARCH_EXECUTION_UPDATE.md)
- [New verification receipt](execution_verification.json)
- [Original 20-issuer progress PDF — eight pages](research_progress/Research_Progress_Report.pdf)
- [Original pilot checkpoint PDF — four pages](research_progress/Pilot_Checkpoint_Report.pdf)
- [Research overview](index.html)
- [Full data request](../docs/full_study_data_request.md)
- [Run the WRDS export](../docs/wrds_full_export.md)
- [Historical dataset contract](../docs/historical_dataset.md)
- [Freeze and final evaluation](../docs/final_evaluation.md)
- [Robustness methods](../docs/robustness.md)
- [Semantic comparison](../docs/semantic_analysis.md)

## Exact next empirical step

Normalize and reconcile the locally preserved development exports documented in
the [manual WRDS guide](../docs/wrds_daypass_export.md). The four daily batches
cover the requested dates **October 7, 2009 through February 2, 2022**, including
the first liquidity window and the late-2021 outcome tail. Names, combined
CCM/company metadata and the independent benchmark are also preserved. Raw date
coverage does not certify the complete historical security universe or produce
model-ready inputs.

Review source units and return conventions, dated classifications, historical
CIK links and source vintage/availability; reconcile the benchmark and explain
full-sample coverage. Complete the source-bound human reviews against the
existing evidence, then run development and freeze the actual procedure.
Holdout population price/volume and return collections remain separately gated;
the actual 2022–2025 study has not been executed. The primary design and completed
20/20 numerical review remain unchanged.
