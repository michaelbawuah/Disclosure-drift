# WRDS sample and pilot exports inspected on 9-10 October 2026

The owner downloaded these files through Cornell's authenticated WRDS session.
The [receipt](../reports/market_access_samples.json) records exact byte hashes,
row counts and actual column names. Matching downloads were checked where available;
all nine supplied files are archived with verified hashes in the owner's ignored
local data directory. The pilot Names CSV was archived from the supplied attachment.
Licensed rows remain outside public git.

| File | Observed result | Scope |
|---|---|---|
| `crsp_access_check.csv` | 5 rows, 6 columns | AAPL daily stock returns, 4-8 January 2021 |
| `crsp_access_expanded.csv` | 5 rows, 10 columns | Same observations, plus capitalization, return/delisting flags and benchmark |
| `crsp_names_apple.csv` | 11 rows, 24 columns | Historical security descriptions for the sample security |
| `crsp_names_apple.sql` | Vendor SQL supplied | Source view `crsp_a_stock.wrds_names_query` |
| `crsp_ccm_pilot.csv` | 60 rows, 47 columns | 19 of the 20 requested pilot CIKs |
| `crsp_ccm_xom.csv` | 2 rows, 47 columns | XOM ticker supplement; header CIK differs from pilot filings |
| `crsp_names_pilot.csv` | 237 rows, 24 columns | Dated security descriptions for all 20 candidate PERMNOs |
| `crsp_names_pilot.sql` | Vendor SQL supplied | Confirms the 20 requested PERMNOs and all 24 selected columns |
| `crsp_daily_pilot.csv` | 36,000 rows, 10 columns | 1,800 sessions per security for all 20 candidates, 4 November 2014 to 28 December 2021 |

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

The full pilot Names CSV has exactly the 20 PERMNOs requested, and its 24 columns
match the SQL selection in order. All 237 date intervals are valid, with no gaps,
overlaps or duplicate PERMNO/start-date keys. Its Apple rows match the earlier
sample exactly. The control-history start, controls date, entry-reference date and
label end each match exactly one record for every candidate event: **540 of 540**
boundary checks pass. Continuous interval coverage makes the intervening dates
covered too. These checks use provisional retrieval associations, not approved
CIK mappings. Historical SIC differs from header SIC at **76 of 135** controls
dates. Preserve dated SIC for normalization; do not substitute header SIC.

The full daily export has unique security/session keys and exactly the 1,800 XNYS
sessions in the requested envelope for every candidate: no missing or extra dates.
All stock and benchmark returns are numeric, finite and at least minus one; every
capitalization is positive. All 36,000 return-quality flags are the literal source
code `NA`, and every delisting flag is `N`. The benchmark agrees across securities
on all 1,800 dates. The five-row expanded Apple sample matches the full export
exactly. All daily observations join exactly one dated Names record with the same
PERMCO. These are source consistency checks, not independent vendor verification.

Using the provisional retrieval associations, all 135 event windows have their
60 control sessions, entry-reference row and 20 return sessions: 8,100 control-row,
135 entry-row and 2,700 label-row checks pass. No compounded event labels or fitted
models were created. The daily query ID, vendor SQL and exact source release date
have not been supplied; they are recorded as unknown rather than inferred.

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

The pilot Names export now shows the original Exxon Mobil name and historical
CUSIP throughout our development windows under the candidate PERMNO. This supports
the candidate security and provides dated industry records. It does not add a CIK
field or certify the full CIK/security history. The original SEC filing CIK remains
unchanged and independent historical identity review is still pending.

Nineteen requested CIKs match the batch file directly. Adding the XOM supplement
provides 20 candidate securities for the next retrieval. It does **not** establish
20 audited historical CIK-to-security mappings. Preserve the historical SEC filing
CIKs and original raw headers separately. In particular, CCM dates describe the
GVKEY/security link; the WRDS form says the accompanying identifiers are header data.
No predecessor filing splicing, historical CIK substitution or outcome-based
security selection has been approved.

## Next data request

The pilot daily and Names exports are received. The remaining small export is a
[Whole Foods delisting QA case](wrds_delisting_check.md) in August 2017. The pilot
contains no delisting rows and cannot validate terminal-payoff handling by itself.
Reconcile the dated Names records against original SEC filings before label staging,
and finish the source-release, identifier-change and independent human reviews.

The [135 event windows](../reports/pilot_market_request/event_windows.csv) define
the precise control and label sessions. No actual filing-event labels or prediction
models have been generated. No final-period
2022-2025 returns or evaluation outcomes have been examined; identifier metadata
outside development dates was read solely to inspect the delivered schemas/history.
The protocol and final evaluation gate are unchanged.
