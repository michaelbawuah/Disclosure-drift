# Historical identity review

`review-identities` puts the existing SEC, CCM and dated Names evidence together
for each development filing event. The outputs remain private because they contain
licensed source records. The command loads no daily returns and creates no approved
security links, labels or modeling data.

```bash
uv run disclosure review-identities \
  --events data/processed/pilot-resolved/label_events.parquet \
  --filings data/processed/pilot-resolved/filings.parquet \
  --audit outputs/audit-pilot-resolved \
  --ccm data/raw/wrds/2026-10-09/crsp_ccm_pilot.csv \
        data/raw/wrds/2026-10-09/crsp_ccm_xom.csv \
  --names data/raw/wrds/2026-10-09/crsp_names_pilot.csv \
  --output data/reviews/identity-pilot-v2
```

The default company configuration is `configs/pilot_companies.json`, and cached
SEC headers are read from `data/raw/sec_cache`. Use a new output directory for
another run. Preserve the original files and the filing table's sibling
`filing_pairs.parquet`; both must match the existing source audit.

## What the packet checks

1. Reject final-period events before opening vendor sources. Verify the event's
   current and previous accessions against the audited annual pair, the original
   filing CIKs, acceptance timestamp and source-evidence fingerprints.
2. Recheck each cached SEC header's URL and byte hash, then its original filer CIK,
   company name, accession and form. A missing, changed or ambiguous header remains
   a visible issue. A header confirms the SEC filer, not its PERMNO.
3. Find candidate CCM records using the original CIK and any explicitly configured
   discovery CIK. Preserve both identities separately. Never join on ticker or
   automatically select the first security or a particular share class/link type.
4. Compare each candidate with dated Names records for every required session:
   60 control sessions, the reference session and 20 label sessions. Show missing
   or overlapping descriptions, PERMCO disagreement and explicit link-boundary gaps.

Literal CCM `E` end markers remain unchanged and flagged for dictionary/extract-end
review. They allow a record into the **candidate search**, not an approved historical
interval. CCM dates describe a GVKEY/security link; they do not turn header CIKs into
dated CIK histories. Names records and header identifiers are retrospective evidence,
not proof of point-in-time availability. Out-of-period identifier metadata does not
open final-period filing events or returns.

## Outputs and review

Open `identity_review.html` to see each event's SEC links, both filer identities,
CCM candidates and dated security descriptions. The five Parquet tables preserve
the event queue, candidate links, header evidence and relevant CCM/Names fields.
Source references use one-based CSV record numbers including the header, not
physical line numbers inside quoted multiline fields.

`identity_reviews.template.jsonl` contains pending records bound to the input
hashes, computed evidence, protocol and review code. A reviewer must inspect the
registered security in the original filing, establish historical CIK/security
continuity, resolve open dates and class selection, and record source references,
the supported validity interval, reviewer identity and notes. Filling the template
does not import a mapping: this command has no approval or review-ingestion mode.
The later normalized import still requires independently established links.

This packet supplements the separate 30-pair filing review and 20-event arithmetic
review. It does not mark either complete. Hashes bind evidence; they are not an
independent source certification or a human signature.

## Pilot result on 10 October 2026

The packet covers 135 events across 20 issuers and rechecks 155 original SEC
headers, all identity-consistent. Each event has one candidate security, and all
10,935 required session checks have exactly one dated Names record with matching
PERMCO. This is coverage evidence, not approval.

Seven Exxon events retain the original filing CIK and explicitly flag the different
CCM header CIK. The [corporate-source follow-up](identity_source_evidence.md)
documents the July 2026 reorganization and both CIKs; historical-link approval
remains pending for all 135 events. WRDS documentation supports an open-ended
interpretation of `E`, but export-specific normalization bounds and all verdicts remain
pending. No approved mapping, actual label or empirical result was produced.

The later [arithmetic audit](pilot_arithmetic_review.md) calculates conditional
labels and controls for the 135 candidates and verifies raw-source arithmetic.
It retains all identity verdicts as pending, including seven header-CIK differences
and 135 open-end markers. It creates no approved mapping or empirical forecast result.

The public [aggregate receipt](../reports/identity_pilot_summary.json) contains
counts and hashes only. Raw records and the detailed HTML stay outside public git.
