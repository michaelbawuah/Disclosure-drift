# Disclosure Drift: Risk Disclosures and Return Forecasting

[![Research integrity checks](https://github.com/michaelbawuah/Disclosure-drift/actions/workflows/checks.yml/badge.svg?branch=main)](https://github.com/michaelbawuah/Disclosure-drift/actions/workflows/checks.yml)

Do year-over-year changes in annual risk disclosures improve 20-session return
forecasts for historically selected large, liquid U.S. stocks?

This repository implements the research pipeline and its audit trail. The primary
protocol is frozen in [protocol.md](protocol.md) and
[configs/protocol.json](configs/protocol.json). Initial training is 2010-2015,
development is 2016-2021, and the final evaluation period is 2022-2025.

**Current milestone: 05 in progress.** The 155-filing parser pilot is complete at
the automated-evidence level. A dated market-data request now covers its 135 events,
with 20 pending trace reviews and a tested standalone pre-event control calculator.
The received CRSP pilot has 36,000 rows covering 20 securities and 1,800 sessions.
CSV-to-Parquet/DuckDB staging now preserves source flags, USD capitalization and
dated SIC. The WFM QA export lacks a terminal row; delisting verification,
historical identity approval, source-availability review and human audits remain pending.
A private identity-review packet now checks all 155 SEC headers and assembles
dated security evidence for 135 events, with seven Exxon header-CIK differences
kept explicit. A [source follow-up](docs/identity_source_evidence.md) documents
Exxon's 2026 reorganization and verifies GE's 2021 CUSIP transition through staging.
Historical links still require approval.
The frozen final evaluation has not been opened; all model demos are synthetic.

See the [Milestone 05 progress report](reports/MILESTONE_05_PROGRESS.md),
[Cornell access check](docs/data_access_checklist.md), and
[pilot export instructions](docs/pilot_market_request.md).

| Milestone 04 evidence | Status |
|---|---|
| Complete parser pilot | 155 original filings; 135 annual pairs across 20 issuers |
| Source and extraction comparison | Original source hashes, 141 control texts and all event dates unchanged |
| Previously flagged references | All 14 source-bound resolutions reproduced in the full pilot |
| Market-data handoff | Hashed Parquet imports, DuckDB tables and audit-bound event export |
| Research-integrity tests | 103 passed locally, on macOS and in GitHub Actions |
| Filing review and empirical results | Human review and historical market data pending |

See the [completed Milestone 04 report](reports/MILESTONE_04.md),
[verification record](reports/milestone_04.json), and
[complete HTML review packet](reports/expanded_audit.html).
The [targeted reference comparison](reports/MILESTONE_03.md),
[initial 155-filing pilot](reports/MILESTONE_02.md), and
[foundation checkpoint](reports/MILESTONE_01.md) are retained as earlier evidence.

**Stack:** Python 3.12, pandas, Parquet, DuckDB, httpx, lxml, scikit-learn and NumPy.
See [technology choices](docs/technology_stack.md) for the implemented tools and
the planned report and semantic-model stages.

## Run locally

Install [uv](https://docs.astral.sh/uv/), then clone and run the project:

```bash
git clone https://github.com/michaelbawuah/Disclosure-drift.git
cd Disclosure-drift
make reproduce
```

This command synchronizes the locked environment, runs lint and tests, verifies the
protocol, and rebuilds the synthetic demo. It reproduces the current engineering
milestone; real market-data preparation and the empirical report remain pending.

Without Make, run `uv sync --locked`, `uv run --locked ruff check .`,
`uv run --locked pytest`, `uv run --locked disclosure status`, and
`uv run --locked disclosure demo` in that order.

The default environment uses Python 3.12. The declared package range also permits
Python 3.11; this milestone was verified on Python 3.12. The committed `uv.lock`
records dependency versions. All commands below run from the repository root.

The demo creates 144 invented observations and runs all six development folds for
the two models and four ridge penalties. Its numbers verify the software only.
They are not stock-market findings and must not be used as research results.

## Download the real extraction sample

Set a research User-Agent with your actual contact information, then run:

```bash
export SEC_USER_AGENT='DisclosureResearch/0.1 contact https://github.com/michaelbawuah'
uv run disclosure ingest
```

The sample includes original 2018-2021 filings for Apple, JPMorgan Chase, Exxon
Mobil, Johnson & Johnson, and Walmart, yielding up to 15 annual pairs for
2019-2021. These are document-format test cases, not the study's historical universe.

Outputs are local:

- `data/raw/sec_cache/`: immutable response bodies and hashes, keyed by URL.
- `data/processed/smoke/filings.parquet`: filing provenance and extracted sections.
- `data/processed/smoke/filing_pairs.parquet`: eligible annual pairs.
- `data/processed/smoke/research.duckdb`: queryable copies of the tables.
- `data/processed/smoke/audit_queue.csv`: boundary/timing checks for human review.
- `data/processed/smoke/ingestion_summary.json`: coverage, exclusions and failures.

A second identical run should require zero network requests. Cached SEC submission
snapshots are deliberate provenance snapshots. Use a new cache directory when
collecting a newer snapshot; do not silently mutate an old one.

## Audit the filing evidence

After downloading the sample, run `make audit`. The HTML packet in
`outputs/audit-smoke/audit.html` links the original filings and headers, shows
boundary excerpts, and preserves timestamp disagreements. DuckDB coverage tables
and fingerprinted review templates accompany it. Automated consistency is separate
from human review.

The expanded parser pilot uses 20 selected issuers and development-year filings:

```bash
make pilot-ingest
make pilot-audit
```

These commands require the same identifying User-Agent for ingestion. The pilot
is a document-format sample, not the historical investment universe. It selects
up to 30 annual pairs for review while keeping extraction failures visible.
See the [filing audit workflow](docs/filing_audit.md), including how to record
reviews and handle disclosures that point to a separate exhibit.

The reference-resolution checkpoint handles 14 known GE, Intel and J&J
cases with explicit registered ranges and original-accession exhibit verification.
It reproduces a targeted 24-filing comparison with `make reference-reproduce`.
The complete 155-filing regression comparison is rebuilt with
`make pilot-resolved-reproduce`. It yields 135 annual pairs and preserves every
unregistered extraction and original event date. See the
[boundary policy and limitations](docs/reference_resolution.md). Human review remains pending.

## Research safeguards

The tests verify holiday and after-hours timing, the exact 20-session return window,
cash after delisting, missing-price rejection, historical identity ambiguity,
training-label maturity, future-document isolation, table-of-contents rejection,
and refusal to feed final-period observations to development commands.

The primary model is ridge regression with market controls and all three text
features: length change, Jaccard distance and TF-IDF cosine distance. Vocabulary,
scaling and industry encoding are fitted only on each fold's training rows. Each
model selects its penalty on development data. The final evaluator remains gated
until access, audits, development selection and the semantic-model protocol are ready.

## Connect market data

Start with [docs/market_data_contract.md](docs/market_data_contract.md) and
[docs/data_access_checklist.md](docs/data_access_checklist.md). Verify your Cornell
WRDS entitlements and export small examples before downloading a full history.
The repository does not contain WRDS credentials or assume that any account has access.

The [import and label-staging workflow](docs/market_import.md) is runnable now.
`make market-demo` checks three invented events, including a delisting and an
explicit missing-session exclusion. `import-market` accepts documented normalized
Parquet files; it does not infer vendor mappings. `export-label-events` binds
the filing event queue to a matching source audit. `prepare-labels` produces
engineering QA tables, with pending research gates kept explicit.

For the received CIZ daily and historical Names CSVs, use the
[CRSP staging command](docs/crsp_staging.md). It creates private Parquet and DuckDB
tables with explicit incomplete-audit status. It does not create approved CIK links
or an import-ready manifest. The [source receipt](reports/market_access_samples.json)
records what was received, the completed coverage checks and the missing WFM
terminal evidence.

Use the [historical identity review command](docs/identity_review.md) to assemble
the existing SEC headers, CCM candidates and dated Names records into a private
HTML/Parquet packet. Its [aggregate receipt](reports/identity_pilot_summary.json)
records the 135-event pilot without publishing licensed rows.

After the historical universe, links, labels and controls have been independently
verified, prepare the documented development Parquet table and run:

```bash
uv run disclosure develop --dataset data/processed/development.parquet
```

The command rejects 2022 or later filing events. It produces development selections,
not a confirmatory result. There is no current claim of predictive performance.

## Project map

| Component | Purpose |
|---|---|
| `src/disclosure_research/edgar.py` | SEC API/archive access, hashes, caching, retries |
| `extraction.py`, `ingest.py` | Item 1A extraction, annual pairing and audit outputs |
| `audit.py` | Offline source checks, DuckDB coverage and fingerprinted review packets |
| `timing.py`, `market.py` | Session arithmetic, historical links and return labels |
| `market_data.py`, `labels.py` | Validated Parquet/DuckDB imports and audit-bound event-label staging |
| `crsp_staging.py` | CIZ CSV staging, original flags, units, dated SIC and explicit coverage gaps |
| `identity_review.py` | Source-bound SEC/CCM/Names evidence, dated candidate coverage and pending reviews |
| `controls.py`, `export_plan.py` | Prior-session controls and outcome-free pilot export requests |
| `features.py`, `modeling.py` | Training-only text measures and chronological baselines |
| `evaluation.py` | Paired score and contiguous-month uncertainty estimates |
| `protocol.py`, `configs/` | Frozen choices and integrity guards |
| `tests/` | Scientific/data failure cases and synthetic integration checks |
| `docs/`, `reports/` | Data contract, decisions, evidence and remaining gates |

## Research context and ownership

The idea is inspired by Cohen, Malloy and Nguyen's
[*Lazy Prices*](https://doi.org/10.1111/jofi.12885). Our annual Risk Factors and
20-session design is an extension. Sources and distinctions are in the protocol.

This milestone was co-developed with Codex. Code generation is not evidence that
the researcher has completed manual audits or independently reproduced a result.
The decision log records choices; human review and explanations remain part of
each research gate. The report will describe measured outcomes, including nulls.

## Next milestone

Review the initial 30-pair sample and all registered reference boundaries, including
the source-method transitions. Resolve the missing terminal row in the WFM export
and complete source metadata, then build and audit the historical universe, joins and pre-event
controls before running real development experiments.
Select and audit a semantic checkpoint before unlocking the primary final evaluation.
