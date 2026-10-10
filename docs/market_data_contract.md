# Normalized market-data contract

Store restricted source data under `data/`, which is excluded from git. Keep an
export manifest with dataset/version, source field names, timestamps and hashes.
This document is a target schema; it is not a claim that the WRDS export has already
been obtained or mapped.

The executable [import and label-staging workflow](market_import.md) implements the
first three tables below. `configs/market_manifest.template.json` records the
required provenance. A standalone pre-event control calculator and
[dated pilot export request](pilot_market_request.md) are available. The historical
universe and full prepared dataset remain pending. The
[CIZ CSV staging adapter](crsp_staging.md) now converts the observed daily/Names
schemas to returns, benchmark and dated snapshots, with source and human audits
still unresolved. Staging is not an approved import bundle.
The [pilot arithmetic audit](pilot_arithmetic_review.md) now combines staged returns
and snapshots with source-bound candidate identity evidence. Its private results
have an explicit provisional-QA data kind and omit the text/model input schema.
They do not replace the approved historical links required below.

## Returns and benchmark

`daily_returns.parquet` has `security_id`, `session` (ISO exchange date),
`total_return` (decimal), and `terminal_event` (boolean). Every value must be finite,
returns cannot be below -1, and `(security_id, session)` must be unique. Total
returns include dividends and any applicable delisting payoff exactly once. Keep
original missing/flag codes in the source layer; do not convert them to zero.

`market_returns.parquet` has one `session` and `total_return` per market session,
from a declared value-weighted total-return benchmark. No forward filling.

`market.make_label` accepts one security and the benchmark. It excludes the
reference day's return, compounds exactly the following 20 session returns, and
subtracts benchmark compounded return. A terminal event must include a defensible
payoff. Remaining proceeds earn zero return for the rest of this research horizon.
An unavailable payoff remains a data-quality issue; do not manufacture one.

`combine_legacy_return` is only for verified legacy separate ordinary/delisting
fields: `(1 + ordinary_return) * (1 + delisting_return) - 1`. It must not be applied
to a field already containing both. Normalize modern CRSP flags and dates with
the source's current dictionary before invoking the label engine.

## Historical identity and universe

`security_links.parquet`: `cik` (zero-padded string), `security_id`, `valid_from`,
`valid_to`, mapping source and class-selection rule. Date ranges are inclusive.
Normalize open-ended validity to a documented extract-end date. Zero or multiple
eligible IDs for an event require review; never select the first arbitrarily.

`universe.parquet`: `year`, `cik`, `security_id`, prior-window dollar volume,
valid-session count and selection rank. Build it from historical U.S. common-stock
listings as of each year-start. The actual full-universe selector is a later
milestone, after the input data dictionary is verified.

## Prepared development table

The `disclosure develop` command accepts one Parquet table with these columns:

| Column | Meaning |
|---|---|
| `observation_id` | Unique accession/security event identity |
| `acceptance_date` | SEC acceptance date interpreted in New York time |
| `reference_session` | Second exchange session strictly after acceptance date |
| `label_end` | Reference session plus 20 trading sessions |
| `controls_asof` | Preceding session close's date |
| `previous_text`, `current_text` | Audited, nonempty annual Item 1A sections |
| `target` | Unranked 20-session stock return minus benchmark return |
| `momentum_20`, `momentum_60` | Compounded prior total returns ending at controls_asof |
| `volatility_20` | Sample standard deviation of prior 20 daily total returns |
| `log_market_cap` | Natural log of positive historical market cap in USD |
| `industry` | Historical industry category known at prediction time |

All rows must have fully audited linkage, timing and labels; carry source identifiers
in the upstream tables. Resolve missing-data/exclusion rules before modeling. The
current runner rejects missing required values and rejects any filing year beyond
2021. It fits text vocabulary and all learned preprocessing only in training folds.

Fetch source history before 2010 as needed for initial liquidity windows and prior
annual filings. At the current development-only stage, request returns only through
development-event label ends (which can include an early-2022 tail). After the final
gate is explicitly unlocked, 2025 events may require an early-2026 tail. The
runner's ordering checks support the audit; they cannot prove that a vendor's
historical values are point-in-time without source-level evidence.
