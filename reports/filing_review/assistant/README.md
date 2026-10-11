# Assistant filing review completed — October 11, 2026

The saved review packet now has **73 completed assistant boundary/timing records**.
Michael Baffour Awuah authorized the assistant to perform the work on his behalf.
The [readable results page](index.html) shows every recorded judgment, its author,
its original time, and its SEC sources. No action from Michael is needed to finish
this assistant filing-review checkpoint.

## Verified result

| Check | Result | Evidence |
|---|---:|---|
| Packet coverage | **73 / 73 assistant reviews** | [Recorded decisions](reviews.jsonl) |
| Earlier assistant decisions preserved | **63 / 63** | [Prior-binding and timing evidence](evidence/timing_prior_evidence.json) |
| New source inspections | **10 / 10 boundary passes** | [GE / Intel findings](evidence/ge_intel_findings.json); [JNJ findings](evidence/jnj_findings.json) |
| Independent original-header clocks and session windows | **73 / 73 pass** | [Independent timing evidence](evidence/timing_prior_evidence.json) |
| Fixed-pair identity, chronology and cohort predecessor relationships | **30 / 30 pass** | Same timing evidence; predecessor completeness is limited to the saved cohort |
| Distinct selected original SEC bodies and cache metadata rehashed | **152** | Same timing evidence |
| Authoritative source audit of the complete original cohort | **155 / 155 consistent; zero blocking issues** | [Audit summary](audit_summary.json); [actual execution](execution.json) |
| Evidence identities and fixed sample after the source audit | **155 unchanged IDs; byte-identical 30-pair selection** | [Actual execution](execution.json) |

The declared-review validator accepted all 73 records. Its
[validation result](validation.json) correctly says it does not itself reread SEC
bytes. The **separate source audit did reread the original bytes**, re-extracted
the sections with the existing rules, and accepted all 73 assistant records. It
completed at `2026-10-11T09:55:36.521815+00:00` in 107.833 seconds.
The 72 API/header timestamp cautions across the entire 155-filing cohort remain
observations rather than blocking defects; 29 of them occur in this 73-filing
packet. No causal explanation for these differences is asserted.

## What was reviewed now, and what was preserved

The fixed 30 annual pairs contain 58 distinct filings. The reference template
contains 24 filings, nine shared with the fixed sample, producing the unchanged
73-filing union. Of these, **63 already had assistant source-bound judgments**.
Their eight audit fields, including the author, notes and timestamp
`2026-10-10T18:10:19.375935+00:00`, are retained exactly. The full original records
remain in [the earlier decision file](../../review_progress/assistant_filing_decisions.jsonl).
Their scope remains textual boundary-window inspection and header/session checks;
it has not been expanded retrospectively into a whole-document visual review.

The following ten additional filings were read from their original SEC source
text. Independent HTML-event or DOM-boundary inventories were compared with the
complete extracted sections. Filing years below are **filing dates**, not fiscal
period labels.

| Filing | Boundary / timing | Source finding |
|---|---|---|
| [GENERAL ELECTRIC CO — 2014](https://www.sec.gov/Archives/edgar/data/40545/000004055414000023/geform10k2013.htm) | Pass / pass | Complete substantive risk section; internal page labels remain and one terminal period is stripped. |
| [INTEL CORP — 2014](https://www.sec.gov/Archives/edgar/data/50863/000005086314000020/a10kdocument12282013.htm) | Pass / pass | Complete substantive risk section and page-break continuations; internal page/navigation text remains. |
| [INTEL CORP — 2015](https://www.sec.gov/Archives/edgar/data/50863/000005086315000015/a10kdocument12272014.htm) | Pass / pass | Complete substantive risk section and page-break continuations; internal page/navigation text remains. |
| [INTEL CORP — 2016](https://www.sec.gov/Archives/edgar/data/50863/000005086316000105/a10kdocument12262015q4.htm) | Pass / pass | Complete substantive risk section and page-break continuations; internal page/navigation text remains. |
| [INTEL CORP — 2017](https://www.sec.gov/Archives/edgar/data/50863/000005086317000012/a10kdocument12312016q4.htm) | Pass / pass | Complete substantive risk section and page-break continuations; internal page/navigation text remains. One terminal period is stripped. |
| [JOHNSON & JOHNSON — 2017](https://www.sec.gov/Archives/edgar/data/200406/000020040617000006/form10-k20170101.htm) | Pass / pass | Complete direct Item 1A, including page-break continuations, international-risk bullets and the final cybersecurity paragraph. |
| [JOHNSON & JOHNSON — 2018](https://www.sec.gov/Archives/edgar/data/200406/000020040618000005/form10-k20171231.htm) | Pass / pass | Complete direct Item 1A, including page-break continuations, international-risk bullets and the final cybersecurity paragraph. |
| [JOHNSON & JOHNSON — 2019](https://www.sec.gov/Archives/edgar/data/200406/000020040619000009/form10-k20181230.htm) | Pass / pass | Complete direct Item 1A, including page-break continuations, international-risk bullets and the final cybersecurity paragraph. |
| [JOHNSON & JOHNSON — 2020](https://www.sec.gov/Archives/edgar/data/200406/000020040620000010/form10-k20191229.htm) | Pass / pass | Complete direct Item 1A, including page-break continuations, international-risk bullets and the final cybersecurity paragraph. |
| [JOHNSON & JOHNSON — 2021](https://www.sec.gov/Archives/edgar/data/200406/000020040621000008/jnj-20210103.htm) | Pass / pass | Complete direct Item 1A, with an explicit caution about unspecified incorporated material. |

The GE/Intel review read 866 matched original text events; the JNJ review read
278 nonempty source nodes. These are counts from different parsing methods and
are not an interchangeable measure of paragraphs. The reviewers checked the
substantive headings, tables of contents, continuations, bullets, ending headings,
and cross-references. Internal page furniture remains under the unchanged
normalizer. GE 2014 and Intel 2017 each lose one terminal period, with no
substantive words or paragraphs missing in those inspected spans.

Johnson & Johnson 2021 uses a generic incorporated-by-reference phrase in its
COVID discussion. The entire paragraph and its page-break continuation are
present. No separate omitted risk exhibit is named there; concrete risk
cross-references point to same-document notes. The bounded direct Item 1A
extraction passes under the existing policy. **Unspecified incorporated material
is not certified.** See the preserved [incorporation context](evidence/jnj_2021_incorporation_context.json).

All 73 header clocks were independently recalculated from original SGML
acceptance digits and the locked XNYS calendar. The second exchange session
strictly after the New York acceptance date is the reference session; the
preceding session is the controls cutoff; the following 20 sessions are the
label window. The independent arithmetic shares the pipeline's calendar
dependency, so it does not independently validate the external calendar provider.
The 30-pair check establishes same-CIK chronology and predecessor adjacency
**within the preserved 155-filing cohort**. It does not establish predecessor
completeness across the historical issuer population.

Six original-header/display-name differences are documented: two Apple
capitalization differences and four Home Depot punctuation differences. Each
selected issuer CIK uniquely matches its original header. These observations
create no historical CIK-to-security approvals. Source bodies were read from the
hash-verified saved SEC cache; this was an offline source audit.

## Authorship and execution record

[Authorization](authorization.json) records Michael's delegation separately from
review authorship. All filing judgments are attributed to the assistant.
[Combined-review provenance](evidence/combined_review_provenance.json) preserves
the individual boundary-inspection times and independent timing-check time.
The ten combined judgments were recorded only after both checks had completed.
The previous 63 records keep their earlier times. No human filing decision has
been manufactured, and the user's completed 20/20 arithmetic/printed-timing
review retains its separate credit and unknown original timestamp.

The [source inspection archive](evidence/source_inspection_archive.tar.gz)
preserves all 39 original delegated inspection files at their original paths,
including the complete reading inventories, scripts and judgments. Its
[manifest](evidence/archive_manifest.json) lists every member's byte count and
SHA-256. The scripts in that archive document the historical execution; rerunning
an inventory does not perform or manufacture a new source judgment.

The [completion receipt](receipt.json) binds this bundle and its source inputs.
To verify it, copy its SHA-256 from the published completion record and run:

```bash
uv run --locked --python 3.12 python scripts/verify_assistant_filing_packet.py \
  --receipt-sha256 RECEIPT_SHA256
```

This default command validates the pinned records and source-table bindings.
An optional `--audit-output outputs/NEW_DIRECTORY` also reruns the original-byte
source audit and refuses an existing output directory. It needs the preserved
SEC cache and original processed tables. The receipt hash must come from the
published record; recalculating it from an untrusted modified receipt is not
an independent integrity check.

## Research work still open

This completes the **assistant review of this 73-filing packet**. It does not
complete the empirical forecasting study. Historical universe membership and
security links, point-in-time availability and vendor-vintage evidence, benchmark
resolution, remaining required judgments, development model selection, and final
empirical results still require their own evidence. The original whole-table
human `manual_audit` remains pending. The five later expansion cases and other
flagged filings retain their own scope. The actual 2022–2025 final period remains
unopened, and no market returns were read for this filing-review task.

The original [pending review form](../index.html), packet and generation receipt
are preserved unchanged. That form remains available for a separate personal
review; this completed page does not alter any saved browser draft.
