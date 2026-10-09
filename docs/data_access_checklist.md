# Market-data access gate

Open Cornell's current WRDS entry point:
https://johnson.library.cornell.edu/database/wharton-research-data-services-wrds/

Check actual entitlements rather than assuming the platform contains every needed
subscription. This build has not signed in to a Cornell or WRDS account.

Cornell's entry page was checked on 9 October 2026. It lists day-pass access for
current Cornell students, faculty and staff, and describes individual accounts for
JCB faculty and students. For an Engineering undergraduate, begin with the listed
day-pass route; do not assume eligibility for an individual account or a particular
dataset. The next user action is to open the Cornell entry point and check whether
CRSP and the required historical tables are available. No private entitlement has
been verified by this project.

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
fields blank. Current verification uses invented market returns only.

If access remains unavailable, continue the public filing pipeline and extraction
audit. Record that market-return research is blocked. A current ticker list or
surviving-stock sample is not an equivalent replacement for the historical universe.

Primary documentation:
- SEC API: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- CRSP format cross-reference: https://www.crsp.org/crsp_pdf/crsp-us-stock-indexes-databases-siz-to-ciz-cross-reference-guide/
- CRSP format/delisting conventions: https://www.crsp.org/wp-content/uploads/appendix/FlagType_MU.html
