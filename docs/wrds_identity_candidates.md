# Annual Names/CCM identity-candidate evidence

This offline consumer organizes the saved Names snapshots and complete CCM
inventory into a private evidence bundle for the frozen **2010–2021** annual
selections. It can also compare the recorded public SEC pilot filing manifest
with CCM company-header CIKs. It creates **no approved historical identity
links**, CIK history, universe membership, market outcomes, or availability
timestamps. The completed 20/20 arithmetic and timing review is unchanged.

The purpose is concrete: enumerate every plausible or unresolved relationship,
retain conflicting and unmatched evidence, and identify which historical source
facts are still missing. It does not resolve those missing facts by choosing a
current header identifier.

## Run locally after both upstream bundles succeed

From the repository root on the Mac containing the preserved sources:

```bash
uv run --locked --python 3.12 python scripts/wrds_manual_identity_candidates.py \
  --ccm-inventory data/private/wrds-intake/ccm-v2 \
  --listing-candidates data/private/wrds-listing-candidates/development-v1 \
  --sec-manifest reports/pilot_expansion/filing_sources.csv \
  --output data/private/wrds-identity-candidates/development-v1
```

The SEC manifest is optional. Omit `--sec-manifest` for Names/CCM evidence alone.
`--protocol` defaults to `configs/protocol.json`; the frozen lock must verify.
There is no year override. Use a new output directory under `data/` or
`outputs/`; the command refuses to overwrite an existing bundle or place its
output inside either input bundle. It reads no original daily files, returns,
prices, model outcomes, or final-period security selections. It makes no network
requests, executes no saved vendor query, and sends no correspondence.

The CLI prints aggregate counts, headers, source hashes, and fixed status labels.
Raw security identifiers, CIKs, company text, vendor URLs, local input paths,
and SEC accession values stay out of that summary. On failure it prints only
the exception category and an unapproved failure status. Detailed files are
private: directories have mode `0700`, finished files mode `0400`.

## Inputs and integrity checks

The Names input must satisfy the exact supported
[annual listing-candidate contract](wrds_listing_candidates.md): its frozen
policy, Parquet schema, annual counts, source-inventory receipt, source hashes,
and part hashes are checked. A complete date/provenance pass verifies every
snapshot's January 1 selection date, preceding-close information cutoff,
inclusive SecInfo interval, source CSV ordinal, and null `known_at`. The
classification diagnostics are recomputed, and SQLite checks the actual
per-security/year occurrence and distinct-projection counts against the Names
ambiguity declarations. No original Names CSV is reopened.

The CCM input must be a successful, unapproved metadata inventory with all
12 required fields: `gvkey`, `liid`, `linkprim`, `linktype`, `lpermno`, `lpermco`,
`linkdt`, `linkenddt`, `cik`, `conm`, `tic`, and `cusip`. Extra delivered columns
are allowed under the existing metadata inventory contract. The complete
preserved CSV or gzip stream is read; compression is recognized by signature.
The actual source hash and size, exact delivered header, record widths, source
row count, every column's blank/nonblank counts, interval classifications, and
date-bound counts/extrema must agree with the inventory receipt. Duplicate or
unsafe headers are rejected by the shared metadata parser.

The complete CCM date-bound pass and the complete Names date/provenance pass
finish before any identity matching. The tool preserves raw future metadata
as context without creating a final-period selection or inferring historical
knowledge. It rechecks input identities and hashes before publication, hashes
every output part, and copies the small input receipts exactly. The full CCM
CSV stays byte-for-byte in its original inventory, so its extra company and
contact fields are not needlessly copied into a new joined table. The full
Names Parquet parts are copied byte-for-byte as private evidence.

## Identifier comparisons are explicit search keys

Original strings are always retained. The consumer derives a comparison key
only for **nonzero ASCII digit strings** of 1–20 characters for PERMNO/PERMCO,
or 1–10 characters for a CIK. Security comparison keys remove leading zeros;
CIK comparison keys use ten-digit padding. The relationships distinguish exact
raw-text equality from equality obtained solely by leading-zero comparison.

Blank and whitespace-only strings, all-zero strings, whitespace-padded values,
signs, decimal/scientific notation, non-ASCII digits, and oversized values never
supply a comparison key. They remain in the source/detail accounting. This
grammar check does not certify a vendor identifier, normalize an approved
table, or infer identity from a company name, ticker, CUSIP, or accession prefix.
Multiple raw Names IDs sharing one comparison key are explicitly counted and
make the annual identity evidence ambiguous.

## Every related CCM occurrence is retained

For each preserved Names record/year, the tool enumerates all CCM records with
the same valid PERMNO comparison key. It applies no LINKTYPE, LINKPRIM, LIID,
share-class, ordinary-stock, or company filter. The Names ordinary-candidate
status and PERMCO agreement are diagnostics; neither chooses an issuer or
accepts a security mapping.

January 1 is the selection date. The preceding XNYS close is recorded as the
information cutoff, but it never becomes `known_at` or `available_at`.

| CCM date relationship | January 1 candidate search | Treatment |
|---|---:|---|
| Both finite, nonreversed bounds include January 1 | Yes | Inclusive dated-link candidate evidence only. |
| A finite start is later than January 1 | No | Retained as `AFTER_SELECTION_CONTEXT`, even if the other bound is open or blank. |
| A finite end is earlier than January 1 | No | Retained as `BEFORE_SELECTION_CONTEXT`, even if the other bound is open or blank. |
| Two finite bounds are reversed | No | Retained as `REVERSED_FINITE_CONTEXT`. |
| A literal `B` or `E` occurs and no finite bound contradicts January 1 | Unresolved possibility | Retained as an open-marker search candidate; the marker is not replaced by a date or infinity. |
| Blank, malformed, or other bounds with no finite contradiction | Unresolved possibility | Retained in a separate unresolved-bound search category. |

A future-only relationship cannot promote a January 1 candidate. An unresolved
interval is a search possibility, not evidence of effective validity. Full
source occurrences are preserved even when identical. Annual counts separate
the number of Names×CCM pairs from the number of distinct source-record
ordinals; duplicates do not become one accepted mapping. Names exact duplicate
counts compare all 24 raw canonical fields, while CCM full-row fingerprints
cover the complete delivered row. No fingerprint is used to deduplicate or
silently collapse classes.

## Optional SEC discovery and its limits

The supported SEC input is the exact `filing_sources.csv` schema used by the
public pilot expansion. Its bytes are copied and hashed. The parser checks
record width, unique accession syntax, positive ASCII filer CIKs, explicit
timezone-aware recorded acceptance timestamps, agreement with the recorded
New York acceptance date, official HTTPS SEC archive URL syntax, and the
syntax of the recorded source/header/risk hashes. An out-of-development filing
is refused before either vendor input is opened. Header-only manifests remain
valid zero-record evidence.

Discovery requires the manifest's acceptance year to equal the Names snapshot
year and its filer CIK comparison key to equal a **current CCM company-header
CIK** among the January 1 search candidates. Every such match is retained,
including ambiguous alternatives. The private discovery row also reports
whether finite CCM bounds contradict the filing's recorded acceptance date and
whether the actual Names SecInfo interval covers that date. These diagnostics
never stretch a January 1 attribute through the security's lifetime.

`ccm_date_compatible_at_acceptance=true` means the same conservative search test
found no finite contradiction; an open or unparsed bound remains unresolved in
`ccm_relation_at_acceptance`. It does not certify effective identity at the
filing date. Every manifest row receives coverage accounting, including filings
with no Names year, no candidate, an earlier/predecessor CIK, or only a future
CCM relationship. Absence of a match is not a final exclusion.

**Original SEC filing and header bytes are not reread.** Source hashes in the
manifest are recorded declarations, not hashes recomputed from those original
documents. The packet records `original_sec_bytes_reread=false` and
`recorded_source_hashes_verified_against_original_bytes=false`. A same-year
header-CIK agreement is discovery evidence only; it does not verify a historical
security/issuer relationship. Recorded SEC acceptance timestamps never fill
link availability fields. This consumer does not alter the separate permitted
filing-availability proxy described in the existing research contract.

## Private output contract

`receipt.json` has status
`ANNUAL_MANUAL_WRDS_IDENTITY_EVIDENCE_NOT_SOURCE_APPROVED`. Its `tables` object
lists each table's part paths, SHA-256 hashes, byte counts, and row counts.

| Table/directory | Retained evidence |
|---|---|
| `ccm_records` | Every original CCM record's required 12 raw fields, syntax/comparison keys, raw-bound diagnostics, and SHA-256 fingerprint of the entire parsed delivered row in original column order. Includes blank/unresolved PERMNO rows. |
| `names_evidence` | Exact upstream Names Parquet bytes, including all 24 raw fields, overlaps, classification diagnostics, and source provenance. |
| `relationships` | Every related Names-record/year×CCM-record pair, raw link IDs/flags/bounds/header CIK, exact-vs-leading-zero comparison, date relationship, and explicit `candidate_search` flag. |
| `annual_evidence` | Every raw Names PERMNO/year, including unmatched records; candidate/context counts, Names overlap counts, distinct raw GVKEY/header-CIK counts, PERMCO diagnostics, and SEC discovery counts. |
| `sec_discovery` | All same-year header-CIK discovery pairs with both vendor source ordinals, manifest ordinal, accession, raw/comparison CIKs, and acceptance-date interval diagnostics. |
| `sec_manifest_coverage` | Every supplied manifest row, with discovery multiplicity, distinct raw Names IDs/CCM source records, or an explicit unmatched status. |
| `input_receipts` | Exact CCM inventory, Names candidate, Names inventory receipts, and optional SEC manifest snapshot. |

CCM and Names provenance includes the original source SHA-256, source-inventory
receipt SHA-256, and CSV **record ordinal**, with the header as record 1. A
quoted multiline cell does not increment the record ordinal more than once.
Empty computed tables still have a schema-bearing zero-row Parquet part.
SQLite indexing, file-backed temporary storage, and bounded Arrow output
batches avoid an all-row in-memory join.

Every newly derived row leaves `known_at` and `available_at` null and
`identity_approved=false`. The receipt keeps `model_ready=false`,
`source_approvals=0`, `approved_security_links_created=0`,
`historical_cik_supplied=false`, `historical_availability_supplied=false`, and
`final_period_opened=false`. Existing source approvals and the completed user
arithmetic review are not modified.

## What would resolve the historical-header shortfall

The strict [historical dataset contract](historical_dataset.md) needs historical
CIK/link validity and availability evidence; current company headers alone do
not satisfy it. The public CRSP Company History dictionary documents `HCIK`
with `HCHGDT`/`HCHGENDDT`, `GVKEY`, and linked security fields. This is a source
lead, not evidence that its data, access entitlement, WRDS schema, coverage,
release, or historical availability have been obtained. See the primary-source
research and access boundaries in
[historical identity access evidence](historical_identity_access_evidence.md)
and [CRSP's Company History dictionary](https://www.crsp.org/wp-content/uploads/ccm_files/CompanyHistory.html).

When authorized historical identity evidence arrives, this packet supplies
the preserved candidate relationships and unresolved cases to reconcile. Its
outputs must not be renamed or copied into approved `identity_links` or
universe inputs without that separate source work and the applicable review.
