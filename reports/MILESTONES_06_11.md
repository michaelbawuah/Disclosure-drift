# Milestones 6–11: implementation and empirical progress

**Date:** October 10, 2026

**Researcher:** Michael Baffour Awuah

**Status:** The software and reporting work has advanced through the final
evaluation and secondary-analysis stages. The actual empirical milestones are
not complete because historical source data and required human reviews are absent.

The frozen primary protocol has not changed. Its hash is
`3951be086ed9a74ec69a304004ebcb5aed63bac161e043ff92ae4f51b8e325d9`.
The original ten-week plan is superseded where it differs: retain unranked
20-session market-adjusted targets, development in 2016–2021, final evaluation
in 2022–2025, and paired three-/six-month reference-month blocks.

## What each milestone now contains

| Milestone | Delivered | Empirical requirement still open |
|---|---|---|
| **6: pilot checkpoint** | Recovered source/arithmetic reproduction; text-only distributions and coverage; deterministic source-linked examples; four-page report; audited controls-only smoke command | Reviewed identities, source availability and filing/trace evidence; adequate 2019–2021 coverage; real controls smoke; independent person's reproduction |
| **7: full dataset** | Historical year-start selector; complete source contracts and export windows; universe-bound SEC ingestion; audited one-to-one model assembly; separated final features/targets; exclusions and evidence fingerprints | Full historical population and 2010–2025 inputs, including predecessor filings; additional 30-pair filing audit; explained full-sample coverage |
| **8: development and freeze** | Eight primary configurations over six development folds; six secondary ablation subsets; pinned retrospective semantic encoder and separate model; code/data/review/selection freeze | Run approved empirical development, validate the actual semantic model and fixed examples, and freeze real choices/evidence |
| **9: final evaluation** | Four annual mature-label refits; paired incremental R-squared; 2,000-draw three-/six-month intervals; exact prediction artifacts; durable access ledger and changed-freeze refusal | Execute the approved freeze on the actual 2022–2025 observations; report the measured result |
| **10: robustness** | Year/month/leave-one-year-out diagnostics; fixed size/industry groups; six frozen ablations; source-linked failures; independent delay rebuild APIs; descriptive paragraph comparison; verified-run orchestration | Execute all declared checks on empirical predictions and independently rebuilt delay data; inspect real cases; interpret limitations |
| **11: research package** | Locked code and tests; full synthetic reproduction; eight-page progress report; figures; public overview page; data request and handoff guides | Actual results and final interpretation; another person's reproduction; final portfolio publication/update |

No generated template has been turned into a person's approval. No synthetic
prediction has been presented as a market result. No primary final score exists.

## Observed pilot evidence

The source checkpoint contains **155 original filings, 135 annual pairs and 20
issuers**. The seven acceptance years 2015–2021 contain 19, 19, 19, 19, 19, 20 and
20 pairs. Only **59** are in 2019–2021, below the original plan's 100–150-pair
target for those years. The longer pilot is a useful parser sample, but cannot
stand in for the planned historical investment universe.

All 155 source checks reproduce. The audit retains 14 registered reference
resolutions and 72 differences between API timestamps and original SGML headers.
The original header determines the event clock; dissemination/availability
assumptions remain explicit.

All 135 provisional candidate label/control calculations independently reconcile
to raw CSV decimal arithmetic within `1e-12`. The maximum absolute difference is
`1.429412144204889e-15`. The original candidate-calculation and independent-trace
artifact hashes reproduce. DuckDB files may differ in container metadata; no
whole-bundle byte-equivalence claim is made.

Human filing reviews and human trace passes remain zero. Seven candidate events
retain header-CIK differences, and 135 historical candidate links retain an
unresolved open-ended marker. These arithmetic successes do not approve the
identity, share class, source release or historical information availability.

Sources: [pilot checkpoint](pilot_checkpoint/pilot_checkpoint.json),
[candidate arithmetic receipt](pilot_arithmetic_summary.json), and
[review follow-up](review_followup_summary.json).

### Descriptive text results

| Measure | Observations | Median | 10th–90th percentile |
|---|---:|---:|---:|
| Current section tokens | 135 | 7,601 | 3,448–12,675 |
| Log length change | 135 | 0.04595 | −0.02304–0.16979 |
| Jaccard distance | 135 | 0.09816 | 0.03452–0.22031 |
| TF-IDF cosine distance | 116 | 0.003867 | 0.001040–0.01314 |

TF-IDF vocabulary is fitted only on earlier acceptance years for these descriptive
exhibits. The first 19 pairs have no prior pilot vocabulary and remain unavailable.
This is a text description, not evidence that the variables predict returns.
Source: [public text features](pilot_checkpoint/text_features.csv).

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
Separate semantic tests use an explicitly synthetic toy encoder. The actual
MiniLM backend has not run; runtime and manual semantic validation remain open.

These are automated and assistant checks. They do not complete the plan's
independent-person reproduction requirement.

## Reproduction and artifacts

```bash
make reproduce-full
make research-report
```

The first command works with public code and invented data. The second builds
the progress PDFs from the public SEC-only exhibits and saved audit receipts.
`make pilot-checkpoint` additionally needs the recovered private source cache
and matching source audit. Licensed market rows remain excluded from Git.

- [Research progress report — eight pages](research_progress/Research_Progress_Report.pdf)
- [Pilot checkpoint report — four pages](research_progress/Pilot_Checkpoint_Report.pdf)
- [Research overview](index.html)
- [Full data request](../docs/full_study_data_request.md)
- [Historical dataset contract](../docs/historical_dataset.md)
- [Freeze and final evaluation](../docs/final_evaluation.md)
- [Robustness methods](../docs/robustness.md)
- [Semantic comparison](../docs/semantic_analysis.md)

## Exact next empirical step

Obtain the full dated population, liquidity, identity and development-return
exports described in the request, while staging final outcomes separately.
The first liquidity window starts **October 7, 2009**; late-2025 filing labels
require coverage through **February 3, 2026**. Complete the source-bound human
reviews against the existing evidence, then run development and freeze the
actual procedure. The remaining commands and reports can then consume approved
empirical inputs without changing the primary design.
