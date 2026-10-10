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
Public retrieval reaches its sign-in page. The current pass's available fields, independent
index access, and a standalone company-header form still require checking.
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

## 2. Start with one daily CSV, then continue by year

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
included. Choose CSV and ISO dates when available, submit the query, and preserve
its settings and downloaded file as described above. Name the first file
`crsp_daily_2009-10-07_2009-12-31.csv`. This combines daily returns and the raw
price/volume inputs needed for historical liquidity selection. Do not include
licensed data rows in chat; file headers, query status, and aggregate counts are
sufficient for initial troubleshooting.

After the first export succeeds, repeat for **2010, 2011, …, 2021**, one full
calendar year per file, and one final interval **2022-01-01 through 2022-02-02**.
The complete allowed source envelope is **2009-10-07 through 2022-02-02**. The
early-2022 tail supplies the fixed 20-session outcomes of late-2021 filings; it
does not authorize modeling 2022 filings. If the site imposes a smaller result
limit, split the affected year by month and preserve every request. A successful
truncated query is not full coverage.

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

Also obtain an **independent value-weighted daily total-market return** export
for the same date envelope, with `DlyCalDt`/`dlycaldt` and `vwretd` as the source
fields when actually offered. Save the exact delivered header, documented
benchmark, and source table. A market return repeated only on existing stock
rows cannot prove benchmark coverage after a stock's terminal event.

## 4. Offline intake and current implementation limits

Keep licensed CSVs and event-level outputs on the owner's Mac under ignored
`data/` or `outputs/`. Public repository changes can include code, empty templates
and source-free aggregate verification, without uploading the licensed rows.

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
| Manual source inventory | No day-pass bundle import command | Inventory files, headers, hashes, query evidence, ranges, row counts and part completeness; report unknown provenance explicitly |
| Full-population daily staging | Reads the entire CSV into memory; accepts only known `NA` return flags | Stream/partition large files and review dictionary-defined missing codes, with explicit exclusions or unresolved records rather than zero filling |
| Independent benchmark | Existing staging derives `vwretd` from stock rows | Accept a separate verified market CSV and reconcile overlapping benchmark values without deleting post-terminal benchmark sessions |
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
