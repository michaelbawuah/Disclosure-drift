# Run the full-study WRDS source export

**Choose the access route first.** The commands below require an authenticated
WRDS database connection. A website Access Pass/Daypass is a separate route:
follow the [manual browser-export guide](wrds_daypass_export.md) instead of
retrying a Python username/password prompt. WRDS requires website login and
download queries to be submitted manually; this exporter connects to the
database and does not automate the website. See the
[official access rules](https://wrds-www.wharton.upenn.edu/users/tou/).

The exporter collects the missing historical source inputs into private,
resumable CSV checkpoints. **The default export covers development population
selection years 2010–2021.** Final population price/volume windows and final
returns each require completed development prerequisites and separate directories.
The helper does not create credentials, approve source availability, normalize
historical CIKs, or mark a research dataset ready.

The implemented files are [the exporter](../src/disclosure_research/wrds_export.py),
[the local command](../scripts/wrds_full_export.py), and the
[source-binding template](../configs/wrds_sources.template.json). Existing
[historical dataset](historical_dataset.md) and
[market-data](market_data_contract.md) contracts remain unchanged.

## One initial execution path

Run these commands from the repository root on your own computer, with Python
3.12, `uv`, and your institution's WRDS access. PyWRDS handles any username,
password and authentication prompts in that terminal. Do not put credentials in
the binding file, command arguments, receipts, or chat. The project does not
inspect your credential files.

### 1. Check the actual source catalog

```bash
uv run --locked --python 3.12 --with wrds==3.5.0 python scripts/wrds_full_export.py \
  catalog --output data/private/wrds-catalog.json
```

This lists candidate tables and their observed columns, without querying source
rows. It reports unavailable requested libraries. The template namespaces are
**candidates**, not a claim that your account can read those tables. An existing
WRDS web-form session does not by itself prove PostgreSQL access.

Copy the binding template after the catalog command creates `data/private/`:

```bash
cp configs/wrds_sources.template.json data/private/wrds_sources.json
```

Check its five `library`/`table` pairs against `wrds-catalog.json`. If your account
uses another namespace, replace the corresponding pair with the cataloged table
whose `missing_required_columns` is empty. Catalog additional known libraries
with `--libraries LIBRARY1 LIBRARY2` and a new output filename when necessary.
The exporter accepts exact source-field names, allowing case differences; it
does not silently replace a missing CIZ field with a legacy variable.

Leave `source_release` and `release_evidence` null until you have vendor evidence
for them. A modern download date is not a historical availability date. Recording
release text is a declaration for review, not approval.

### 2. Download the development population inputs

```bash
uv run --locked --python 3.12 --with wrds==3.5.0 python scripts/wrds_full_export.py \
  export --bindings data/private/wrds_sources.json \
  --output data/raw/wrds-full/population-development-v1
```

This default request collects:

- Dated Names records intersecting the development source envelope.
- All CCM link-history rows, including unresolved link types, null permanent IDs,
  and open-bound markers; these remain identity candidates.
- Compustat company-header CIK/name/ticker/CUSIP metadata in a separate file.
- Exactly the 60 XNYS sessions preceding each year start for 2010–2021, split
  into calendar-month queries. The first requested session is **2009-10-07**;
  the final selection window ends **2020-12-31**.

Queries cover all source securities. They contain no current-constituent,
current-ticker, survival, or approved-link-type filter. Population daily queries
project only `PERMNO`, `DlyCalDt`, `DlyPrc`, `DlyVol`, and `DlyPrcFlg`. They do
not retrieve stock returns, capitalization, benchmark returns, or terminal flags.
Later delisting does not remove a security from a historical selection window.

### 3. Download development market inputs

```bash
uv run --locked --python 3.12 --with wrds==3.5.0 python scripts/wrds_full_export.py \
  export --partition development --bindings data/private/wrds_sources.json \
  --output data/raw/wrds-full/development-v1
```

The conservative source envelope runs from **2009-10-07 through 2022-02-02**.
The early-2022 tail is explicitly allowed for late-2021 development filing
labels; this command cannot extend it. Stock queries preserve the ten observed
staging fields:

`PERMNO`, `HdrCUSIP`, `Ticker`, `PERMCO`, `DlyCalDt`, `DlyDelFlg`, `DlyCap`,
`DlyRet`, `DlyRetMissFlg`, and `vwretd`.

The benchmark enters each stock CSV through a left join, so a missing benchmark
cannot silently drop a stock row. Independent index queries also export every
requested benchmark session, including sessions after an individual security's
last stock observation. A missing or duplicate benchmark session stops completion.
No return is recalculated, filled with zero, or combined with a legacy `DLRET`.
A blank terminal ticker is retained. Literal `NA` return flags and missing
capitalization remain distinguishable.

This broad source export can be large. Queries run one month at a time and save
each successful part immediately. The exporter does not need the full export in
memory, although the existing pilot-only staging command is not a streaming
full-population normalizer.

### 4. Verify and assemble local CSVs

These commands work offline and do not require PyWRDS:

```bash
uv run --locked python scripts/wrds_full_export.py verify \
  --bundle data/raw/wrds-full/population-development-v1
uv run --locked python scripts/wrds_full_export.py assemble \
  --bundle data/raw/wrds-full/population-development-v1 \
  --output data/staging/wrds-full/population-source-csv
uv run --locked python scripts/wrds_full_export.py verify --partition development \
  --bundle data/raw/wrds-full/development-v1
uv run --locked python scripts/wrds_full_export.py assemble --partition development \
  --bundle data/raw/wrds-full/development-v1 \
  --output data/staging/wrds-full/development-source-csv
```

Assembly verifies each input receipt and hashes the same source bytes it copies.
It concatenates monthly CSVs with one header, preserving source strings and date
order. Development `crsp_daily.csv` and `crsp_names.csv` use the existing
`stage-crsp` source column contract. `crsp_market.csv` remains separate. Population
outputs are `crsp_names.csv`, `crsp_ccm_link_history.csv`,
`compustat_company_headers.csv`, and `crsp_liquidity.csv`.

Build the development universe from a reviewed normalized manifest containing
only membership years 2010–2021. That is sufficient to ingest development SEC
filings and build the development dataset; no holdout population is needed to
finish the development prerequisites.

## Resume and receipts

If a download is interrupted, repeat the identical export command with `--resume`.
Completed parts are checked before any missing value query runs. A changed source
file, query, receipt, binding, protocol, code version, or catalog causes refusal.
Use a new output directory for a changed request. Existing output is never
silently overwritten.

The private export directory contains:

| Artifact | Purpose |
|---|---|
| `export_plan.json` | Protocol/code/binding fingerprints, observed source columns, exact SQL, parameters, windows and job inventory |
| `source_bindings.json` | Exact source tables and declared release evidence |
| `parts/JOB/data.csv` | Projected source rows for that query |
| `parts/JOB/query.sql` and `parameters.json` | Executed query and bounded parameters |
| `parts/JOB/receipt.json` | UTC export timestamp, row count, date coverage, source table, file hashes and request identity |
| `checkpoint.json` | Completed parts, hashes, progress, data access indicators and outstanding audits |

`source_export_complete` means every requested query completed with its required
columns and aggregate session coverage. It does not certify vendor population
completeness, individual security coverage, historical data vintages, or source
review. All receipts remain `WRDS_RAW_SOURCE_EXPORT_NOT_AUDIT_APPROVED`,
`model_ready: false`, with zero human reviews completed by the exporter. A resume
cannot prove that an unversioned vendor database stayed unchanged between query
times; preserve the per-part timestamps and obtain release evidence before audit.

Licensed exports inside this repository are allowed only under ignored `data/`
or `outputs/`. Code, templates and source-free documentation may be committed;
raw CSVs and event-level market data must remain private.

## Final population and final market data

Price/volume observations from the windows selecting the 2023–2025 population
could indirectly expose 2022–2024 price changes. Therefore **even holdout
population price/volume collection is gated**. It has no ungated execution mode.

After the actual development source audits, model selection and secondary
specification pass the existing prerequisite verifier, use the completed
[prerequisite request](../configs/examples/development_prerequisites.json):

```bash
uv run --locked --python 3.12 --with wrds==3.5.0 python scripts/wrds_full_export.py \
  export --partition holdout_population --bindings data/private/wrds_sources.json \
  --prerequisites-request data/private/development_prerequisites.json \
  --output data/raw/wrds-full/population-holdout-v1
uv run --locked --python 3.12 --with wrds==3.5.0 python scripts/wrds_full_export.py \
  export --partition holdout --bindings data/private/wrds_sources.json \
  --prerequisites-request data/private/development_prerequisites.json \
  --output data/raw/wrds-full/holdout-v1
```

The first command collects exactly the 2022–2025 year-start liquidity windows,
starting **2021-10-07**, and separate metadata for a holdout universe bundle. The
second collects holdout control/return sources from **2021-10-07 through
2026-02-03**. Their outputs are physically separate from development. Verification,
assembly and resumption of either partition also require fresh prerequisites.
The command checks prerequisites before connecting or prompting for WRDS
credentials and before opening saved holdout files. It does not accept a bare
approval flag or a saved `model_ready: true` value as authorization.

The complete 16-year population plan remains available offline, without querying
any values or connecting to WRDS:

```bash
uv run --locked python scripts/wrds_full_export.py plan --partition full_population \
  --output outputs/wrds-full-population-plan.json
```

`full_population` is plan-only; the execution command deliberately has no such
partition. Keep the main [full-study data request](full_study_data_request.md) as
the scientific specification.

## What normalization still must establish

| Normalized input | Exported source evidence | Review still required |
|---|---|---|
| Historical listings | Dated Names classifications and trading fields | U.S. listing/common-stock/active mapping, historical information availability and full-population coverage |
| `daily_liquidity` | Exact pre-year `DlyPrc`/`DlyVol`/price-flag observations | USD/volume units, price conventions and historical `available_at`; export time cannot fill that field |
| `identity_links` | CCM link history, dated Names and separate company headers | Original SEC CIK, selected share class, historical identity, finite effective bounds and `known_at` evidence |
| Returns and benchmark | `DlyRet`, source flags and independent `vwretd` | Release/version, missing-return rules, dividends and delisting treatment, terminal coverage |
| Size and industry | `DlyCap` and dated Names `siccd` | Documented units, exact-date historical match and source availability |

A modern company-header CIK is not silently assigned throughout a GVKEY/PERMNO
link interval. The recovered Exxon example already demonstrates why that would
be unsafe. `E` and null link bounds stay unresolved source values. Historical
`known_at` and `available_at` must come from documented evidence, not invented
timestamps. The strict normalized builder remains responsible for rejecting
unsupported or ambiguous records.

## Interface and source references

Verified against official documentation on 10 October 2026:

- [Wharton's PyWRDS source](https://github.com/wharton/wrds/blob/main/wrds/sql.py)
  documents `list_libraries`, `list_tables`, `describe_table`, and parameterized
  `raw_sql`, including `coerce_float=False`. The command pins the
  [WRDS-maintained 3.5.0 package](https://pypi.org/project/wrds/3.5.0/).
- [WRDS's CIZ event-study implementation](https://wrds-www.wharton.upenn.edu/pages/wrds-research/macros/run-an-event-study-ciz-format-macro/)
  uses `dlycaldt`, `DlyRet`, and independent `wrds_dailyindexret_query` benchmark
  fields; it describes delisting return as incorporated in CIZ returns.
- [WRDS's CCM example](https://wrds-www.wharton.upenn.edu/pages/wrds-research/macros/wrds-macro-ccm/)
  documents `ccmxpf_lnkhist` and dated GVKEY/PERMNO links. This exporter preserves
  all source link types for review rather than adopting the example's sample
  filtering choices.
- The user's unchanged [Names SQL](source_queries/crsp_names_pilot.sql), SHA-256
  `556924430cf54c6eb3b7a8ebe0654b3323c659af3659cbc623017fc4d7498efa`, establishes
  the observed `crsp_a_stock.wrds_names_query` selection and 24 source columns.
  Its [query receipt](../reports/review_progress/names_query_receipt.json) records
  what was actually checked. Runtime catalog validation is still required.

No WRDS account was accessed or full-study vendor rows downloaded while building
this helper. Tests execute the emitted SQL against invented DuckDB tables and
exercise missing sessions, terminal rows, exact string preservation, metadata
mismatches, interruption/resume, mutated receipts, and blocked holdout access.
