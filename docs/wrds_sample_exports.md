# WRDS sample exports inspected on 9 October 2026

The owner downloaded these files through Cornell's authenticated WRDS session.
The [receipt](../reports/market_access_samples.json) records exact byte hashes,
row counts and actual column names. The same hashes were checked in the owner's
Mac Downloads folder. Licensed rows remain outside public git.

| File | Observed result | Scope |
|---|---|---|
| `crsp_access_check.csv` | 5 rows, 6 columns | AAPL daily stock returns, 4-8 January 2021 |
| `crsp_access_expanded.csv` | 5 rows, 10 columns | Same observations, plus capitalization, return/delisting flags and benchmark |
| `crsp_names_apple.csv` | 11 rows, 24 columns | Historical security descriptions for the sample security |
| `crsp_names_apple.sql` | Vendor SQL supplied | Source view `crsp_a_stock.wrds_names_query` |
| `crsp_ccm_pilot.csv` | 60 rows, 47 columns | 19 of the 20 requested pilot CIKs |
| `crsp_ccm_xom.csv` | 2 rows, 47 columns | XOM ticker supplement; header CIK differs from pilot filings |

## What was checked

The two daily files have identical shared fields, five expected sessions and no
duplicate security/session keys. Observed returns are finite and no lower than
minus one; capitalization is positive. Preserve literal `NA` in `DlyRetMissFlg`
as a source code, rather than letting generic CSV null inference erase it.
The sample contains only `N` delisting flags, so it does not test a delisting payoff.

The Names CSV matches its SQL selection. Its intervals are contiguous and
nonoverlapping, and every sample daily observation matches exactly one interval.
The historical SIC for the sample dates differs from the header SIC, demonstrating
why historical industry controls need a dated join. The Names output has no CIK.
This is interval coverage evidence, not proof of contemporaneous data vintages.

The combined CCM files have the same schema, 62 rows, no duplicate link keys and
no reversed explicit date intervals. Of these, 33 rows have blank permanent security
IDs and source link types `NR` or `NU`; retain them in raw evidence. End-date `E`
markers are retained literally. Source normalization is not yet implemented.

The batch result is WRDS query **11768919**, product **crsp_a_ccm**, marked Success,
60 rows and 29 KiB on the supplied results screenshot. The displayed submission
time is `2026-10-09 22:12`; its timezone is not asserted. The page offered CSV only.
The actual submitted parameter expansion and a vendor SQL file were not supplied.
The pre-submission form showed all eight link types and all 51 variables selected;
both delivered CCM files contain 47 columns. All nine core identity/link fields
are present. Do not invent missing vendor SQL or silently call this a 51-column file.
The XOM supplement's query number and full submitted parameters were not supplied.

## Identity issue still open

The original pilot contains Exxon Mobil filing CIK `0000034088`. The XOM supplement
instead carries header CIK `0002115436`, company name EXXONMOBIL HOLDINGS CORP and
candidate PERMNO `11850`. This is evidence of a header-identity mismatch, not enough
to authorize assigning that header CIK throughout the historical link interval.
The reason for the changed header has not been established from primary filings.

Nineteen requested CIKs match the batch file directly. Adding the XOM supplement
provides 20 candidate securities for the next retrieval. It does **not** establish
20 audited historical CIK-to-security mappings. Preserve the historical SEC filing
CIKs and original raw headers separately. In particular, CCM dates describe the
GVKEY/security link; the WRDS form says the accompanying identifiers are header data.
No predecessor filing splicing, historical CIK substitution or outcome-based
security selection has been approved.

## Next data request

Use **CRSP / Annual Update / Stock - Version 2 (CIZ) / Names** for the 20 candidate
PERMNOs prepared from these private files. Select all 24 variables, CSV,
uncompressed and ISO dates; save as `crsp_names_pilot.csv`, plus SQL if offered.
Reconcile dated names, security types and identifiers against original SEC filings
before admitting a link to label staging. Names alone cannot certify a CIK history.

Then obtain daily stock/benchmark observations for the pilot request envelope
**2014-11-04 through 2021-12-28**, with the exact required fields and dictionaries.
The [135 event windows](../reports/pilot_market_request/event_windows.csv) define
the precise control and label sessions. Separately complete the development-period
delisting example, identifier-change review and all pending human audits.

Only a five-session actual-return sample has been inspected so far. No actual
filing-event labels or prediction models have been generated. No final-period
2022-2025 returns or evaluation outcomes have been examined; identifier metadata
outside development dates was read solely to inspect the delivered schemas/history.
The protocol and final evaluation gate are unchanged.
