# Milestone 02: filing audit and expanded parser pilot

Completed 9 October 2026. The public-source engineering checkpoint is implemented;
human filing review and the empirical study remain pending.

## Measured coverage

| Check | Result |
|---|---|
| Selected issuers | 20 |
| Original annual filings, filing years 2014–2021 | 155 |
| Filings passing automatic source/extraction/timing consistency | 141 |
| Filings requiring review | 14 |
| Annual pairs ready for manual review | 121 |
| Issuers with an eligible pair | 19 |
| Pairs selected for the initial review sample | 30 |
| API/header timestamp disagreements retained | 72 |
| Completed human reviews | 0 |

The 20 companies are purposive document-format cases. Current ticker discovery
does not establish historical investment eligibility. The XOM discovery CIK was
corrected to its previously verified historical filing CIK. The first run used
the uncorrected in-memory config; both run summaries are retained in the
[verification record](milestone_02.json). Disney's newer CIK remains separate from
its predecessor, so its earlier years are absent rather than silently spliced.

The [filing manifest](pilot_filing_manifest.csv) records source URLs, hashes and
dates without publishing the full extracted texts. See [issuer coverage](pilot_coverage.csv)
and the [30-pair review sample](pilot_review_pairs.csv). The sample covers issuers
first, then uses a fixed seeded hash; it is not a population accuracy estimate.
GE has no eligible annual pair in this pilot. The 15
pair exclusions also include Disney's first observed filing without a predecessor.

## Flagged source evidence

| Issuer | Filing date | Extracted tokens | Automated issue |
|---|---|---:|---|
| GENERAL ELECTRIC CO | 2015-02-27 | 0 | extraction_requires_review |
| GENERAL ELECTRIC CO | 2016-02-26 | 0 | extraction_requires_review |
| GENERAL ELECTRIC CO | 2017-02-24 | 0 | extraction_requires_review |
| GENERAL ELECTRIC CO | 2018-02-23 | 0 | extraction_requires_review |
| GENERAL ELECTRIC CO | 2019-02-26 | 0 | extraction_requires_review |
| GENERAL ELECTRIC CO | 2020-02-24 | 0 | extraction_requires_review |
| GENERAL ELECTRIC CO | 2021-02-12 | 0 | extraction_requires_review |
| INTEL CORP | 2018-02-16 | 1 | extraction_requires_review |
| INTEL CORP | 2019-02-01 | 1 | extraction_requires_review |
| INTEL CORP | 2020-01-24 | 1 | extraction_requires_review |
| INTEL CORP | 2021-01-22 | 1 | extraction_requires_review |
| JOHNSON & JOHNSON | 2014-02-21 | 34 | extraction_requires_review |
| JOHNSON & JOHNSON | 2015-02-24 | 80 | extraction_requires_review |
| JOHNSON & JOHNSON | 2016-02-24 | 78 | extraction_requires_review |

Johnson & Johnson's 2014–2016 main-document sections refer readers to Exhibit 99.
Those short sections are not evidence of disappearing economic risk. A future
exhibit-resolution policy must identify and preserve the additional source before
these years can enter comparable text features. Pairs depending on flagged
sections are excluded; the pipeline does not skip a failed prior year.

Intel's 2018–2021 and GE's 2015–2021 numbered Item 1A entries contain page references.
The current extractor returns those short index entries and flags them. Inspection
of representative sources located earlier risk discussions; their alternate
boundaries still require a source-aware resolver and review. These are parser
coverage failures, not evidence that the companies omitted their risk disclosures.

The audit command deliberately exits nonzero while blockers remain and still
writes the evidence packet. Re-extracting the same source and verifying hashes
does not prove that section boundaries are correct. Human review remains pending.
API/header differences and unverified public dissemination remain explicit; the
frozen second-session timing proxy has not changed.

## Reproduction and execution

The tested code is commit `10cbc067748e2a931aac1ff311785dc03618405c`.
`make reproduce` passed lint, 49 tests, protocol verification and the synthetic
demo in the cloud, on the owner's macOS arm64 machine, and in
[GitHub Actions](https://github.com/michaelbawuah/Disclosure-drift/actions/runs/37991704378).
Cloud and Mac checks used Python 3.12.14; GitHub Actions used Python 3.12.3.
Four upstream calendar/NumPy deprecation warnings remain in each run.

The owner's Mac clone is connected and runnable. Its separate SEC smoke download
received HTTP 403 for all five submission-history requests and retrieved no
filings. Forbidden responses were not retried. This pilot's live-source evidence
comes from the successful cloud download, not from a successful Mac data download.

With an identifying `SEC_USER_AGENT` and working SEC access, run:

```bash
make pilot-ingest
make pilot-audit
```

The second command writes `outputs/audit-pilot/audit.html`, an evidence table,
coverage summaries and a pending review template. See the
[audit workflow](../docs/filing_audit.md) for recording fingerprinted reviews.

## Remaining research gates

1. Review the selected pairs and all flagged documents; resolve exhibit handling.
2. Verify historical market-data access and its actual export dictionary, including
   dated identities, inactive securities and delisting conventions.
3. Construct the historical universe and audited market/control joins; run the real
   development comparisons and freeze their selections.
4. Specify and audit the semantic model's chronology before opening the final test.

No real market returns were loaded. The 2022–2025 final evaluation remains closed.
There is no claim of predictive performance or completion of the empirical study.
