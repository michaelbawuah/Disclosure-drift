# Ownership-form issuer observations for the complete 2020 candidate cohort

This consumer connects the saved public 2019 Q4 SEC ownership-form metadata to
complete dated Names descriptors for every 2020 annual foundation observation
already marked rank-eligible by the provisional candidate policy. It compares
all resulting issuer observations with every original CCM relationship for that
cohort. It does not select 500 issuers, change eligibility, approve identities,
or infer historical availability.

## Inputs and execution

The required inputs are the completed historical foundation, its original
identity evidence bundle, the original Names inventory, the public source
ledger, the original public collection receipt, and the exact `SUBMISSION.tsv`.
Explicit pins bind the foundation, identity, Names inventory and public ledger;
the pinned ledger binds the collection receipt and TSV. The cohort year is
fixed to 2020 and the permitted SEC filing-date quarter is October–December 2019.

```bash
uv run --locked --python 3.12 python scripts/reconcile_sec_ownership.py \
  --foundation data/private/historical-foundation/development-v1 \
  --foundation-receipt-sha256 <actual-foundation-receipt-sha256> \
  --identity <original-private-identity-directory> \
  --identity-receipt-sha256 <actual-identity-receipt-sha256> \
  --names-inventory data/private/wrds-intake/names-v2 \
  --names-receipt-sha256 <actual-names-inventory-receipt-sha256> \
  --sec-submission data/private/public-source-preservation/2026-10-11/sec/2019q4_SUBMISSION.tsv \
  --sec-ledger reports/public_historical_identity_sources.json \
  --sec-ledger-sha256 <actual-public-ledger-sha256> \
  --sec-collection-receipt <original-public-collection-receipt.json> \
  --output <new-private-output-directory>
```

The placeholders require actual receipt hashes and paths. The output directory
must be new and private. Source hashes, schemas, complete source dates and
upstream relationships are checked; consumed files are checked again before
the immutable output bundle is published. Failure prints an aggregate error
type without exposing private source rows or paths.

## Matching and clock rules

All 13 delivered SEC fields and every original occurrence are retained, including
amendments, duplicate accessions, placeholder symbols, malformed report-period
literals and remarks. Only `FILING_DATE` determines the observed filing day.
Neither `PERIOD_OF_REPORT` nor `DATE_OF_ORIG_SUB` supplies an availability date.

The information cutoff comes from the frozen final XNYS close before selection.
A filing date strictly before its calendar day is an earlier reported filing-date
observation. A filing on the cutoff day has an unresolved clock and never enters
the earlier-date corroboration totals. The later quarterly extract and current
retrieval do not establish first website availability for either category.

Matching uses exact SEC symbol equality to Names `ticker` or `tradingsymbol`
at inclusive SecInfo dates. Both field hits are retained in one SEC/Names
occurrence relationship. Case, punctuation and combined symbols are not repaired.
Explicit placeholder phrases and combined or spaced literals receive unresolved
flags. Case folding is used only to flag placeholders; it never creates a match.

Collision checks include every matching record from the complete Names source,
including securities outside the cohort. All contemporaneous descriptors for
the same PERMNO comparison key are also checked, even if a second overlapping
descriptor has a different ticker. Duplicate occurrences, overlapping records
and raw identifier aliases therefore remain ambiguous. A security lifetime is
a diagnostic and never extends a descriptor interval.

The original annual Names values must match their complete-source CSV
occurrences exactly. The existing identity validator checks all original CCM
relationships. Comparisons retain current-header CIK agreement, disagreement,
unsupported values, context-only records and missing relationships. No matching
candidate is chosen from an ambiguous set. Repeated filings never vote to resolve
issuer identity.

## Private outputs and useful next evidence

| Table | Retained evidence |
|---|---|
| `cohort` | Every original 2020 rank-eligible annual foundation row |
| `sec_occurrences` | Every original SEC metadata occurrence and source ordinal |
| `names_records` | Required cohort descriptors and all collision/overlap context |
| `original_relationships`, `ccm_records` | All original cohort relationships and their source occurrences |
| `observations` | Literal issuer/symbol/Names observations at reported filing dates |
| `header_comparisons` | Every corresponding original CCM header comparison |
| `cohort_summary` | One result per cohort security, including unmatched cases |
| `original_source_followup` | Original XML/header requests and explicit no-observation placeholders |

The exact TSV and input receipts are preserved in the bundle. The public
aggregate contains counts, source hashes, declared rules and a cross-tabulation
of existing identity status, observation status and header comparisons. It
contains no vendor identifiers or raw rows. Counts of agreements and
disagreements can overlap when a security has multiple candidate relationships.
An earlier candidate-header disagreement means at least one pairwise comparison
differs; it does not mean the observed issuer is absent from the entire usable
candidate set. Those header-comparison totals use unambiguous earlier literal
observations only. In contrast, the multiple-earlier-issuer-key count preserves
keys from all earlier observations, including ambiguous descriptor matches.
It is not a count restricted to globally unique earlier observations.

The follow-up queue prioritizes missing/unsupported current-header identity,
conflicting issuer observations, descriptor ambiguity and cutoff-day clock
questions. It names source accessions without inventing archive URLs or
substituting the reporting owner's CIK for the issuer. Unmatched cohort members
remain explicit requests for earlier original issuer evidence.

These are dated observations, not continuous CIK-to-security intervals. A Names
record covering both filing and selection does not extend the filing's issuer
observation to selection. Absence from one quarter's ownership extract never
excludes a security. All historical availability fields remain null, and the
consumer creates no source approvals, human reviews, empirical dataset or
final-period access. See the [public source evidence](public_historical_identity_sources.md)
and [historical dataset contract](historical_dataset.md).
