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
| Original SEC identity evidence | 215/215 primary files, headers, acceptance clocks and unique manifest-filer matches reverified; 218 filer observations include three legitimate Comcast co-filings |
| Lexical cover evidence | 1,494 cover facts retained from 79 filings; 136 have no supported inline cover facts, which is a coverage observation rather than an identity exclusion |
| Completed user review | 20/20 independent numerical and printed-timing checks recorded against the exact original packet |
| Filing review | Assistant boundary/timing review covers all 73 distinct filings in the fixed-pair/reference packet: 63 prior records preserved and 10 new reviews; no human filing review created |
| Candidate market arithmetic | All 135 candidate calculations reconcile independently within 1e-12; historical identities remain unapproved |
| Conditional SEC-backed modeling diagnostic | 135 original filing pairs joined one-to-one to provisional market controls; 116 paired expanding-year predictions per fixed-alpha model, **unapproved and not a validated predictive finding** |
| Independently reconstructed 2020 pilot issuer anchors | **20/20** securities with original SEC issuer CIK and dated CRSP Names corroboration; 419 strictly earlier observations, 5 cutoff-day unknown, 1 current-header conflict; **historical continuity/availability unapproved** |
| Original 10-K TradingSymbol corroboration | 43 of 135 development filings have cover-page lexical symbols with same-date exact CRSP Names candidates; 17 single/clean/unhidden; multiple-class and historical availability remain unapproved |
| Development event identity matrix | All 135 original SEC events independently reconcile **10,935/10,935** dated Names session checks, 135 single CCM candidates and PERMCO checks; six descriptor transitions, seven current-header conflicts; **no historical known-at or mapping approval** |
| Original 10-K stock-class lexical context triage | All **41** doubly corroborated pilot filings reviewed for exact original SEC symbol/context, title and exchange: **19** standard common-stock members (**16** with no structural warning), **4** issuer-specific-only, **18** no standard class axis; **no XBRL semantic or historical identity approval** |
| Paired-year registered-security review | The **16** strongest lexical SEC stock contexts form **eight consecutive annual issuer pairs**, each with stable reported symbol, title and exchange; **14** say Common Stock and **two** say Capital stock, which remains unapproved |
| Direct SEC original-byte reinspection | All **16** shortlisted 10-K HTML and 16 SEC headers fetched on Mac; headers match prior hashes, HTML differs uniformly by four bytes, but **16/16 full lexical source reports** and **16/16 direct DOM stock contexts** reproduce exactly; historical known-at still unknown |
| IBM SEC Exhibit 4.1 registered equity corroboration | Both original 2019 and 2020 year-end exhibits identify **one issued/outstanding equity class** with voting, dividend and residual rights under ticker IBM; resolves the two Capital stock wording review leads without certifying the historical CRSP mapping |
| SEC-only disclosure-drift descriptive study | Original **215 SEC filings / 180 annual Item 1A comparisons / 35 issuers**; within **34 balanced 2019–2021 issuers**, mean Jaccard turnover rose **+0.0460** (27/34 increased). **Exploratory text description only, no return forecast or causal claim** |
| Public daily market cross-check | Independent Fama–French factor series covers all 3,103 saved CRSP development sessions, but different market definitions/releases prevent automatic benchmark substitution |
| Actual semantic execution | Pinned MiniLM on the original 155 filings / 135 pairs; full token coverage and numerical reproducibility checks; human semantic judgment pending |
| Development market processing | Four manual daily batches, Names, CCM/company and market exports preserved locally; 22,588,059 provisional numerical rows cover all 3,103 requested sessions |
| Annual candidate evidence | 86,064 Names snapshots, 50,230 provisional liquidity ranks, and 100,261 Names/CCM relationships; historical identity and availability remain unapproved |
| Historical foundation reconciliation | All 87,405 annual observations retained; full Names history explains all 1,341 liquidity-only records by saved security lifetimes ending before selection; identity evidence gaps across 50,230 rank-eligible candidates remain |
| Complete filing-date Names history | All 207 existing discoveries have unique descriptors at all 16,974 required role/date observations; all 15 January-snapshot date questions resolved; the original current-header ledger retains eight unmatched Exxon filings |
| Complete 2020 SEC cohort reconciliation | All 4,122 eligible security observations and all 38,145 original SEC occurrences retained; 3,105 securities have unambiguous earlier literal observations; 987 remain without usable quarterly observations |
| Original ownership-filing follow-up | All 47 selected missing/unsupported-header cases have original issuer CIK/name/symbol agreement; all source occurrences, amendments and reporting-owner roles preserved |
| Multiple-CIK original-source follow-up | All 14 selected original filings across seven cases reproduce the quarterly issuer metadata; eight separate issuer documents distinguish four symbol inconsistencies and three corporate-structure cases |
| Cutoff-day original clocks | All 39 filings across 14 cases resolved against the December 31, 2019 close: 16 before and 23 after; three cases have only before-close clocks and eleven only after-close clocks |
| Exxon historical identity follow-up | Current header refers to a later successor; eight historical issuer/CUSIP observations and unique Names candidate coverage at all 656 required window points and eight selections; continuous identity/availability remains unresolved |
| Historical revision check | Four saved annual snapshots within a published CRSP correction interval disagree with its corrected classification literals; the exact source vintage remains unresolved |
| Benchmark source evidence | All five audited source bindings preserved; 52 exact-comparison differences remain unexplained; a source-backed reviewed benchmark choice is pending, with no tolerance or replacement accepted |
| Full software demonstration | 192 invented annual memberships; 144 development and 48 separately staged final observations |
| Empirical completion | Historical CIK/availability evidence, reviewed source choices and normalization, remaining judgments, approved universe, development selection and final estimates remain pending |

See the [no-new-WRDS exploratory route](docs/sec_backed_alternative_pilot.md)
its [aggregate-only verification checkpoint](reports/alternative_pilot_checkpoint.json),
and the [byte-identical independent rerun](reports/alternative_pilot_reproduction.json)
for a development-only feasibility analysis. Its source/identity and review gates
remain closed; conditional predictions stay private. This is not the final study.

A [separate source-audited SEC-only descriptive study](docs/sec_only_descriptive_study.md)
now reports measured original Risk Factors vocabulary turnover and a
[year-by-year chart](reports/sec_only_descriptive_balanced_means.svg) without
waiting for historical CRSP mapping permission. The source-bound
[independent numerical recheck](reports/sec_only_descriptive_independent.json)
and [repeat-run reproducibility receipt](reports/sec_only_descriptive_reproduction.json)
verify every issuer difference and bootstrap estimate and establish
byte-identical aggregate outputs. This is an **exploratory original
SEC text result, not a claim of predictive uplift**.

The [source-pinned IBM SEC Exhibit 4.1 equity review](docs/ibm_capital_stock_exhibit_review.md)
its [independent source-text corroboration](reports/ibm_capital_stock_exhibit_independent.json),
and [byte-identical verification receipt](reports/ibm_capital_stock_exhibit_reproduction.json)
explain the two outstanding `Capital stock` descriptions using the issuer's
original 2019/2020 securities registration exhibits, preserving closed
research approvals and source-vintage caveats.

The [direct original SEC document reinspection](docs/sec_original_live_reinspection.md)
now reproduces all 16 saved source lexical/context audits directly from freshly
downloaded SEC HTML and headers. The [independent current-document DOM review]
(reports/sec_original_dom_independent.json) and
[byte-identical reparse record](reports/sec_original_live_reproduction.json)
bind this checkpoint to the original SEC bytes and 1,181 passing tests. The
four-byte original HTML hash differences remain recorded—not silently
corrected—and source publication times and historical links remain unapproved.

The [source-bound eight-issuer registered-stock pair review](docs/paired_stock_class_review.md),
its [aggregate checkpoint](reports/paired_stock_class_checkpoint.json),
[independent verification](reports/paired_stock_class_independent.json)
and [byte-identical reproducibility record](reports/paired_stock_class_reproduction.json)
provide a narrower private next-review packet without claiming eligible
stock classes or historical data availability.

The [41-filing original SEC cover stock-class review](docs/sec_cover_class_review.md)
its [source-pinned aggregate result](reports/sec_cover_class_checkpoint.json),
[independent original-context verification](reports/sec_cover_class_independent.json),
and [byte-identical repeat-run receipt](reports/sec_cover_class_reproduction.json)
narrow the documentary review queue without equating ticker strings with
approved stock classes.

The [read-only 135-event historical identity review matrix](docs/development_identity_matrix.md)
and its [independently reconstructed source receipt](reports/development_identity_matrix_independent.json)
and [byte-identical rerun verification](reports/development_identity_matrix_reproduction.json)
provide a concrete private filing-by-filing handoff while keeping all research
gates closed.

See the [original 10-K symbol-source corroboration](docs/tenk_symbol_corrob.md), its [aggregate checkpoint](reports/tenk_symbol_corrob_checkpoint.json), and the source review limits.

See the [2019Q4 original-source 20-issuer anchor](docs/pilot_issuer_anchor.md), its [aggregate audit](reports/pilot_issuer_anchor_checkpoint.json), and [independent raw-source reconstruction](reports/pilot_issuer_anchor_independent.json).

Start with the [latest execution update](reports/RESEARCH_EXECUTION_UPDATE.md),
[cutoff-day clock results](docs/ownership_cutoff_clock_results.md),
[multiple-CIK findings](docs/ownership_multi_cik_findings.md),
[actual 2020 issuer-corroboration results](docs/sec_ownership_results.md),
[Exxon current-header diagnosis](docs/exxon_candidate_diagnostic.md),
[complete Names-history results](docs/dated_names_results.md),
[historical foundation results](docs/historical_foundation.md),
[Milestones 6–11 progress record](reports/MILESTONES_06_11.md),
[expanded text checkpoint](reports/pilot_expansion/pilot_checkpoint.json),
[actual semantic validation](reports/semantic_validation/report.md),
[review progress](docs/review_progress.md), and [project overview](reports/index.html).
The [completion and reviewer handoff](docs/research_completion_gates.md) separates
completed engineering checkpoints from the remaining empirical gates and uses
the existing review packets.
**October 11, 2026 (UTC):** Michael Baffour Awuah authorized the assistant to
perform the remaining filing review. The [completed records](reports/filing_review/assistant/README.md)
now cover all 73 filings and are accepted by the original-source audit.
Open `reports/filing_review/assistant/index.html` on your Mac to inspect the
recorded findings. The 73 assistant checks do not need to be repeated manually.
The [short review guide](docs/filing_review.md) retains instructions for a
separate personal review; the original pending packet and generation receipt
remain unchanged. Required human judgments and empirical gates remain separate.
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
uv run --locked disclosure status       # static published progress checklist
uv run --locked disclosure --help       # all source/audit/model commands
```

The status command does not inspect or validate private bundles. Licensed inputs
are not distributed in this repository. Reproducing the actual SEC/market audits
additionally requires the source snapshots and review bundles described in the
contracts.

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

The preserved development exports have already been processed on the Mac; a
fresh upload or download is not required for the completed candidate work.
The [new complete-cohort reconciliation](docs/sec_ownership_results.md) ran at
`5a96224`, retaining all 4,122 eligible 2020 securities, source conflicts and
unmatched cases. Its [source-bound consumer](docs/sec_ownership_corrob.md) creates
dated issuer observations and a complete original-source follow-up queue.
The [47 original-filing checks](docs/sec_ownership_original_followup.md) confirm
selected issuer observations without promoting them to historical security links.
The subsequent [seven-case original-source audit](docs/ownership_multi_cik_findings.md)
shows why even a unique ticker match requires issuer and share-class evidence.
The [complete cutoff-day follow-up](docs/ownership_cutoff_clock_results.md) resolves
all 39 original acceptance clocks while keeping public availability separate.
The [latest complete-history checks](docs/dated_names_results.md) resolve the
specific descriptor-date questions while retaining all original evidence.
The [identity execution record](reports/wrds_identity_evidence_execution.json)
and [benchmark source-evidence record](reports/wrds_benchmark_source_evidence_execution.json)
bind the completed candidate and discrepancy packets. The next historical-identity source lead is
documented in the [Company History access research](docs/historical_identity_access_evidence.md),
which includes an unsent request for the authorized schema/export, coverage,
release and availability evidence. Candidate relationships are not approved
universe inputs.

The new [original SEC execution record](reports/sec_identity_evidence_execution.json)
documents a successful 29.560-second run at `3a5b368`, completed on 11 October
2026 UTC. The [complete compressed evidence](reports/sec_identity_evidence.json.gz)
retains original-source bindings, co-filers and lexical cover contexts. The
separate [discovery-ledger inspection](reports/sec_identity_discovery_context.json)
accounts for all 215 manifest records: 207 discovery matches and eight unmatched
Exxon filings under original SEC CIK `0000034088`. That inspector reads manifest
and coverage evidence; original SEC bytes were reverified by the separate source
run. These observations create no approved historical security mapping.
The [subsequent Exxon audit](docs/exxon_candidate_diagnostic.md) explains that
specific current-header mismatch and supplies separate dated CUSIP candidates;
it preserves the original 207/215 discovery accounting.

The [benchmark source proposal](docs/benchmark_source_decision.md) makes the
remaining decision concrete: review a documented value-weighted total-return
series for the identical label sessions while preserving all 52 unexplained
differences. Exact agreement between export views is not a frozen requirement.
No proposed source choice or human approval has been enacted; the prepared
external questions remain unsent.
The [recovered native CRSP definition](docs/benchmark_primary_definitions.md)
now identifies the index and total-return field to check against those saved
views. The [public SEC source demonstration](docs/public_historical_identity_sources.md)
also supplies dated issuer-corroboration routes. Neither investigation establishes
the missing source version, availability or approved historical security links.

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
