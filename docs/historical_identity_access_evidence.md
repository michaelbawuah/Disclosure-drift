# Historical identity: access alternatives and evidence limits

Checked **2026-10-11 UTC**. Public documentation research only; no new source
approval, licensed export, or protocol amendment. The completed
[20/20 arithmetic and timing review](../reports/review_progress/user_arithmetic_receipt.json)
remains complete.

**The best next lead is CRSP/Compustat Merged Company History.** CRSP documents a
historical CIK field alongside effective bounds and company/security links.
This establishes a documented alternative to investigate; it does **not**
establish that the current WRDS account can obtain it. The next useful input is
that history and its source documentation, rather than another copy of the
current company header. [CRSP dictionary][company-history]

## What is already established

The saved CCM export contains dated GVKEY/PERMNO links and current company
header identifiers. Link validity dates do not turn the header CIK into a dated
CIK observation. The specific full SEC Analytics form for `wrdssec_common`
displayed **Submit Form (Not Subscribed)** under the selected institution and
session. This is the recorded access result, not proof of pass expiry or a
permanent, institution-wide entitlement decision. See the existing
[source conventions](wrds_source_conventions.md#7-current-company-headers-cannot-establish-historical-ciks)
and [identity evidence](identity_source_evidence.md).

## Retrieved primary evidence

Every external source below was opened during this research. Catalog entries
describe products; they do not certify this user's access or the contents of a
saved export.

| Route or source | What the source establishes | Exact boundary and practical use |
|---|---|---|
| [CRSP Company History dictionary][company-history] | `HCIK` is historical CIK; `HCHGDT`/`HCHGENDDT` bound the description's effectiveness. The dictionary also lists `GVKEY`, `LPERMNO`, `LPERMCO`, and `LINKRANGETYPECD`. A zero linked PERMNO is a missing/not-applicable value. | Strongest alternative source lead. The dictionary does not establish current WRDS table names, actual historical coverage, revision history, or when each fact became available. |
| [WRDS CRSP product catalog][crsp-catalog] | Separate annual, monthly, and quarterly CCM products are listed as `crsp_a_ccm`, `crsp_m_ccm`, and `crsp_q_ccm`. | Ask which authorized product exposes Company History. The annual/monthly dictionary links redirected this unauthenticated documentation read to login; their table contents were not inspected. Product update dates are not the saved file's release evidence. |
| [WRDS SEC Suite presentation, slide 22][sec-suite] | `WCIKLINK_GVKEY` connects GVKEYs with historical CIKs to help retain filing histories through restructurings. | This remains a documented alternative if authorized access is later confirmed. The presentation does not establish an effective-interval or historical-availability schema for this project; the observed full-form denial remains unresolved. |
| [WRDS historical identifier tutorial][historical-identifiers] | `sec_history` and `sec_idhist` support historical security identifiers. The displayed identifier list includes CUSIP, exchange, ISIN, SEDOL, and ticker. The tutorial distinguishes some nominal earliest dates from actual coverage starts. | CIK is absent from that displayed list. These tables can help corroborate security matches, but this tutorial does not establish a historical CIK replacement. Its linked detailed support page required login. |
| [SEC API documentation][sec-api] and [EDGAR access guide][sec-access] | Public APIs expose filing history by CIK without credentials, including references to additional history files. EDGAR also documents historical indexes, filing documents, and header paths. | Automated discovery and document-level corroboration are feasible. These sources do not supply a complete GVKEY/PERMNO crosswalk. Current ticker/name associations cannot establish historical security identity; the [SEC FAQ][sec-faq] explains that an accession prefix can belong to a filing agent rather than the registrant. |
| [WRDS/S&P webinar, slide 21][snapshot] and [WRDS S&P catalog][sp-catalog] | Compustat Snapshot preserves successive data versions using dates tied to delivery into the product. WRDS lists `comp_snapshot` separately. | A real delivery-vintage lead. The retrieved material does not verify that the needed CIK/classification fields, CRSP daily inputs, or the user's account are covered. Do not substitute financial-statement vintage evidence for those unverified fields. |
| [Cornell Management Library database guide][cornell] | Cornell describes WRDS day passes for current faculty, students, and staff, and individual accounts for JCB faculty and students. The page gives `mgtref@cornell.edu` as its reference contact. | A legitimate contact for product-level access clarification. This general page does not prove personal eligibility, Company History entitlement, or SEC Analytics entitlement. |

## Historical availability: distinguish the contracts

The [frozen historical dataset contract](historical_dataset.md) requires
historical `known_at` for listing classifications and identity links, and
`available_at` for daily liquidity. Selection uses the preceding year's final
XNYS close as its information cutoff. A fact's effective date, the date a
researcher retrieved it, and the date a vendor published its guide are different
quantities. None can silently fill those fields.

For **listing and identity facts**, a dated vendor history can establish an
effective interval. To establish availability before the selection cutoff, seek
documented publication/update semantics or a preserved, dated source version
containing that exact fact. Snapshot is a possible source of such evidence only
after the relevant fields, version dates, and coverage are verified. A later
corporate filing explaining an earlier reorganization supplies retrospective
corroboration; it does not alone establish when the mapping was historically
known. Any conservative bound must be documented and reviewed before use.

For **liquidity**, the missing evidence concerns availability of the specific
price/volume observations and their revision conventions. A session date does
not certify that today's vendor value was available at that session's close.
Request applicable vendor release/revision documentation or preserved versions.
No retrieved source here establishes a complete historical `available_at`
solution for the delivered daily series. Guide publication dates and catalog
refresh dates also do not identify its actual release.

For **filing pairs**, the existing contract already allows
`availability_status=documented_assumption` with explicit evidence and review.
The frozen second-session proxy remains available under that status. Exact first
publication timestamps are **not a new universal requirement**. A `verified`
claim is stronger: SEC's [Webmaster FAQ][sec-faq] distinguishes acceptance from
website availability, describes variable dissemination lag, and states that its
filing timestamps do not identify first availability on the website. Acceptance
alone, or acceptance plus an assumed fixed delay, cannot be relabeled verified.
This distinction does not reopen the completed timing review.

Optional corroboration has limits. SEC's [log documentation][sec-logs] covers
2003-01-01–2017-06-30 and 2020-05-19–2025-06-30, reports the intervening gap as
unavailable, and warns that traffic is incomplete. Its [variable guide][log-fields]
shows response status in older logs, but only request time and URI in the newer
files. A recorded request alone does not prove successful delivery or the exact
content served. The [PDS description][pds] documents a paid dissemination feed
and recent archives, not a guaranteed retrospective archive covering the whole
study. These are optional filing-evidence leads, not substitutes for universe
availability or additional gates imposed by this note.

## The next obtainable input

Request **the authorized Company History schema and historical CIK export**, or
an explicit answer that this product is unavailable. Ask for the dictionary
fields in the first table row, histories covering the 2010–2021 annual selections
and development events, and boundary records needed to interpret the intervals.
Preserve any supplied history outside the development window as raw evidence;
do not open the final evaluation period.

The response should identify the actual WRDS product/table or supported export,
coverage and exclusions, boundary/missing-value semantics, vendor release, and
whether effective dates describe economic validity, vendor observation, or both.
Request separate availability/revision evidence where those meanings differ.
Keep the original file and delivered query/parameter evidence; do not invent SQL
when the export does not provide it.

Meanwhile, automated work can organize all saved Names/CCM candidates, preserve
their provenance and overlaps, enumerate missing evidence, and discover relevant
SEC filings. Once historical CIK evidence arrives, an interval join can be
staged and conflicts surfaced for review. Those operations cannot manufacture
missing timestamps, choose a current-header CIK as historical truth, certify
population completeness, or create human source approvals. The current
candidate outputs remain unapproved; source reconciliation and the empirical
milestone gates remain as recorded in the
[execution report](../reports/RESEARCH_EXECUTION_UPDATE.md).

## Unsent access request

**Draft only — not sent.** Intended recipient: Cornell Management Library
reference service, for coordination with the appropriate WRDS administrator.

> Subject: Historical CIK in CRSP/Compustat Company History
>
> I am preparing a historical disclosure study using preserved CRSP and CCM
> exports. The SEC Analytics CIK–GVKEY form displayed Not Subscribed for
> `wrdssec_common` in my selected institution/session. Could you confirm whether
> my authorized CCM access includes Company History with historical CIK and
> effective bounds, and identify the supported WRDS table/export?
>
> I need histories covering 2010–2021 selections and development events, with
> the data dictionary, coverage, release, and date/revision semantics. Please
> also advise whether dated versions or documentation establish when these
> identifiers, listing classifications, and daily price/volume observations were
> available. If Company History is unavailable, is another product I am entitled
> to use suitable for historical CIK–GVKEY/PERMNO evidence?

[company-history]: https://www.crsp.org/wp-content/uploads/ccm_files/CompanyHistory.html
[crsp-catalog]: https://wrds-www.wharton.upenn.edu/pages/about/data-vendors/center-for-research-in-security-prices-crsp/
[sec-suite]: https://wrds-www.wharton.upenn.edu/documents/1439/WRDS_SEC_Suite_PowerPoint_for_Video_Learning.pdf#page=22
[historical-identifiers]: https://wrds-www.wharton.upenn.edu/pages/wrds-research/database-linking-matrix/using-compustat-historical-identifier-notebook/
[sec-api]: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
[sec-access]: https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
[snapshot]: https://wrds-www.wharton.upenn.edu/documents/2180/WRDS_SP_Webinar_Feb_002.pdf#page=21
[sp-catalog]: https://wrds-www.wharton.upenn.edu/pages/about/data-vendors/sp-global-market-intelligence/
[cornell]: https://johnson.library.cornell.edu/databases/
[sec-faq]: https://www.sec.gov/about/webmaster-frequently-asked-questions
[sec-logs]: https://www.sec.gov/data-research/sec-markets-data/edgar-log-file-data-sets
[log-fields]: https://www.sec.gov/files/variables-edgar-log-file-data-sets.pdf
[pds]: https://www.sec.gov/oit/announcement/public-dissemination-service-system-contact.html
