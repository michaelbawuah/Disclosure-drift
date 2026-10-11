# Original SEC issuer checks for 47 queued 2019 observations

**All 47 queued observations now have matching original SEC issuer evidence.**
Each complete original submission was preserved, its original header identified
the issuer separately from reporting owners, and its ownership XML reported the
same issuer CIK, issuer name and ticker as the queued 2019Q4 source occurrence.
This confirms **original issuer observations**, with no approved security mapping
or historical availability claim.

The [complete source ledger](../reports/sec_ownership_original_followup.json)
contains every queued occurrence, original SEC URL, SHA-256 hash, byte count,
retrieval receipt, selected field and byte location. The 47 original files total
**412,879 bytes**, downloaded on **October 11, 2026, 15:37:22–15:40:04 UTC**.
There were no HTTP failures, unresolved source structures or literal name/ticker
differences. Every queue record remains accounted for.

## What was checked

| Check | Actual result |
|---|---:|
| Exact queued occurrence and selected fields against the pinned 2019Q4 `SUBMISSION.tsv` | 47/47 |
| Original SEC submission/header accession and form agree with queue | 47/47 |
| Original header filing date agrees with queue | 47/47 |
| Header issuer CIK and name agree with queue | 47/47 |
| XML issuer CIK, name and ticker agree with queue | 47/47 |
| Original header and XML issuer CIK agree | 47/47 |
| Acceptance clock precedes January 1, 2020 | 47/47 |
| Form 3 / Form 4 / Form 4 amendment | 11 / 35 / 1 |
| Reporting-owner role occurrences preserved | 65 |
| Retrieval or structural errors | 0 |

The supplied queue came from an earlier cohort check of missing or unsupported
current-header CIK cases. It selected the earliest globally unique earlier
filing per security, with accession and source-record tie breaks. This audit
checked the **exact 47 supplied public source occurrences**; it did not reread
vendor records or independently rebuild the cohort or uniqueness selection.
The original bulk source, schema and limits are described in the
[public-source note](public_historical_identity_sources.md).

### Issuer and reporting-owner roles

The original headers contain 47 `ISSUER` roles and 65 `REPORTING-OWNER`
occurrences. Forty-three filings have one reporting owner; the other four have
two, five, seven and eight owners. All occurrences remain separate. None of the
observed reporting-owner CIKs equals that filing's issuer CIK, and none was used
in place of the issuer. The archive-directory CIK and accession prefix served
only to locate the original submission; the fields inside it supplied the
identity evidence.

For example, the
[Communications Systems filing](https://www.sec.gov/Archives/edgar/data/22701/000161559419000040/0001615594-19-000040.txt)
has original issuer CIK `0000022701`, issuer name `COMMUNICATIONS SYSTEMS INC`,
and XML symbol `JCS`. The
[Glatfelter filing](https://www.sec.gov/Archives/edgar/data/41719/000112760219032211/0001127602-19-032211.txt)
reports issuer CIK `0000041719`, name `GLATFELTER P H CO`, and symbol `GLT`.
These observations retain their own accession, clock and reporting-owner roles.

### Bounded XML reading

The collector preserved complete original submission text. The inspector reads
header metadata and the XML prefix ending at the single direct `issuer` element
of `ownershipDocument`. It checks the primary document's original form,
filename and sequence wrapper, then reads issuer CIK/name/symbol, document type,
and the separately labeled report and original-submission dates.

The XML parser receives no reporting-owner, transaction, holdings, footnote,
remarks or signature section. Other document bodies are not parsed. This is
not a claim of full XML validity or analysis of the remaining ownership content.
Raw XML byte slices and entity-decoded field text remain distinguishable. All
47 CIK literals already use the queue's ten-digit padding; no literal CIK,
name or symbol difference needed resolution.

## Timing remains evidence, not historical availability

The observed acceptance clocks range from **October 1 to December 23, 2019**.
They are interpreted in `America/New_York`, retaining the applicable UTC offset.
Report dates, filing dates and change dates are recorded separately.

The retained
[Neuralstem Form 4/A](https://www.sec.gov/Archives/edgar/data/1357459/000117184319006480/0001171843-19-006480.txt)
illustrates the difference: its acceptance is **October 11, 2019, 19:23:53
Eastern**, its reported period is **July 1, 2019**, and its stated original
submission date is **July 3, 2019**. The amendment was not removed or reassigned
to either earlier date.

As explained by the [SEC timestamp guidance](https://www.sec.gov/about/webmaster-frequently-asked-questions),
these recorded clocks do not establish first website availability. HTTP dates
and the 2026 retrieval clock describe the preserved copy. Earlier acceptance
alone does not prove historical `known_at`, continuous security-link validity,
or the applicability of the retrieved bytes at a selection cutoff.

## Reproducibility and remaining work

Originals, queue, per-file attempts, receipts and the collection receipt are in
`outputs/ownership-originals-20261011/`. The public ledger binds the ignored
collector and inspector scripts by path and SHA-256. A separate verifier
rehashed all 47 originals, checked **676 exact field byte anchors**, independently
parsed all 47 isolated issuer fragments, and checked all 65 reporting-owner
roles. Its successful receipt is
`outputs/ownership-originals-20261011/independent_verification.json`.

Where those preserved files exist, rerun the independent check with a new
output path:

```bash
python outputs/verify_ownership_originals_47_20261011.py \
  --output outputs/ownership-originals-20261011/reverification.json
```

The collector is `outputs/collect_ownership_originals_47_20261011.py`; the
prefix inspector is `outputs/inspect_ownership_originals_47_20261011.py`.
The collector first requires the pinned queue and existing `SUBMISSION.tsv`,
checks source-row lineage, and uses two workers with at least 0.6 seconds between
request starts. It does not replace conflicting saved bytes or bypass access
errors. The inspector writes a new report and refuses an existing output.

These originals support the next source-bound candidate comparison. They do
not supply a CUSIP or class decision, a vendor security identifier, effective
link bounds, or source-release/availability evidence. All 47 observations keep
`known_at`, `available_at` and link bounds null. Approved historical links,
source approvals and human reviews remain zero; `model_ready` remains false.
No vendor rows, market returns or final-period sources were opened in this audit.
