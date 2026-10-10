# Market-data access gate

Open Cornell's current WRDS entry point:
https://johnson.library.cornell.edu/database/wharton-research-data-services-wrds/

Check actual entitlements rather than assuming the platform contains every needed
subscription. The owner completed authenticated WRDS sample exports on 9 October
2026. Their files have been inspected; see the [sample evidence](wrds_sample_exports.md).

Cornell's entry page was checked on 9 October 2026. It lists day-pass access for
current Cornell students, faculty and staff, and describes individual accounts for
JCB faculty and students. For an Engineering undergraduate, begin with the listed
day-pass route; do not assume eligibility for an individual account or a particular
dataset. Successful samples now establish access to the observed daily-stock,
historical Names and CCM query outputs. They do not establish complete historical
coverage, access to every required table or a completed market-data audit.

## Quick entitlement check

1. Open the Cornell page above and select **Connect to Wharton Research Data
   Services (WRDS)**. Follow the Cornell authentication and day-pass instructions.
   Cornell marks this resource **on-campus only**; start on campus. Do not assume
   that owning a Cornell email address grants an individual WRDS account.
2. Once in WRDS, find the CRSP stock-data product and open its daily stock query.
   Look for the current Version 2/CIZ product, and record the exact product,
   release, table and visible field names. Menu wording can vary by subscription.
3. For a minimal access test, use **AAPL, 2021-01-04 through 2021-01-08**. Select
   the permanent security identifier, observation date and daily total return
   including distributions, using that table's dictionary. Download a CSV.
   AAPL is only a convenient access test, not the study's identity-mapping rule.
4. A successful live query/export verifies access to **that table only**. A CRSP
   logo, documentation page or public demo does not. Record any subscription or
   permissions error exactly; do not repeatedly retry an access denial.
5. Report the result or share the dataset/error screen with account details hidden.
   Keep licensed extracts local under `data/`; do not commit them to public git.

If the route is unavailable to your student category, ask Cornell Management
Library's reference desk at **mgtref@cornell.edu** whether Engineering
undergraduates can use the CRSP US Stock and Indexes data through a day pass,
and how to obtain the required historical returns and identifiers. This project
has not contacted the library or requested an account on your behalf.

Passing this quick check does not yet establish access to the benchmark, historical
links or other tables below. Record those separately before the full export.

## Research data coverage

For each item, record dataset/table, release/version, export time, date coverage,
available identifiers, permission constraints and any missing fields:

- [ ] Daily security returns including dividends; identify precise return convention.
- [ ] Delisting event/payoff information and missing-return flags.
- [ ] Historical security name/type/exchange records, including inactive securities.
- [ ] Dated issuer/CIK-to-security links, with handling of multiple share classes.
- [ ] Historical price, volume and shares/market cap for the annual liquidity universe.
- [ ] Historical industry classification; avoid assigning current industries backward.
- [ ] A consistent daily value-weighted market total-return benchmark.
- [ ] Rights to store local extracts and publish only permitted derived examples.

Export a small, inspectable sample first: an ordinary continuing stock, one that
delisted, and one that changed identifiers. Include a holiday and a corporate-action
date if possible. Never put account credentials in this repository or a chat message.

The exact source-field mapping is pending your available export format. In
particular, legacy separate delisting returns must not be blindly added to a modern
return field that already incorporates that payoff. CRSP's format/version and
delisting flags must be checked against the source documentation before normalization.

The [normalized import and event-label staging tools](market_import.md) are ready
for that verified sample. The manifest template intentionally leaves source-specific
fields blank. Importer tests still use invented market returns. Actual sample
observations have been inspected separately, without importing research labels.

The [pilot export request](pilot_market_request.md) supplies exact dates for all
135 current development events and a pending 20-event label/control trace sample.
It loads no market outcomes and provides no entitlement or human-review sign-off.

If access remains unavailable, continue the public filing pipeline and extraction
audit. Record that market-return research is blocked. A current ticker list or
surviving-stock sample is not an equivalent replacement for the historical universe.

Primary documentation:
- SEC API: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- WRDS current CRSP format guides: https://wrds-www.wharton.upenn.edu/pages/data-announcements/changes-to-crsp-data/
- CRSP research-data product entry: https://indexes.morningstar.com/
- CRSP format/delisting conventions: https://www.crsp.org/wp-content/uploads/appendix/FlagType_MU.html

Links checked 2026-10-09. The former CRSP cross-reference URL returned 404;
use the WRDS transition page's Cross Reference Guide and User Guide links.
