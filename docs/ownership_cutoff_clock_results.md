# Original SEC clocks for all 14 cutoff-day-only cases

**All 39 original SEC acceptance clocks are now resolved against the exact
December 31, 2019 XNYS close: 16 are before the cutoff and 23 are after it.**
Across the 14 saved cases, three have only earlier acceptance clocks and eleven
have only later clocks. None is exactly at the cutoff or remains unresolved.

The complete [source-bound result](../reports/ownership_cutoff_clock_resolved.json)
retains every quarterly source occurrence, original SEC URL, source hash,
retrieval receipt, exact header field, and XML issuer field with byte locations.
The original 2020 cohort and its stored statuses remain preserved in their
existing immutable bundle. This follow-up resolves acceptance-clock facts; it
does not assign historical public availability or approve a security mapping.

## Complete queue and exact cutoff

The audit reselected every `CUTOFF_DAY_OBSERVATIONS_ONLY` case from all **4,122**
rows of the pinned 2020 cohort summary, then retained every related observation
and every quarterly occurrence of the selected accessions. Its 14 cases have
**39 saved unambiguous literal observation relationships**, **39 quarterly
occurrences**, and **39 distinct accessions**. No source occurrence repeats in
this particular queue. The collection and inspection code retain repetitions
when they exist.

The frozen protocol's `year_start_window(2020)` reconstructs the final exchange
close before selection using **XNYS**, exchange_calendars **4.13.2**:

| Calendar fact | Value |
|---|---|
| Selection as of | 2020-01-01 |
| First selection session | 2020-01-02 |
| Cutoff session | 2019-12-31 |
| Exact cutoff in New York | **December 31, 2019, 16:00:00 EST** |
| Exact cutoff in UTC | **December 31, 2019, 21:00:00 UTC** |
| Frozen protocol SHA-256 | `3951be086ed9a74ec69a304004ebcb5aed63bac161e043ff92ae4f51b8e325d9` |

Original `ACCEPTANCE-DATETIME` values are interpreted in
`America/New_York`, retaining the applicable offset. The comparison uses
timezone-aware timestamps and separates strict before, exact equality, and
strict after. `FILING_DATE`, period of report, original-submission date, change
date, HTTP dates, and current retrieval clocks never replace acceptance.

| Clock result | Distinct original accessions | Saved cases |
|---|---:|---:|
| Strictly before the cutoff | 16 | 3 with all original clocks before |
| Exactly at the cutoff | 0 | 0 |
| Strictly after the cutoff | 23 | 11 with all original clocks after |
| Unresolved | 0 | 0 |
| **Total** | **39** | **14** |

There are no cases with both earlier and later original acceptance clocks.

## Source examples and issuer groups

These groupings use **public SEC issuer metadata**, rather than publishing
licensed security identifiers or Names/CCM associations.

| Public SEC issuer | Original accessions | Acceptance range on December 31, 2019, EST | Relative to 16:00 |
|---|---:|---|---|
| Avenue Therapeutics, Inc. | 1 | 06:01:52 | Before |
| Merus N.V. | 1 | 08:00:31 | Before |
| Cronos Group Inc. | 14 | 09:36:36–14:24:13 | Before |
| Echo Global Logistics, Inc. | 1 | 16:05:31 | After |
| Quaker Chemical Corp | 2 | 16:06:30–16:08:03 | After |
| Oragenics Inc | 1 | 16:10:30 | After |
| Atlanticus Holdings Corp | 2 | 16:15:21–16:15:49 | After |
| International Bancshares Corp | 1 | 16:52:13 | After |
| Gossamer Bio, Inc. | 1 | 17:00:11 | After |
| Mr. Cooper Group Inc. | 1 | 17:00:21 | After |
| Abeona Therapeutics Inc. | 1 | 17:17:03 | After |
| Diamond Eagle Acquisition Corp. | 7 | 18:15:31–18:38:42 | After |
| Medicines Co | 5 | 19:54:03–19:55:58 | After |
| Reliant Bancorp, Inc. | 1 | 21:14:59 | After |

For example, the original
[Echo Global Logistics submission](https://www.sec.gov/Archives/edgar/data/1426945/000110465919077308/0001104659-19-077308.txt)
records acceptance at **16:05:31 EST**, just five minutes and 31 seconds after
the cutoff, while the
[Avenue Therapeutics submission](https://www.sec.gov/Archives/edgar/data/1644963/000114036119023473/0001140361-19-023473.txt)
records **06:01:52 EST**, before the cutoff. Both have the same quarterly
filing date. The filing date alone cannot distinguish their position relative
to the exchange close.

## Original issuer inspection

All 39 complete original submissions were preserved, totaling **458,962 bytes**.
They comprise **19 Form 3** and **20 Form 4** submissions. Every original header
accession, submission form and filing date agrees with its exact quarterly
source record. All 39 header issuer CIKs and issuer names match; all 39 XML
issuer CIKs, entity-decoded issuer names and trading symbols match. Original
header and XML issuer CIKs agree in all 39.

The inspector preserves **44 separately labeled reporting-owner role
occurrences**. It selects the original `ISSUER` role and the single direct
XML `issuer` element. It does not substitute reporting owners, the archive
directory CIK, or the accession prefix for the issuer. Reporting-owner CIKs
equal the issuer CIK in **0** observed roles.

The XML pull parser receives only the prefix through the direct issuer element.
It reads document type and separately labeled report/original-submission dates
from that prefix. It receives no transaction, holdings, reporting-owner,
footnote, remarks or signature sections. The complete source bytes are retained;
no claim of full-document XML validation is made. Raw XML text, entity-decoded
text and original byte positions remain distinct in the ledger.

## Retrieval provenance and unchanged evidence

The first ordinary Mac collection produced **39 HTTP 403 responses**. Its
[original failure report](../reports/ownership_cutoff_clock_audit.json),
per-accession attempts and collection receipt remain intact.

An ordinary container HTTPS request to an exact queued original URL succeeded
with the same honest research User-Agent. The public collector then preserved
the remaining 38 sources. It used two workers, at least 0.6 seconds between
request starts, a 30-second timeout and an 8 MiB per-source ceiling. It used
no retries, alternate archive paths, disguised headers or access bypass.
Successful original collection occurred on **October 11, 2026,
16:30:16–16:32:26 UTC**.

All 118 public source/receipt/attempt files were transferred to the Mac without
changing their bytes. Offline inspection checked source hashes before and
after parsing. The final report binds both the source transport and the
retained Mac failure evidence. Every original bundle file and every consumed
protocol, calendar and data input remained unchanged.

The initial audit's exact executed code is retained as
`outputs/cutoff-clock-followup-20261011/ownership_cutoff_clock_audit.executed.py`.
Two later `noqa: E402` annotations on its repository bootstrap imports fixed
the linter warning without changing behavior. The offline resolution binds and
executes the current inspector separately. All three tracked scripts pass Ruff.

## Reproduce the offline inspection

Where the preserved source files and private queue exist on the authorized
data host, use new output and report paths:

```bash
.venv/bin/python scripts/ownership_cutoff_clock_resolve.py \
  --output outputs/cutoff-clock-followup-20261011/recheck-new-run \
  --report reports/ownership_cutoff_clock_recheck_new_run.json
```

The standalone original audit is
`scripts/ownership_cutoff_clock_audit.py`; the ordinary public collector is
`scripts/ownership_cutoff_clock_collect_public.py`. The resolver consumes the
preserved public originals and performs no network requests. Licensed case
associations stay in the private output subdirectories on the Mac.

## What this resolves

This resolves every previously unknown **original acceptance clock** in the
14-case queue and confirms the original issuer metadata for all 39 sources.
It does not establish when each submission first became publicly accessible;
the [SEC timestamp guidance](https://www.sec.gov/about/webmaster-frequently-asked-questions)
distinguishes its recorded filing-system clocks from website availability.

The three cases with earlier acceptance remain subject to historical
availability, share-class and security-link evidence. The eleven cases with
later acceptance have no earlier clock among this complete set of originals.
Absence of an earlier observation here does not establish absence from all
possible SEC sources.

All `known_at`, `available_at`, and effective-link bounds remain null.
Approved historical links, source approvals and human reviews remain zero;
`model_ready` remains false. The source audit opened no market returns or
final-period outcomes and changed no empirical access gate.
