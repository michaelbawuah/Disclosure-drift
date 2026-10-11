# Public sources for historical issuer corroboration

Checked **2026-10-11 UTC**. Two public SEC routes supply dated issuer
observations without depending on the saved CCM current company header:
ownership-form issuer metadata and Schedule 13D/G subject-company evidence.
The [source ledger](../reports/public_historical_identity_sources.json) records
the actual downloaded bytes, hashes, source locations, complete delivered
metadata schema, and the bounded inspection results below.

This work creates **zero historical security links, availability timestamps,
source approvals, or human reviews**. No licensed rows, market-return files,
transaction/holdings tables, or final-period sources were read. The existing
historical dataset contract and completed reviews remain unchanged.

## A concrete issuer-to-CUSIP observation

The original [Masimo Schedule 13G/A header][masimo-header] and
[primary document][masimo-primary], accession **0001228621-20-000002**, contain:

| Source location | Reported observation |
|---|---|
| Header `SUBJECT-COMPANY` / `COMPANY-DATA` | Masimo, CIK `0000937556` |
| Header `FILED-BY` / `COMPANY-DATA` | Reporting person, CIK `0001228621` |
| Primary cover and Item 2 | CUSIP `574795100`; common stock, $0.001 par value |
| Primary reported event date | December 31, 2019 |
| Header acceptance clock | February 10, 2020, 16:10:59 Eastern |

The subject company and reporting person are separate roles. The
[SEC header specification][pds], section 3.3.1, documents those separate nests.
Using the reporting person's CIK, or the accession prefix, would attach this
security to the wrong entity. The ledger binds both roles to exact header byte
spans and the cover observations to their positions in the parsed primary.

This supplies documentary evidence linking a reported security identifier and
class to the subject issuer **in this submission**. A later private comparison
could check the identifier against a dated Names security record. That would
still require review of date coverage, share class, corporate actions and
ambiguities before approving a PERMNO mapping. No such join was performed here.

The report was accepted **after** the January 1, 2020 selection. Its December 31
event date does not establish that this evidence was available by the selection
cutoff. A single filing observation also does not establish a continuous
identity interval before or after that date.

## Actual public bulk-data demonstration

The [SEC Insider Transactions Data Sets][insider] provide quarterly extracts of
ownership Forms 3, 4 and 5, including amendments, beginning in 2006. The
[official dictionary][insider-dictionary] separates issuer identifiers in
`SUBMISSION` from reporting-person identifiers in `REPORTINGOWNER`. These are
filing extracts; SEC warns that filing and extraction errors can remain and
that original submissions provide the fuller evidence.

The **2019 Q4** ZIP was downloaded successfully. Only `SUBMISSION.tsv` was
decompressed and read; the ZIP directory was inspected for member names, sizes,
and checksums. Transaction, holdings, reporting-owner and other member bodies
were not opened. The archive and complete original SUBMISSION values were
preserved without removing amendments, deduplicating records, or normalizing
identifier and ticker literals.

| Metadata inspection | Actual result |
|---|---:|
| Submission records | **38,145** |
| Distinct reported issuer CIK literals | **4,247** |
| Distinct exact issuer-CIK/ticker-literal groups | **4,348** |
| Distinct ticker literals | **4,241** |
| Amendment records retained | **649** |
| Issuer CIKs with more than one reported ticker literal | **94** |
| Ticker literals appearing with more than one issuer CIK | **18** |
| Duplicate accession excess | **0** |
| Filing-date range | **2019-10-01–2019-12-31** |

These groups are observations for discovery, not approved security mappings.
For example, the extract contains **38** records pairing Disney's issuer CIK
`0001744489` with `DIS`, **14** pairing NIKE's `0000320187` with `NKE`, and
**9** pairing Masimo's `0000937556` with `MASI`. The ledger names example
accessions for original-document follow-up. This quarter has no row using
Disney's predecessor CIK `0000102909`; that absence alone establishes neither
its earlier history nor a research exclusion.

### Preserve the source's unresolved values

Nonempty ticker text is not necessarily a usable unique ticker. The extract
contains `NONE` in **388** records, `N/A` in **104**, and the combined literal
`ISCA, ISCB` in **115**. Other capitalization variants are retained separately.
Multiple reported symbols can reflect classes, changes, placeholders or errors;
this inspection does not choose among those explanations.

One `PERIOD_OF_REPORT` is the literal **`05-DEC-0019`**. It remains unchanged,
and the ledger identifies its accession. Other records report dates years
before filing. Neither a repair to 2019 nor substitution of report date for
filing/publication date is justified by this inspection.

The delivered schema has **`FORM3_HOLDINGS_REPORTED`**, while section 5.1 of the
downloaded dictionary prints **`FORM3_HOLDING_REPORTED`**. Both observations
are preserved. The note does not silently rename the field or claim that this
dictionary is a version-matched description of every delivered column.

## What these sources do and do not resolve

The ownership extract can supply historical **issuer CIK/ticker observations**
for candidate discovery, including cases whose saved current header lacks a
CIK. The Schedule 13D/G route can add a **reported CUSIP and class tied to the
subject issuer in one accession**. Neither supplies a complete PERMNO crosswalk,
listing population, continuous effective interval, or historical `known_at`.

The downloaded 2019 Q4 ZIP's HTTP `Last-Modified` is in **September 2022**.
That is recorded retrieval metadata, not evidence of its initial publication.
The [SEC timestamp FAQ][timestamps] distinguishes filing, acceptance and change
dates and states that submission timestamps do not identify first website
availability. The [EDGAR access guide][access] also describes post-acceptance
corrections and deletions. The newly inspected sources therefore do not resolve
the historical availability or vendor-version gaps in the
[completion guide](research_completion_gates.md).

The next useful action is to use complete dated Names descriptors to identify
unresolved candidates, inspect development-period issuer observations for those
candidates, and retrieve the relevant original ownership XML/header or
Schedule 13D/G submission. Preserve every conflicting candidate and review the
specific class/date relationship. Evidence from these sources can support that
work; it cannot silently fill the remaining historical availability fields.

## Preserved evidence

The original public sources and the collection receipt are under
`outputs/public-identity-research-20261011/` on the research machine. The
committed [ledger](../reports/public_historical_identity_sources.json) identifies
each source by URL, byte count, SHA-256 and retrieval time. The main bindings are:

| Preserved source | SHA-256 |
|---|---|
| 2019 Q4 SEC ZIP | `df28aa75bf703f0c202c59d94046e84e8e082a97a49965a4b66149d3184e540c` |
| Exact `SUBMISSION.tsv` | `0f73eaa50e3964641fe180cb2db299d94ae5b77e4d12d3a68ba1ab5b663b6e2c` |
| Masimo original header | `b0916d201ca4e7a2873eb146b98c57f830a4acb955de4437d499f1a6091c8b69` |
| Masimo primary | `65b4a6b4b00e4f6d7e6de3f3128fe440168ce175f0b1966bf96e39e244d72bff` |

[masimo-header]: https://www.sec.gov/Archives/edgar/data/937556/000122862120000002/0001228621-20-000002.hdr.sgml
[masimo-primary]: https://www.sec.gov/Archives/edgar/data/937556/000122862120000002/schedule13ga-2019.htm
[insider]: https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets
[insider-dictionary]: https://www.sec.gov/files/insider_transactions_readme.pdf
[pds]: https://www.sec.gov/info/edgar/pdsdissemspec051310.pdf
[timestamps]: https://www.sec.gov/about/webmaster-frequently-asked-questions
[access]: https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
