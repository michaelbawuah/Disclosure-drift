# Research completion gates and reviewer handoff

Updated 11 October 2026. **The immediate source requirement is now measured:
historical CIK intervals, unresolved security links, and actual source-version
and availability evidence.** The [completed foundation reconciliation](historical_foundation.md)
preserves all 87,405 annual observations and quantifies the gaps among 50,230
provisionally rank-eligible rows. The [complete Names-history results](dated_names_results.md)
resolve all 15 filing-date snapshot questions and explain all 1,341 liquidity-only
observations by recorded security lifetimes ending before selection. They do not
approve historical identities, availability or research exclusions.
A [published historical correction check](historical_availability_evidence.md)
also exposes four saved annual classification discrepancies. The 73 assistant
filing reviews and the user's 20/20 arithmetic review retain their completed
credit. Required human judgments remain distinct. Current execution evidence is in the
[research update](../reports/RESEARCH_EXECUTION_UPDATE.md).

This guide interprets the existing [frozen protocol](../protocol.md),
[historical dataset contract](historical_dataset.md) and
[final-evaluation contract](final_evaluation.md). It changes none of them and
records no new approval, benchmark selection, timestamp or external message.

## What completion means

Milestones **1–4 are completed engineering/source-verification checkpoints**:
the executable foundation, filing audit, registered reference resolution and
expanded source verification with market-data staging. Their successful tests
and source reproductions do not complete the empirical gates in **5–11**.
The [milestone report](../reports/MILESTONES_06_11.md) distinguishes implemented
software and measured preparation from the following remaining outcomes.

| Milestone | Evidence needed to finish its empirical work |
| --- | --- |
| 5: source and arithmetic audit | Supported identity/class/interval and market normalization, source availability and remaining filing/full-source trace judgments. **The user's 20/20 arithmetic and printed-timing review is already complete.** |
| 6: pilot checkpoint | Reviewed model inputs, the real fixed-alpha controls-only smoke and independent reproduction of the permitted examples; existing text counts/descriptions retain their credit. |
| 7: full dataset | A defensible historical issuer universe, complete predecessor searches, reviewed extraction and normalized labels/controls, with explained coverage and exclusions. |
| 8: development and freeze | Actual 2016–2021 development comparisons, completed declared secondary decisions/reviews, and a freeze binding the real choices and evidence. |
| 9: final evaluation | Approved separate 2022–2025 inputs and the measured annual predictions, primary comparison and intervals. |
| 10: robustness | The declared empirical diagnostics, ablations, independently rebuilt timing alternatives and source-linked failure review. |
| 11: research package | Actual results and limitations, reproducible permitted artifacts, another person's reproduction and the final research presentation. |

The separate 2026 cohort and a trading strategy are not requirements for this
primary study. Numerical preparation and a runnable synthetic study are useful
deliverables; neither establishes forecast performance.

## 1. Finish decisions supported by existing evidence

### Filing boundaries, annual pairs and reference cases

Start with these existing materials; preserve their selected cases and evidence
identifiers:

The [local filing-review page](../reports/filing_review/index.html) is the current
recording interface. It combines the fixed 30 pairs and all 24 matching reference
cases into 73 distinct filings, with saved drafts and a validated export. The
[Mac guide](filing_review.md) explains the next steps. The source packets below
remain available for comparison; manual JSON editing is optional.

| Material | Reviewer action |
| --- | --- |
| [Expanded reading packet](../reports/expanded_audit.html) and [fixed 30 pairs](../reports/expanded_review_pairs.csv) | Inspect both complete filings for each selected pair: true Item 1A boundaries, included/omitted material, immediate original annual predecessor and timing interpretation. The 30 pairs involve 58 distinct filings. |
| [Reference packet](../reports/reference_audit.html), [reference pairs](../reports/reference_review_pairs.csv) and [boundary policy](reference_resolution.md) | Review the registered indirect disclosures and method transitions. These cases and other flagged filings remain required in addition to the fixed sample. |
| [Expanded pending template](../reports/expanded_reviews.template.jsonl) and [reference pending template](../reports/reference_reviews.template.jsonl) | Copy to separate review files, retain the original accession/fingerprint, and record only actual decisions. Unreviewed rows remain pending. |

The [M5 follow-up](review_followup.md#where-the-30-pair-filing-packet-is) also
locates the already prepared private `filing_pairs_30.html`. Use it when available;
there is no need to regenerate the same packet or reselect a sample.

Each completed filing decision needs `boundary_verdict` and/or `timing_verdict`
(`pass` or `fail`), the actual reviewer, `reviewer_type`, the actual timezone-aware
`reviewed_at`, and substantive notes. Disclose assistant help. A timing pass may
confirm correct SEC-header interpretation and the declared exchange-session
proxy; it does not assert verified public dissemination. Review the full source,
not only its displayed boundary snippets. A filing counts as human-reviewed
only when both verdicts pass and its source checks succeed. See the
[review workflow](filing_audit.md#review-and-record).

After recording real decisions, the existing offline CLI can recheck their
fingerprints against the preserved source tables and cache. The following
review-file/output names are proposed new paths, not completed artifacts. Use
the table/cache paths belonging to the reviewed packet and retain prior outputs:

```bash
uv run --locked disclosure audit \
  --filings data/processed/pilot-resolved/filings.parquet \
  --pairs data/processed/pilot-resolved/filing_pairs.parquet \
  --cache data/raw/sec_cache \
  --reviews data/reviews/filings-v1/expanded.jsonl \
  --output outputs/audit-pilot-human-v1

uv run --locked disclosure audit \
  --filings data/processed/references/filings.parquet \
  --pairs data/processed/references/filing_pairs.parquet \
  --cache data/raw/sec_cache \
  --reviews data/reviews/filings-v1/references.jsonl \
  --output outputs/audit-references-human-v1
```

These arguments are implemented in the [CLI](../src/disclosure_research/cli.py).
Changed evidence invalidates its old review. A source-audit exit code of zero
does not establish human completion. Its `manual_audit` summary concerns every
filing in that supplied table, so a completed sample need not make that
dataset-wide field complete. Neither signal replaces the later scoped dataset
evidence checks.

### Preserve completed arithmetic; review only the remaining claims

The [recorded user review](review_progress.md) credits all **20/20** arithmetic
and printed-timing passes. Its original review time is unknown and stays unknown.
The preserved older pending draft does not revoke this credit. Do not repeat
the calculations or invent a timestamp to make a broader importer accept them.

The assistant's checks of 2,040 cited source references are separate evidence.
Remaining judgments concern original-source traces, historical security/class
identity, interval interpretation, release and availability. The
[trace review contract](review_followup.md#review-fields) is broader than the
completed printed-packet review; importing it requires actual review of those
additional claims, with the existing IDs and source references preserved.

### Filing availability and semantic review can proceed now

For filing pairs, [the contract](historical_dataset.md#2-normalized-dataset-inputs)
permits `availability_status: documented_assumption` with explicit evidence and
human review. The frozen reference is the second XNYS session strictly after the
SEC acceptance date in New York. `verified` availability additionally requires a
supported `public_available_at`; any supplied timestamp must satisfy the stated
acceptance/prediction bounds. Known timing violations are excluded. Exact
first-publication timestamps or archival SEC logs are not universal prerequisites.

The existing [semantic validation](semantic_validation.md) has already run the
pinned model and saved the unchanged, rewording and new-risk examples. Review
those examples rather than rerunning embeddings. The
[secondary specification](../configs/secondary_analysis.json) explicitly permits
the pinned comparator as **retrospective only**, with unknown cutoffs retained
and no historical checkpoint-availability claim. Its eventual freeze still needs
bound chronology/limitation evidence, the actual human example review and its
declared development-model comparison. Unknown training dates do not require
replacing the primary three text features or inventing a point-in-time claim.

## 2. Obtain the missing historical facts and decide normalization

| Evidence gap | Most direct next input and its limit |
| --- | --- |
| Historical CIK/security links | Obtain authorized historical CIK values with effective bounds, schema, coverage and release evidence. [CRSP/Compustat Company History `HCIK`](historical_identity_access_evidence.md) is a documented lead, not a mandatory product. Saved CCM link dates do not date its current header CIK. |
| Historical listing/identity `known_at` and liquidity `available_at` | Obtain evidence explaining historical availability under the [universe contract](historical_dataset.md#1-historical-selection). Effective dates, retrieval dates and query success are insufficient; the filing-specific documented-assumption option does not silently relax these fields. |
| Source normalization and population coverage | Resolve the specific [source-convention questions](wrds_source_conventions.md): release/dictionary applicability, units, share classes, missing-return codes, terminal payoff handling, projected duplicates and supported identity bounds. Review the resulting mappings and exclusions against the eligible population. |
| Benchmark source | Review the [bound source evidence](wrds_benchmark_source_evidence.md) and [pending source proposal](benchmark_source_decision.md), and obtain enough source-definition/vintage evidence for a documented choice. Keep the observed discrepancy evidence and any unresolved limitation. |

The [recovered native CRSP definition](benchmark_primary_definitions.md) now
identifies `INDNO=1000200` and `IndDlySeriesData.DlyTotRet` for checking the saved
WRDS benchmark views. It does not prove their mapping, vintage or formatting;
all 52 discrepancy causes remain unresolved. The
[public SEC demonstration](public_historical_identity_sources.md) supplies
dated issuer/CUSIP/class corroboration leads without creating a continuous
historical security crosswalk or filling availability fields.

Historical identity must be defensible for retained memberships/events, with
population coverage and exclusions reviewed. It is not necessary to resolve
every unrelated record in the raw CCM history. Missing or ineligible records can
lead to explicit exclusions under the contract; silently selecting convenient
survivors or deleting unresolved failures cannot establish completeness.

**The benchmark gate is a source-backed decision, not forced equality between
two export views.** The [protocol](../protocol.md) requires a value-weighted
total-return benchmark over the identical label sessions.
[`validate_manifest`](../src/disclosure_research/market_data.py) requires the
declared convention, benchmark description and source/normalization provenance;
it does not impose cross-view equality. The 52 observed differences remain
unexplained. A later reviewed choice may retain that limitation, but this guide
chooses no source, accepts no tolerance and does not relabel the audit's exact
comparison as reconciled. The market comparison alone establishes no error in
individual stock returns.

The historical-access request and benchmark question drafts remain **unsent**.
They do not constitute vendor replies, access grants or reviewer decisions.

## 3. Turn reviewed evidence into the empirical run

The [dataset evidence contract](historical_dataset.md#3-evidence-and-review-contract)
requires human-reviewed coverage for every retained event's filing, pair,
availability, label, controls and universe evidence, plus the normalization
record. A record's explicit `subjects` may cover several events; separate
signatures for every raw numeric row are not required. The scope, source-table
hashes and underlying artifacts must support every covered claim. A sample
review cannot automatically approve unseen cases. Changed evidence must be
reviewed again; a deliberate reviewed exclusion records its reason.

Once the source inputs and reviews support normalization, build the historical
issuer universe, obtain its immediate predecessor filings, finish the full-sample
audit, and assemble the reviewed development tables. A successful
`build-universe` remains a selection artifact; `build-dataset` and its reload
checks determine whether the scoped empirical dataset is approved.

Only after an approved development bundle exists, run the real pilot smoke and
development comparison. These paths are examples for that future bundle:

```bash
uv run --locked disclosure pilot-baseline \
  --bundle data/processed/development --output outputs/pilot-baseline-v1

uv run --locked disclosure develop \
  --bundle data/processed/development --output outputs/development
```

`pilot-baseline` uses the bundle's 2019–2021 subset, fixed alpha 1, and matured
training labels; it is a pipeline smoke, not an estimate of the final effect.
`develop` runs the six frozen development folds and selects actual penalties.
Then complete the secondary choices and the six source-audit judgments listed
in the [final-evaluation guide](final_evaluation.md#prerequisite-request).
Only their validated prerequisite record permits final-source access, the
freeze and evaluation. Robustness and interpretation follow the actual results.

### Readiness is established by evidence, not a status label

`disclosure status` and `disclosure evaluate-final` without `--freeze` print a
static published-progress checklist; they do not inspect the saved private
bundles or supply a live approval. The real checks are in
[`dataset.py`](../src/disclosure_research/dataset.py),
[`freeze.py`](../src/disclosure_research/freeze.py) and the
[final evaluator](../src/disclosure_research/final_evaluation.py). They verify
artifact bindings and review declarations; they cannot independently discover
vendor semantics or authenticate the reviewer. Permission to continue working
does not create those missing facts or judgments.
