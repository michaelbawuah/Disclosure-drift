# Offline manual WRDS source projection

The source stage reads the preserved daily and independent-market inventories
created by the [manual download workflow](wrds_daypass_export.md). It operates
locally without connecting to WRDS. Use it after the downloaded daily files have
passed inventory, including the explicit extra-column declaration for a wider
export.

From the repository on the data-holding computer:

```bash
uv run --locked --python 3.12 python scripts/wrds_manual_stage.py stage \
  --daily-inventory data/private/wrds-intake/2009-v1 \
  --daily-inventory data/private/wrds-intake/2010-2012-v1 \
  --daily-inventory data/private/wrds-intake/2013-2015-v1 \
  --daily-inventory data/private/wrds-intake/2016-2022-v1 \
  --market-inventory data/private/wrds-intake/market-v1 \
  --request-start 2009-10-07 --request-end 2022-02-02 \
  --output data/private/wrds-source-stage/development-v1
```

Use a new output directory for each attempt. A failed attempt may leave partial
evidence there, but cannot write a successful `receipt.json`. Preserve it and
choose another output path. The requested dates must stay inside the locked
development source envelope. This includes the early-2022 return tail needed
for late-2021 filings, without opening final-period filing outcomes.

## What the stage verifies

Before interpreting a benchmark return, the stage checks the actual byte hashes
and completes a full date-only scan of **every** daily file and the independent
market file. It checks headers, record widths, row counts and date coverage
against the corresponding inventory receipts. Receipt-relative source paths
cannot escape their bundle or traverse symbolic links. Source identities are
checked across passes, with source and receipt hashes checked again before a
successful receipt is written.

The independent benchmark must contain exactly one valid, finite `vwretd`
observation per delivered date, with values at least -1. Duplicate or invalid
market records stop projection. There is no fallback to the market values
attached to security rows.

For the requested window, every attached daily `vwretd` is compared with the
independent market observation using exact decimal equality. Numerically equal
spellings such as `0.01` and `1e-2` are reported separately from exact text matches.
Missing dates, invalid cells, numeric disagreements, daily within-date conflicts,
expected-session gaps and overlap between batch dates remain explicit.

The receipt's `reconciliation.requested_window_numerically_reconciled` is true
only when the requested expected daily and market sessions are covered and the
attached benchmark cells have no numeric reconciliation issues. This is a
benchmark/date result; it does not establish security-universe completeness.

## Preserved output and scope

Original multi-gigabyte downloads remain in their inventory bundles. The stage
copies only their small receipts and writes bounded, read-only Parquet parts:

| Output | Content |
|---|---|
| `input_receipts/` | Exact copies of the input inventory receipts, bound by SHA-256 |
| `projections/part-*.parquet` | All 13 required raw strings for every daily record, plus provenance |
| `receipt.json` | Input references/hashes, output part hashes/counts, code/protocol hashes, coverage and reconciliation |

The four provenance fields are `source_sha256`, `source_inventory_sha256`,
`source_csv_record`, and `in_requested_window`. CSV numbering counts the header
as record 1 and handles quoted multiline cells as one record. Every repeated
record and the extra early-2009 records are retained. Extra columns in a wider
download remain in its original file. Equality over the 13-field projection
does not establish equality over all delivered fields.

This stage does not deduplicate security/date keys, normalize stock returns,
create labels, establish terminal events, or supply historical CIK mappings and
availability timestamps. Its outputs remain
`RAW_MANUAL_WRDS_SOURCE_PROJECTION_NOT_SOURCE_APPROVED`, with
`model_ready: false` and zero source approvals. The completed 20/20 arithmetic
review is unchanged. Numerical candidate policies are documented separately in
[WRDS source conventions](wrds_source_conventions.md).
