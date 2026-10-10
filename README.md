# Disclosure Drift: Risk Disclosures and Return Forecasting

[![Research integrity checks](https://github.com/michaelbawuah/Disclosure-drift/actions/workflows/checks.yml/badge.svg?branch=main)](https://github.com/michaelbawuah/Disclosure-drift/actions/workflows/checks.yml)

Do year-over-year changes in annual risk disclosures improve 20-session return
forecasts for historically selected large, liquid U.S. stocks?

The repository implements historical universe selection, audited dataset
assembly, chronological development, a fingerprinted model freeze, gated annual
final evaluation, and secondary diagnostics. An end-to-end demonstration uses
invented data. **The empirical study remains unfinished: the actual 2022–2025
final evaluation has not been opened and no predictive result is claimed.**

The [frozen protocol](protocol.md) remains unchanged: initial training in
2010–2015, development in 2016–2021, final evaluation in 2022–2025, and unranked
20-session stock-minus-market total returns. The primary ridge comparison adds
all three text features to the same market controls.

## Current evidence and deliverables

| Evidence | Verified scope |
|---|---|
| Expanded SEC pilot | 215 original filings, 180 annual pairs, 35 issuers; 104 pairs in the planned 2019–2021 window |
| Source audit | 215 automated passes; 19 reference resolutions reproduced; 104 API/header timestamp differences preserved |
| Completed user review | 20/20 independent numerical and printed-timing checks recorded against the exact original packet |
| Candidate market arithmetic | All 135 candidate calculations reconcile independently within 1e-12; historical identities remain unapproved |
| Actual semantic execution | Pinned MiniLM on the original 155 filings / 135 pairs; full token coverage and numerical reproducibility checks; human semantic judgment pending |
| Historical data collection | Runnable, resumable WRDS catalog/export/verification tooling; actual full-study exports still needed |
| Full software demonstration | 192 invented annual memberships; 144 development and 48 separately staged final observations |
| Empirical completion | Full historical exports, source-bound human reviews, development selection and final estimates remain pending |

Start with the [latest execution update](reports/RESEARCH_EXECUTION_UPDATE.md),
[Milestones 6–11 progress record](reports/MILESTONES_06_11.md),
[expanded text checkpoint](reports/pilot_expansion/pilot_checkpoint.json),
[actual semantic validation](reports/semantic_validation/report.md),
[review progress](docs/review_progress.md), and [project overview](reports/index.html).
The [eight-page progress PDF](reports/research_progress/Research_Progress_Report.pdf),
[four-page pilot PDF](reports/research_progress/Pilot_Checkpoint_Report.pdf), and
[earlier build receipt](reports/build_verification.json) preserve the original
20-issuer snapshot from before this expansion and actual encoder run.
Earlier [M4](reports/MILESTONE_04.md) and [M5](reports/MILESTONE_05_PROGRESS.md)
reports remain part of the audit trail.

## Reproduce the software

Install [uv](https://docs.astral.sh/uv/), then run:

```bash
git clone https://github.com/michaelbawuah/Disclosure-drift.git
cd Disclosure-drift
make reproduce-full
```

This synchronizes `uv.lock`, runs Ruff and pytest, verifies the protocol,
rebuilds the development/market demos, and runs the complete synthetic study in
a new output directory. It exercises historical selection, audited joins,
development selection, the freeze, four final-year refits, paired three-/six-month
bootstraps, six feature ablations, subgroup/error diagnostics, and independent
source arithmetic for delays 1, 2 and 5.

The synthetic fixture keeps `model_ready=False`, zero human approvals, and
explicit invented identifiers. Synthetic predictions cannot authorize an
empirical evaluation. Their scores are software checks, not market findings.

Python 3.12 is the verified runtime. Base dependencies are pandas, NumPy,
scikit-learn, PyArrow, DuckDB, exchange-calendars, HTTPX and lxml. Optional
`report` and `semantic` dependency groups are locked separately.

```bash
make research-report                    # rebuild public figures and progress PDFs
uv run --locked disclosure status       # show remaining research gates
uv run --locked disclosure --help       # all source/audit/model commands
```

Licensed inputs are absent. Reproducing the actual SEC/market audits additionally
requires the source snapshots and review bundles described in the contracts.

## Build the empirical study

The [full data request](docs/full_study_data_request.md) specifies the required
historical exports. Return coverage extends through **February 3, 2026** for
late-2025 filing labels. Development and final-return exports remain separate.
Use the [manual browser-export guide](docs/wrds_daypass_export.md) for a WRDS
website Access Pass/Daypass. With authenticated database access, the
[WRDS execution guide](docs/wrds_full_export.md) supplies the runnable catalog,
source-binding, monthly export, resume and offline assembly commands.
Start with development population selection years 2010–2021. Both holdout
population price/volume windows and holdout return collection require completed
development prerequisites.
The [historical dataset contract](docs/historical_dataset.md) defines every
normalized input and source-bound review record.

```bash
# Offline source request; use a new output directory.
uv run --locked disclosure plan-full-export --output outputs/full-export-request

# Select from the full historical population.
uv run --locked disclosure build-universe \
  --manifest data/private/universe_inputs.json --output data/processed/universe

# Requires a real identifying SEC_USER_AGENT and a historical universe bundle.
uv run --locked disclosure ingest-universe \
  --universe data/processed/universe --partition development \
  --output data/processed/full-development-filings

# Audited normalized pairs, labels, controls and selected memberships.
uv run --locked disclosure build-dataset \
  --manifest data/private/development_inputs.json \
  --output data/processed/development

uv run --locked disclosure develop \
  --bundle data/processed/development --output outputs/development
```

The example `data/private/*.json` paths are contracts to populate with actual
exports and evidence; they are not supplied approved data. `develop` only accepts
a validated dataset bundle. Renaming an arbitrary Parquet file cannot pass the
evidence checks.

Once source reviews, development choices and secondary specifications are
complete, follow the [freeze and final-evaluation guide](docs/final_evaluation.md).
Holdout filing ingestion and dataset assembly require freshly validated
development prerequisites. Final targets are stored apart from final features.

```bash
uv run --locked disclosure freeze-development \
  --request data/private/freeze_request.json --output outputs/development-freeze

uv run --locked disclosure evaluate-final \
  --freeze outputs/development-freeze --output outputs/final-evaluation

uv run --locked disclosure robustness \
  --freeze outputs/development-freeze --final-run outputs/final-evaluation \
  --output outputs/robustness
```

Missing evidence leaves explicit blockers. A generated review template, an
assistant-authored check, or a boolean approval flag cannot substitute for the
required person's source-bound review. Fingerprints detect changes; they are an
audit trail and do not authenticate a reviewer's identity.

## Rebuild the pilot checkpoint

The expanded document-format pilot has **104 pairs in 2019–2021**, meeting the
original plan's 100–150-pair count criterion. It contains 215 filings and 180
pairs overall. Historical investment-universe selection, source judgments and
the approved controls smoke remain separate requirements.

```bash
make pilot-expand
```

This collects 15 additional issuers, preserves all original 135 pairs, and
rebuilds the combined audit and descriptive checkpoint. See the
[source corrections and reproduction guide](docs/pilot_expansion.md).
`make pilot-checkpoint` retains the original 155-filing snapshot workflow.
Both read SEC text only and publish source links, distributions and coverage. The
controls-only `pilot-baseline` command exists but requires an approved dataset;
it has not been run on the unapproved candidate market calculations.

Earlier workflows: [filing audit](docs/filing_audit.md),
[reference resolution](docs/reference_resolution.md),
[CRSP staging](docs/crsp_staging.md),
[historical identity review](docs/identity_review.md), and
[candidate arithmetic review](docs/pilot_arithmetic_review.md).
`make pilot-resolved-reproduce` rebuilds the full source comparison when
the original cached documents are available.

## Statistical and access safeguards

- The reference date is the second XNYS session strictly after the New York
  acceptance date. Controls stop at the preceding close; returns start after
  the reference close and span exactly 20 sessions.
- Historical selection uses the prior 60 sessions of dollar volume, at least
  40 valid observations, dated common-stock/identity evidence, and one share
  class per issuer. Later delistings do not remove historical members.
- Preprocessing is fitted on each annual training set. Only earlier events
  whose labels have matured before that year's first prediction are eligible.
- Baseline and augmented ridge penalties are selected separately from four
  declared values using pooled 2016–2021 development MSE.
- The primary score is `1 - SSE(text + controls) / SSE(controls)` on identical
  observations. Paired moving-month blocks preserve all firms and empty
  calendar months; 2,000 draws use three-month blocks and a six-month sensitivity.
- The freeze binds code, protocol, inputs, selection, source evidence and
  secondary choices. A durable access ledger rejects a changed freeze after
  empirical final access. Exact reproduction of the same freeze is allowed.
- [Robustness methods](docs/robustness.md) retain small, constant, missing and
  undefined groups explicitly. Delay checks rebuild controls and labels from
  source data; they do not shift an existing target column.
- The pinned [semantic comparator](docs/semantic_analysis.md) is a separate
  retrospective analysis. Its chronology cannot support historical availability
  claims, and manual example validation is pending.

## Project map

| Component | Purpose |
|---|---|
| `edgar.py`, `extraction.py`, `ingest.py`, `audit.py` | SEC provenance, extraction, annual pairing and source review |
| `market.py`, `market_data.py`, `labels.py`, `controls.py` | Historical identities, exact windows, total returns and prior controls |
| `crsp_staging.py`, `identity_review.py`, `pilot_audit.py` | Vendor normalization and independent candidate arithmetic |
| `universe.py`, `dataset.py`, `study.py` | Historical selection, source-bound model datasets and full-study collection |
| `features.py`, `modeling.py`, `freeze.py`, `final_evaluation.py` | Training-only features, development, frozen choices and annual final refits |
| `robustness.py`, `robustness_run.py` | Declared comparisons, source rebuilds and verified-run orchestration |
| `semantic.py`, `semantic_model.py` | Pinned complete-token retrospective features and separate secondary models |
| `pilot_checkpoint.py`, `reporting.py`, `full_demo.py` | Observed text exhibits, PDFs and full synthetic reproduction |
| `tests/`, `configs/`, `docs/`, `reports/` | Integrity checks, frozen decisions, contracts and public progress |

## Research context and ownership

The idea is inspired by Cohen, Malloy and Nguyen's
[*Lazy Prices*](https://doi.org/10.1111/jofi.12885). This annual Risk Factors,
20-session design is a separate investigation; that paper's results are not
evidence about this study's sample.

The code and draft reports were co-developed with Codex. The
[decision log](docs/decision_log.md) and [experiment log](docs/experiment_log.md)
separate automated checks, human review, synthetic runs and empirical results.
Final interpretation must report the actual estimates, including negative or
inconclusive outcomes, after the remaining data and review requirements are met.
