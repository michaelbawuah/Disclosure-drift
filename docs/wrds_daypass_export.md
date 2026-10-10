# Manual WRDS day-pass exports

Use the account owner's WRDS website session and normal download forms for this
route. A one-day website pass does not establish access to the PyWRDS/PostgreSQL
connection used by `scripts/wrds_full_export.py`. The access link belongs in the
owner's browser, not in scripts, source control, query receipts, or public notes.

WRDS's [access rules](https://wrds-www.wharton.upenn.edu/users/tou/)
require manual website login and download-query submission. Its
[system policies](https://wrds-www.wharton.upenn.edu/pages/about/system-policies/)
allow **one web query at a time**. Finish each query before starting the next.
The official [web-query overview](https://wrds-www.wharton.upenn.edu/pages/about/3-ways-use-wrds/)
describes the browser-download route; no Python database login is needed for
that route.

The previous pilot demonstrated website exports of CRSP CIZ daily data, dated
Names, and CCM data; see [the observed source receipts](wrds_sample_exports.md).
The official daily URL is
[CRSP → Annual Update → Stock Version 2 → Daily Stock File](https://wrds-www.wharton.upenn.edu/pages/get-data/center-research-security-prices-crsp/annual-update/stock-version-2/daily-stock-file/).
Public retrieval reaches its sign-in page. The current pass's first daily export
contains all 13 fields listed below. Independent index access and a standalone
company-header form still require checking.
If a form lacks a required field or selection, record that gap rather than
substituting a different dataset.

## 1. Preserve each download and its query evidence

From the project directory on the Mac, create a new private directory:

```bash
mkdir -p data/raw/wrds-daypass/2026-10-10
```

Download CSV directly into this directory, or move the original downloaded file
there. Keep the original bytes; do not open and resave them through a spreadsheet.
If WRDS supplies a compressed file, keep it as well as the extracted CSV.

For every query, save the displayed submitted parameters, query/result number,
selected fields, date format, requested dates, security filter, displayed row
count, status, and download time with timezone. Save vendor SQL when the site
actually offers it. Preserve the displayed product/table and release/version
documentation. A screenshot or PDF of the query settings is useful evidence;
avoid including login credentials or the day-pass access URL. Record unavailable
SQL, source release, or timezone as unknown.

Use CSV with ISO `YYYY-MM-DD` dates and the highest available numeric precision
when the form supports those options. Preserve
leading-zero identifiers, blank values, literal `NA`, open-bound `E` markers,
missing-return flags, and blank terminal tickers. Do not drop records with an
unresolved flag or link type from the source export.

## 2. Start with one daily CSV, then continue in batches

Open **CRSP → Annual Update → Stock Version 2 → Daily Stock File**. Set the first
request to **2009-10-07 through 2009-12-31** and choose **all securities** rather
than a ticker list. Select the following twelve source fields, plus `vwretd` if
the form offers the benchmark field:

```text
PERMNO HdrCUSIP Ticker PERMCO DlyCalDt DlyDelFlg
DlyCap DlyRet DlyRetMissFlg DlyPrc DlyVol DlyPrcFlg
vwretd
```

If identifiers or date are automatically included by the form, leave them
included. Choose CSV, gzip compression, and ISO dates when available, submit the
query, and preserve its settings and downloaded file as described above. An
example first-file name is `crsp_daily_2009-10-07_2009-12-31.csv`; retain the
`.gz` suffix for compressed files. This combines daily returns and the raw
price/volume inputs needed for historical liquidity selection. Do not include
licensed data rows in chat; file headers, query status, and aggregate counts are
sufficient for initial troubleshooting.

If time is short, use these larger batches after the first export succeeds.
Keep the same fields and all-security selection, and finish **one query at a
time** before submitting the next:

| Batch | Start | End |
|---|---|---|
| First daily file | 2009-10-07 | 2009-12-31 |
| 2010–2012 | 2010-01-01 | 2012-12-31 |
| 2013–2015 | 2013-01-01 | 2015-12-31 |
| 2016–2018 | 2016-01-01 | 2018-12-31 |
| 2019–2021 | 2019-01-01 | 2021-12-31 |
| Development outcome tail only | 2022-01-01 | 2022-02-02 |

The first file downloaded on 2026-10-10 actually begins **2009-07-10** and
contains the required October–December interval. Preserve that original file;
there is no need to repeat the query just to remove the earlier rows. The offline
inventory reports actual coverage separately from the requested slice.

Annual files for **2010, 2011, …, 2021** remain a valid alternative and the
fallback if a larger download fails or exceeds the site's available result limit.
Split an affected year into shorter intervals if necessary, and preserve every
request. Check each result for completeness; a successful truncated query is not
full coverage.

The complete allowed source envelope is **2009-10-07 through 2022-02-02**. The
early-2022 tail supplies the fixed 20-session outcomes of late-2021 filings; it
does not authorize modeling 2022 filings.

The previous CIZ daily form provided attached `vwretd`. If it does not appear in
this pass, preserve the stock export and obtain the independent market file
below rather than filling or manufacturing that column. Do not append legacy
`DLRET` to `DlyRet`; return conventions require the delivered CIZ dictionary.
Leave missing or zero capitalization and original quality flags intact.

## 3. Collect the accompanying metadata and market file

The development population covers membership years **2010–2021**. Each query
must cover all source securities, including ones that later delisted, rather
than today's constituents, surviving firms, or a current ticker list. Historical
eligibility and the most liquid class per issuer are determined offline from
dated evidence. An export filtered to today's active records is insufficient.

### Dated Names

Request historical descriptions covering **2009-10-07 through 2022-02-02**. If
the form returns complete histories instead, preserve them and their metadata;
modern descriptions do not establish historical information availability.

The previously observed 24-field schema is:

```text
permno hdrprimaryexch nasdissuno hdrsiccd permco
secinfostartdt secinfoenddt securitybegdt securityenddt
cusip ticker issuernm shareclass usincflg issuertype
securitytype securitysubtype sharetype securityactiveflg
siccd primaryexch tradingsymbol naics tradingstatusflg
```

Preserve all fields. The dated `siccd` is needed for industry; `hdrsiccd` cannot
replace it. `usincflg` describes incorporation and does not by itself establish
that a security is listed in the United States. Classification meanings require
the actual product dictionary. If the UI filters intervals, preserve the exact
filter and verify that intervals beginning before the first requested date are
included when they overlap the requested coverage. If the form cannot express
interval overlap, request complete history instead of filtering only on interval
start dates.

### CCM link history and separate company-header meaning

Request all link types and retain unresolved rows. Required link fields are:

```text
gvkey LIID LINKPRIM LINKTYPE LPERMNO LPERMCO LINKDT LINKENDDT
```

Company-header fields required separately in meaning are:

```text
gvkey cik conm tic cusip
```

The observed website CCM export delivered these fields in one CSV. Keeping that
original combined CSV is valid source preservation; a later adapter can separate
the two roles without inventing a standalone export. A current company-header
CIK is not a historical CIK for every dated security link. Preserve `E` and blank
link bounds literally, and do not restrict the source to previously approved
link types. Exact source column casing should be retained.

### How the daily files supply pre-year liquidity

The combined daily exports above include these five population-source fields:

```text
PERMNO DlyCalDt DlyPrc DlyVol DlyPrcFlg
```

These windows are copied from the frozen
[year-start request](../reports/full_market_request/year_start_windows.csv).
Each contains exactly 60 XNYS sessions. The offline adapter must select these windows
from the full daily exports. There is no need to download them again when the
combined exports cover every interval and security. If collecting liquidity
separately becomes necessary, use one file per interval with the same all-security
selection and preserve each query's evidence.

| Membership year | Start | End |
|---|---|---|
| 2010 | 2009-10-07 | 2009-12-31 |
| 2011 | 2010-10-07 | 2010-12-31 |
| 2012 | 2011-10-06 | 2011-12-30 |
| 2013 | 2012-10-03 | 2012-12-31 |
| 2014 | 2013-10-07 | 2013-12-31 |
| 2015 | 2014-10-07 | 2014-12-31 |
| 2016 | 2015-10-07 | 2015-12-31 |
| 2017 | 2016-10-06 | 2016-12-30 |
| 2018 | 2017-10-05 | 2017-12-29 |
| 2019 | 2018-10-04 | 2018-12-31 |
| 2020 | 2019-10-07 | 2019-12-31 |
| 2021 | 2020-10-07 | 2020-12-31 |

For a separate export use names such as `crsp_liquidity_membership_2010.csv`.
This source export does not select the top 500 issuers; it provides inputs to historical
selection. Price conventions, volume units and historical availability still
require review before calculating dollar volume.

### Independent market returns

On the **Annual Update** page, find **Stock – Version 2 (CIZ)** and click
**Daily Stock Market Indexes**, shown at the top right beside **Daily Stock File**.

The observed form offers these two fields directly:

| Field | Displayed meaning |
|---|---|
| `dlycaldt` | Daily Calendar Date |
| `vwretd` | Value-weighted return including dividends |

Check that the selected return is **`vwretd` — including dividends**.
**`vwretx` excludes dividends** and cannot serve as the study's benchmark, even
when its date coverage is correct.

Set dates to **2009-10-07 through 2022-02-02**, select those two fields, and leave
conditional filters inactive. Choose **CSV**, **gzip**, and ISO **`YYYY-MM-DD`**
dates, then submit and preserve the download and query evidence. No index-ID
selector was visible on this form; no separate `IndNo` selection or output is
required for this route.

The earlier CRSP mapping associates `VWRETD` with CIZ **`IndNo = 1000200`** and
**`DlyTotRet`**. Those names describe an alternate CIZ representation, not extra
fields to select on the observed `dlycaldt`/`vwretd` form. Preserve the actual
delivered headers, documented benchmark, and source table. This independent
market file is needed because a benchmark repeated only on existing stock rows
cannot prove coverage after a stock's terminal event.

## 4. Offline intake and current implementation limits

Keep licensed CSVs and event-level outputs on the owner's Mac under ignored
`data/` or `outputs/`. Public repository changes can include code, empty templates
and source-free aggregate verification, without uploading the licensed rows.

### Inventory each daily download locally

From the project directory, run the following command, replacing `--source` with
the actual downloaded filename. Both plain CSV and gzip-compressed CSV are
accepted; extraction is unnecessary. Set the requested dates for that batch and
choose a new output directory for every run:

```bash
uv run --locked --python 3.12 python scripts/wrds_manual_inventory.py \
  manualdaily inventory \
  --source data/raw/wrds-daypass/2026-10-10/crsp_daily_2009-10-07_2009-12-31.csv \
  --request-start 2009-10-07 \
  --request-end 2009-12-31 \
  --output data/private/wrds-intake/2009-v1
```

The command requires exactly the 13 daily fields above, with case-insensitive
header matching. It makes a read-only, byte-preserving copy as `source.csv` or
`source.csv.gz` and writes an aggregate `receipt.json` beside it. It records the
source SHA-256, headers, row and security counts, actual and requested date
coverage, missing XNYS sessions, exact repeated rows, conflicting security/date
records, blank/numeric classifications, and uninterpreted flag counts. It uses
disk-backed processing for large files and checks every date against the
development boundary before interpreting numeric values.

No rows are removed, filled, or normalized, including extra early rows. A new
output directory is required, so existing evidence is not overwritten. Source
release, vendor query details, download timestamps, and verified all-security
selection remain unknown until supported by separately preserved evidence.
The receipt explicitly records `model_ready: false`; date coverage alone does
not establish complete security coverage or resolve conflicting records.

### Inventory Names and CCM downloads locally

Use the separate metadata command for Names and the combined CCM/company file.
Replace each example source path with the downloaded CSV or gzip file, and use a
new private output directory for each run:

```bash
uv run --locked --python 3.12 python scripts/wrds_manual_metadata.py \
  inventory --role names \
  --source PATH_TO_NAMES.csv.gz \
  --request-start 2009-10-07 --request-end 2022-02-02 \
  --output data/private/wrds-intake/names-v2

uv run --locked --python 3.12 python scripts/wrds_manual_metadata.py \
  inventory --role ccm \
  --source PATH_TO_CCM.csv.gz \
  --request-start 2009-10-07 --request-end 2022-02-02 \
  --output data/private/wrds-intake/ccm-v2
```

Names requires the 24 fields above; CCM requires the combined 12 link/company
fields and preserves any extra delivered columns. Each inventory saves a
read-only, byte-preserving source copy and aggregate `receipt.json`, including
hashes, headers, row counts, exact duplicates, historical-key variants, date-bound
classifications, definite requested overlap, and unresolved interval-overlap
candidates. Metadata histories outside the requested dates, including bounds
after 2022, remain preserved raw. They do not authorize final-period outcomes or
establish historical information availability. Blank, `B`, `E`, and other
nonfinite bounds remain unresolved; no rows are dropped or normalized.

If the site actually supplied a SQL file, append `--sql PATH_TO_QUERY.sql`.
The command preserves it and performs a restricted text check; it never executes
SQL or verifies vendor execution. SQL is optional: the observed CCM results page
offered compressed output without SQL. Preserve screenshots and displayed input
parameters separately as query evidence; do not create substitute vendor SQL.
Missing SQL, source release and vendor timestamps remain unknown. Both metadata
receipts retain `model_ready: false` and zero source approvals.

### Inventory the independent market download locally

The market command accepts exactly `dlycaldt` and `vwretd`, with case-insensitive
header matching, in CSV or gzip form. Replace the source path and choose a new
private output directory:

```bash
uv run --locked --python 3.12 python scripts/wrds_manual_market.py \
  inventory \
  --source PATH_TO_MARKET.csv.gz \
  --request-start 2009-10-07 --request-end 2022-02-02 \
  --output data/private/wrds-intake/market-v1
```

The command preserves a read-only copy of the original bytes and records its
byte count, SHA-256 and headers in `receipt.json`. A complete date pass blocks
source observations after **2022-02-02** before any return is interpreted as a
number. The inventory reports actual/requested coverage, expected and missing
XNYS sessions, non-session dates, exact duplicates, and dates with different
return text. Numeric counts distinguish blank, malformed, nonfinite and finite
values, with a separate count below minus one. Text differences remain distinct
and unresolved; the inventory does not choose between conflicting records.

Append `--sql PATH_TO_QUERY.sql` only when a SQL file was supplied. Unlike the
metadata command's restricted SQL check, this command only preserves and hashes
that attachment; it neither interprets nor executes it. All source rows,
including extra early dates, remain unchanged. Independent-export provenance,
vendor execution, release/vintage, completeness and return conventions remain
unverified; the receipt records `model_ready: false` and zero source approvals.

### Remaining staging work

The offline `stage-crsp` command already consumes the ten-field stock contract
(`PERMNO`, `HdrCUSIP`, `Ticker`, `PERMCO`, `DlyCalDt`, `DlyDelFlg`, `DlyCap`,
`DlyRet`, `DlyRetMissFlg`, and `vwretd`), allowing additional CSV columns, and a
Names CSV with at least `permno`, `permco`, `secinfostartdt`, `secinfoenddt`, and
`siccd`. See [the staging guide](crsp_staging.md). It hashes the original bytes,
checks development dates before interpreting returns, validates unique daily
keys and dated Names matches, and keeps research approval gates unresolved.

These are the minimum adaptations needed after the manual source schema is
confirmed:

| Component | Current behavior | Required adaptation for full manual exports |
|---|---|---|
| Manual source inventory | Offline daily, Names, combined CCM/company and independent-market CSV/gzip inventories preserve bytes and report aggregate checks | Add supported query/release evidence and reconcile completeness across all batches and source families |
| Full-population daily staging | Reads the entire CSV into memory; accepts only known `NA` return flags | Stream/partition large files and review dictionary-defined missing codes, with explicit exclusions or unresolved records rather than zero filling |
| Independent benchmark | Raw two-field market inventory is implemented; existing staging still derives `vwretd` from stock rows | Verify market-source meaning, normalize its documented fields and reconcile overlapping values without deleting post-terminal benchmark sessions |
| Historical universe | Requires normalized Parquet inputs | Map dated Names classifications, liquidity conventions and reviewed historical CIK links explicitly; preserve raw headers and source bounds |

The online exporter's `verify` and `assemble` commands require its own
query-bound export plans and receipts. They are **not** validators for arbitrary
web-downloaded CSVs. Do not fabricate their receipts to make manual files pass.
An intake inventory or successful staging run is not a historical-identity audit,
an availability review, a complete population, or a model-ready dataset.

## Final-period boundary

Do not request the 2022–2025 population windows or the final-period return bundle
through this route yet. The existing development prerequisite verifier governs
those separate exports, including later population price/volume observations
that could reveal final outcomes. The frozen protocol and recorded user 20/20
arithmetic review remain unchanged; this guide does not ask for that review again.
