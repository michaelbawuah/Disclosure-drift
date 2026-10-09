# Resolving indirect risk disclosures

This checkpoint handles 14 known development-period cases with explicit boundary
rules. It does not claim a general-purpose parser or completed human review.
The cases were selected because the original parser flagged them, before any
market returns or forecast scores were used.

| Source format | Registered cases | Boundary policy |
|---|---:|---|
| GE, filings 2015-2021 | 7 | Substantive Risk Factors body through the next Legal Proceedings heading |
| Intel, filings 2018-2019 | 2 | Substantive Risk Factors body through Non-GAAP Financial Measures |
| Intel, filings 2020-2021 | 2 | Substantive Risk Factors body through Properties |
| J&J, filings 2014-2016 | 3 | Body of the incorporated Exhibit 99, after its title through the exhibit end |

GE and Intel's numbered Item 1A entries point to printed pages. Some lack usable
hyperlinks. A page range can also contain the start of the following section.
Each registered rule therefore uses inspected section boundaries, not every word
on those pages or an unconstrained search for the phrase Risk Factors.

## What a rule verifies

`configs/section_resolutions.json` records the original primary URL and byte hash,
the hash of its short Item 1A pointer, the actual risk-source URL and byte hash,
character offsets in the versioned normalized source, text hash, token count and
boundary rationale. The rules were proposed by the assistant. They are extraction
instructions, not authenticated reviewer approvals.

A registered rule applies only to an unchanged, non-substantive numbered Item 1A
reference. It cannot replace a substantive section accepted by the original parser.
Changes to a source, reference, range, normalizer or expected text stop reproduction
and require investigation. Unregistered documents use the existing conservative
numbered-section parser and retain its failure flags.

For an exhibit, the resolver additionally verifies the original accession's SEC
document index, its hash, and a unique EX-99 document entry. The exhibit must be an
HTML file in that same accession directory. Other issuers, later accessions,
unrelated domains, wrong exhibit types and ambiguous index entries are rejected.
This checkpoint does not resolve EX-13, arbitrary external annual reports or PDFs.

The extracted J&J text includes the exhibit's introductory caution, listed risks
and closing qualification, because Item 1A incorporates that document. It excludes
SEC document metadata and repeated titles. GE and Intel ranges exclude the next
substantive section. Internal page furniture is retained under the unchanged
normalizer; this is a known text-quality limitation for later diagnostics.

## Timing and annual pairs

The original filing's SGML acceptance header continues to determine all event
dates. The exhibit does not introduce a new acceptance date. Index membership does
not independently establish the exact time of public dissemination; the declared
second-session proxy and human timing review remain in place.

The filing table records the actual risk-source URL separately from the primary
filing URL. Annual pairs retain both years' source methods and flag a method change.
Such a transition is a review concern, not automatically an economic signal. It is
not a new predictor or an alteration of the frozen primary model.

The offline audit rechecks the sources, index membership, extraction and event
dates. Review fingerprints include the rule, source hashes and range. Changing
the rule invalidates an earlier review. The audit also verifies paired texts and
source metadata against the filing table and rejects skipped or ineligible prior
annual filings.

## Rebuild the targeted comparison

Set an identifying `SEC_USER_AGENT` as described in the README, then run:

```bash
make reference-reproduce
```

This command rebuilds a baseline with `--no-resolutions`, applies the registered
rules to the same three issuers' 2014-2021 filings, builds the offline audit packet,
and runs `scripts/verify_reference_pilot.py`. The verifier compares all primary and
header hashes and baseline text hashes with the published milestone 02 manifest.
It also requires unchanged dates and unchanged text in the ten control filings.

Outputs include `outputs/reference_verification.json`,
`outputs/audit-references/audit.html`, a review template, source evidence and the
annual-pair review sample. Source data remain under ignored `data/` directories.
Unknown SEC/network failures remain visible; forbidden responses are not retried.

This command retains the targeted 24-filing regression sample. The subsequent
[milestone 04](../reports/MILESTONE_04.md) also verifies the complete 155-filing pilot
with `make pilot-resolved-reproduce`. Review all 21 targeted annual pairs, especially the
method transitions, before using the resolved texts in a prepared research table.
Human review, historical market data, development selection and the final test's
other prerequisites remain pending.
