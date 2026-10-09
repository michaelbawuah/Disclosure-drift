# Disclosure changes and return forecasting

Do year-over-year changes in annual risk disclosures improve 20-session return
forecasts for historically selected large, liquid U.S. stocks?

This repository implements the research pipeline and its audit trail. The primary
protocol is frozen in [protocol.md](protocol.md) and
[configs/protocol.json](configs/protocol.json). Initial training is 2010-2015,
development is 2016-2021, and the final evaluation period is 2022-2025.

**Current milestone:** SEC ingestion, Item 1A extraction and pairing, exchange-session
timing, train-only text features, normalized-return label calculations, ridge
development comparisons, and paired month-block confidence intervals. Real return
data and the final empirical evaluation remain pending. The demo is entirely synthetic.

## Run locally

Install [uv](https://docs.astral.sh/uv/), then run from this directory:

```bash
uv sync --locked
uv run pytest
uv run disclosure status
uv run disclosure demo
```

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
| `timing.py`, `market.py` | Session arithmetic, historical links and return labels |
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

Complete the five-company manual boundary/timing audit, verify market-data access,
then expand the parser pilot to 100-150 development-year filing pairs. Select and
audit a semantic checkpoint before unlocking the primary final evaluation.
