# Historical availability: what the source dates establish

Official documentation checked **2026-10-11 UTC**. This assistant assessment
identifies the evidence needed to turn saved market candidates into historical
inputs. It creates no source approval or availability timestamp. The frozen
protocol and the completed filing and arithmetic reviews remain unchanged.
The structured source record is
[historical_availability_sources.json](../reports/historical_availability_sources.json).

## A documented correction inside the development period

The official [August 2026 CRSP release note][release] links to a
[ten-page PDF][release-pdf]. Page 3, **Individual Edits**, records the following
for **PERMNO 32791, WEATHERFORD INTERNATIONAL PLC**, over
**2015-05-13–2019-05-12**:

| Release-note field label | Before | After |
|---|---|---|
| Exchange code | `0` | `1` |
| Primary exchange | `X` | `N` |
| Trading status | `X` | `A` |
| Security status | `X` | `R` |
| Market history | Earlier state not detailed | Restored for that interval |

These are the vendor note's labels, not an automatic mapping to delivered CIZ
column names. This establishes a real retrospective correction affecting years
inside the study. It does not establish that a particular saved row changed or
which vintage produced it. A bounded Names-only comparison can test consistency
with the corrected classifications without reading returns. Consistency would
not uniquely identify a release.

The release metadata itself is inconsistent: the title says **August 2026**,
the narrative and file-version section refer to **July** data, the calendar
reaches **August 31**, and the landing page displays **September 30, 2026** as
its effective date. Preserve these observations; none identifies the saved
export's actual release. The original query/package evidence must provide that
binding.

### Saved Names comparison

The [bounded production check](../reports/historical_revision_case.json) completed
on the Mac at **2026-10-11T10:25:30.947443+00:00**. It verified **18 preserved Names
parts**, scanned **86,064 annual rows**, and retained **12 annual occurrences**
for the public case. All **four expected January 1 selections, 2016–2019**, were
present with **zero ambiguous snapshots**. **All four disagree with at least one
of the two published corrected literals** used in the comparison: primary
exchange `N` and trading status `A`.

This is a literal comparison of saved January 1 metadata. It does not compare
the full daily interval, map the other two release fields, or identify a prior
vendor vintage. The original Names CSV was not reread; the check verified the
preserved candidate parts and their bound source provenance. Licensed source
rows remain private. No daily market files or outcomes were opened, and the
result creates no source approval or availability timestamp. The disagreement
gives the source supplier a concrete case to reconcile; its cause and the saved
source version remain unidentified.

## Four dates that must remain separate

| Date or interval | What it can establish | What it does not establish by itself |
|---|---|---|
| Economic effective interval | When a classification or identity applies | When the fact first became known or was delivered |
| Vendor observation/delivery interval | When that version appeared in a specified product, if documented | Earlier public availability in another source |
| Source-release/version date | Which documented version a preserved file belongs to, if bound to the export | The original availability of every historical record |
| Researcher download time | When the researcher obtained the saved bytes | Availability before a historical prediction cutoff |

CRSP's [Company History dictionary][company] explicitly supplies effective
description bounds `HCHGDT`/`HCHGENDDT` and historical CIK `HCIK`, alongside
`GVKEY`, `LPERMNO`, `LPERMCO`, and `LINKRANGETYPECD`. It does not identify a
first-delivery timestamp. Obtaining this history can resolve effective identity
without automatically resolving `known_at`.

The [WRDS TAQ–CRSP guide][taq], version 1.1, February 2022, page 3 footnote 6,
describes a **2–3-month CRSP Monthly update lag** and gives December 2019 data
delivered in February 2020 as an example. This is evidence that an observation
date and vendor delivery can differ materially. It is not a universal lag rule
for every product, field, and year.

The current [CRSP release calendar][calendar] separately schedules stock/index
and CCM deliveries. CRSP's [mapping-type][mapping-type] and
[mapping-subtype][mapping-subtype] dictionaries also document recalculated
values and changed date-placement conventions. Neither a calendar nor a CIZ-to-SIZ
column conversion reconstructs earlier source vintages or explains the project's
benchmark differences.

## Availability of a vendor value versus market information

The [historical input contract](historical_dataset.md) requires `known_at` for
listing/identity facts and `available_at` for liquidity, with explicit timezones.
The selector compares them with the preceding year's final XNYS close. It does
not require CRSP to be the only possible historical information channel.

If the claim concerns **the exact vendor version**, delivery after cutoff cannot
support using that version by cutoff. The December 2019 → February 2020 example
therefore cannot establish timely vendor delivery of those December observations.
Actual release records are needed to determine how many observations in a
60-session window satisfy the 40-observation minimum; the general lag description
does not prove every year fails.

If the claim concerns **underlying market information**, a contemporaneous source
could support it. The audit needs compatible price/volume definitions, identity
and adjustment rules, a defensible availability bound, and a treatment of later
corrections. Assuming today's corrected CRSP values equal information observable
at the historical close does not establish those facts. Such an approximation
would require a separately documented retrospective design, not filled primary
timestamps or automatic completion of the current protocol.

For filing pairs, the existing `documented_assumption` route remains available.
The [SEC FAQ][sec] distinguishes acceptance from first website availability.
This note neither removes the two-session proxy nor introduces a new universal
first-publication requirement. That filing exception does not extend to unknown
historical listing or liquidity timestamps.

## Exact evidence to obtain next

The useful request is **historical identity plus version/date semantics**, rather
than another current company header or an unexplained repeat of the daily file.

| Requested evidence | Required content and purpose |
|---|---|
| Authorized Company History schema and export | `HCIK`, `HCHGDT`, `HCHGENDDT`, `GVKEY`, linked `LPERMNO`/`LPERMCO`, and `LINKRANGETYPECD`, or documented equivalents. Cover the 2010–2021 January 1 selections and development events, including necessary boundary records. Preserve original markers and all conflicting intervals. Identify the actual WRDS product/table; do not invent a query name. |
| Preserved source version | Product/library/view, original package or release identifier, data-cut date, release notes or manifest, exact query/parameters, and the preserved file's hash. Distinguish vendor release, WRDS ingestion, and researcher retrieval. Explain whether an annual/monthly snapshot has been revised since its first delivery. |
| CIK and classification availability | Identify which native dates mean economic effectiveness, first observation, delivery, or correction. Supply preserved dated versions containing the relevant fact, or a documented conservative bound tied to that fact. Specify date timezone and granularity; an effective-date field alone is insufficient. |
| Price/volume availability and revisions | Establish availability of the specific observations used in liquidity and controls, their price/volume units and conventions, adjustment treatment, revision policy, and any preserved earlier versions. A session date or current guide date alone is insufficient. |

The [WRDS/S&P webinar][snapshot], slides 21–22, describes Compustat Snapshot
dates tied to product delivery and preservation of successive values. This is a
promising type of evidence, but its coverage of the required CIK/classification
fields and this user's access remain unverified. It cannot substitute for CRSP
market-data vintage evidence merely because both products contain historical data.

No request was sent. No WRDS session or query was opened. Public documents were
inspected through retrieval; their original PDF/HTML bytes were not archived or
assigned invented content hashes. The saved export vintage and historical
availability fields remain unknown until source-bound evidence establishes them.

[company]: https://www.crsp.org/wp-content/uploads/ccm_files/CompanyHistory.html
[taq]: https://wrds-www.wharton.upenn.edu/documents/1336/NYSE_Daily_TAQ_to_CRSP_Linking_BPNFjWm.pdf
[release]: https://indexes.morningstar.com/docs/release-note/crsp-us-stock-database-release-notes-august-2026-monthly?isRdp=true
[release-pdf]: https://indexes.morningstar.com/api/docs/6abeb4ad280ccc81416648b9
[calendar]: https://indexes.morningstar.com/docs/other-documents/morningstar-crsprdp-release-calendar?isRdp=true
[mapping-type]: https://www.crsp.org/wp-content/uploads/appendix/FlagType_MT.html
[mapping-subtype]: https://www.crsp.org/wp-content/uploads/appendix/FlagType_MU.html
[snapshot]: https://wrds-www.wharton.upenn.edu/documents/2180/WRDS_SP_Webinar_Feb_002.pdf
[sec]: https://www.sec.gov/about/webmaster-frequently-asked-questions
