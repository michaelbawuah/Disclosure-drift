# Annual liquidity candidates from saved development sources

This consumer calculates the frozen annual liquidity statistic over saved,
unapproved numerical and Names candidate bundles. It produces private coverage
evidence and an observed-security ranking for **2010–2021**. Historical
availability, issuer identity, source conventions and population completeness
remain unresolved. The output creates zero source approvals and leaves the
completed 20/20 arithmetic review unchanged.

## Run locally

From the repository root:

```bash
uv run --locked --python 3.12 python scripts/wrds_manual_liquidity_candidates.py \
  --numerical-candidates data/private/wrds-candidates/development-v2 \
  --listing-candidates data/private/wrds-listing-candidates/development-v1 \
  --output data/private/wrds-liquidity-candidates/development-v1
```

`--protocol` optionally specifies the protocol JSON; its sibling lock and the
repository lock must verify. There is no year override. The command requires a
new private directory under `data/` or `outputs/`, separate from both inputs,
and refuses an existing output. Original multi-gigabyte CSVs are not reopened.

The Python API is:

```python
from disclosure_research.manual_wrds_liquidity_candidates import build_liquidity_candidates

receipt = build_liquidity_candidates(
    numerical_directory, listing_directory,
    output=new_private_directory, config=config, repo_root=".",
)
```

## Inputs and integrity

The inputs are the existing [numerical candidates](wrds_manual_candidates.md)
and [annual dated Names candidates](wrds_listing_candidates.md). The consumer
verifies their exact supported statuses, protocol, schemas, part hashes, row
counts, provenance and source-receipt snapshots. It validates the dates in
**every input part before reading liquidity values**, including parts whose
dates will not contribute to an annual window. Numerical dates must remain
inside their bound development request. Names snapshots are restricted to
2010–2021; their descriptive metadata may have later finite interval endpoints.

Numerical source references must identify an original bound source and a valid
CSV record ordinal. The upstream date/security ordering and actual number of
distinct projections must agree with their conflict declarations. Exact
projection repetitions already collapsed by the numerical consumer remain
represented by their original record counts. Names record ordinals must be
unique and ordered within each year, and every SecInfo interval must cover its
January 1 selection date. The consumer rechecks the supported Names candidate
policy and actual overlap groups.

Both input receipts and their bound source-receipt snapshots are copied exactly.
Input paths, identities and hashes are checked again before successful
completion. Private output hashes and snapshot bytes are also checked. The
completed bundle is published locally by an atomic directory rename; a failed
run has no successful output receipt or replacement of an existing bundle.

## Coverage and the mean

For each year, `year_start_window` supplies the exact preceding **60 XNYS
sessions**, January 1 selection date, first selection session and prior-year
closing information cutoff. The annual security population is the union of:

- Every PERMNO appearing in that year's Names snapshots, including ambiguous or
  scope-review records.
- Every raw security ID appearing in numerical candidates during those exact
  60 sessions.

Identifiers remain exact source strings. A future-only security cannot enter an
earlier year's union. Missing Names records, missing daily history, partial
requested coverage and calendar dates with no daily candidate remain explicit.

A session contributes a value only when it has one distinct projection,
`liquidity_status = CANDIDATE_REQUIRES_SOURCE_REVIEW`, supported raw positive
identifiers, a `TR` or `BA` price flag, and a finite, nonnegative delivered
`closing_price_volume_usd_candidate`. Other values remain withheld. The upstream
proxy is positive CIZ price times nonnegative raw volume, under the documented
[candidate source conventions](wrds_source_conventions.md). TR and BA counts
remain separate. A zero proxy is a recorded-zero-volume candidate under that
upstream positive-price policy; an absent session is never filled with zero.

The annual receipt and private table distinguish observed sessions, distinct
projection rows, represented original records, exact 13-field repetition
excess, unambiguous sessions, conflicting sessions, numerically valid sessions,
other withheld sessions, missing sessions and zero/TR/BA candidate counts.
Every conflicting security/session contributes **one conflicting session**,
regardless of its number of projections or agreement of price-volume fields.

The accounting identities are:

```text
valid sessions + other withheld sessions + conflicting sessions = observed sessions
observed sessions + missing sessions = 60
```

The minimum is 40 numerically valid sessions. Original repetition counts never
weight the mean or satisfy the minimum. The denominator is the number of valid
sessions, rather than 60. With no valid values, the mean is null.

For reproducibility, the tool sums the delivered IEEE 754 binary64 values as
exact rational numbers, divides by their count, and rounds once to binary64.
At most 60 values are held for a security. This avoids overflowing a finite
mean through an intermediate floating-point sum. It does not reconstruct the
original vendor decimal values. A positive exact mean rounded to zero is
reported explicitly.

## Provisional ranking and unresolved requirements

Rank eligibility requires an unambiguous narrow ordinary-common Names candidate
and at least 40 numerically valid sessions. Every eligible observed security is
ranked by descending reported binary64 mean, then ascending exact raw security
ID using binary string order. Ties refer to the reported binary64 means.
Multiple Names records, including identical repeats, withhold ranking and remain
in the private detail table. The Names scope-review categories remain visible.

The consumer performs **no issuer grouping, no CIK join and no 500-issuer
cutoff**. Ranking more than 500 observed securities is expected when that many
meet the candidate conditions. The narrower Names predicate does not establish
the full protocol's eligible population. Each annual row has null `known_at`
and `available_at`; the calendar cutoff does not establish historical
availability. The strict [normalized universe contract](historical_dataset.md)
still requires historical timestamps, defensible issuer links, source
conventions and population evidence before selecting issuer memberships.

The numerical bundle's benchmark-reconciliation declaration is copied
unchanged. Liquidity arithmetic reads no return values and cannot resolve a
benchmark discrepancy, approve a payoff or create an event label. The final
period remains closed.

## Private outputs and bounded processing

- `receipt.json`: bounded input bindings, policies, processing limits and annual
  coverage counts. CLI output uses an aggregate-only whitelist.
- `input_receipts/`: exact direct and source-receipt snapshots.
- `annual_liquidity/part-*.parquet`: one row per observed security/year, with
  coverage, provisional mean/rank, listing status and null availability fields.
- `listing_evidence/part-*.parquet`: byte-identical copies of all input Names
  snapshot parts, preserving all raw fields, source hashes, CSV ordinals and
  overlap evidence.

Daily record lineage remains in the bound numerical parts and original source
stage. Each annual row also contains an ordered evidence SHA-256 over every
observed projection's metadata and candidate value bits. The receipt specifies
the exact field order and serialization, so an input-bound window can be
recomputed without copying a second large daily series.

DuckDB sorts one annual window at a time with a 1 GB memory limit, two threads
and private disk spill. SQLite stores the annual union and ranking with a
16 MiB cache; conflicting projection hashes use a separate bounded disk-backed
preflight table. Arrow/Python batches have explicit row and byte limits. Final
directories have mode 0700 and files mode 0400. All tables remain private;
aggregate summaries expose no security identifiers, raw flag text or market
value series. Every receipt retains `model_ready: false`, zero new source
approvals and the unchanged arithmetic-review and final-period state.
