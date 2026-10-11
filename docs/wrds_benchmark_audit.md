# Private manual WRDS benchmark diagnostic

This offline diagnostic compares the `vwretd` text attached to each requested
daily stock record with the separately preserved, date-level market export. It
creates exact, source-bound evidence for investigating discrepancies. It does
not choose which source is correct, replace either source, or approve a market
provider.

The comparison concerns benchmark values only. It does not calculate or assess
individual stock returns, prices, capitalization, liquidity, terminal events,
event labels, historical identities, or historical availability. Original stock
records remain in the upstream source stage.

## Run from the repository root

Use the current repository version, including the streaming source-record
preflight introduced by the candidate memory fix. The paths below are examples;
substitute the existing source-stage directory and a new private output path.

```bash
uv run --locked --python 3.12 python scripts/wrds_manual_benchmark_audit.py \
  --protocol configs/protocol.json \
  --stage data/private/wrds/source-stage-v1 \
  --output data/private/wrds/benchmark-audit-v1
```

The output must be a new directory beneath this repository's `data/` or
`outputs/` tree. It must be outside the input source-stage bundle and the
preserved independent-market inventory. Existing output directories are refused.
The command does not contact WRDS or require a live day pass.

The preserved market inventory must remain available at the path recorded in the
stage receipt. Moving that inventory without a new, truthful upstream stage
breaks this binding. The diagnostic does not search for a substitute source.

## Required preserved inputs

The `--stage` directory must contain a successful raw-source projection with
status `RAW_MANUAL_WRDS_SOURCE_PROJECTION_NOT_SOURCE_APPROVED`, its `receipt.json`,
all listed Parquet parts, and its exact inventory receipt snapshots. An upstream
`requested_window_numerically_reconciled: false` is permitted: investigating that
result is the purpose of this tool.

Each daily part must have the canonical 13 raw string fields and the source SHA,
inventory receipt SHA, CSV record ordinal, and requested-window flag. There must
be one or more daily sources and exactly one independent-market source, within
the upstream limit of 64 daily sources. Unknown source roles, repeated source
hashes, missing required fields, and unsupported schema or projection
declarations are refused.

The independent-market inventory must retain both its original inventory
receipt and the exact preserved CSV bytes. That file must have exactly
`dlycaldt` and `vwretd`, in either column order and with unambiguous
case-insensitive field names. Plain and gzip-compressed CSV are supported by the
existing source reader.

Original daily CSVs are not reopened or rehashed by this diagnostic. Their
provenance is bound through the verified stage parts and verified inventory
receipt snapshots; original-byte verification remains recorded by the upstream
source stage. The actual preserved independent-market CSV and its original
inventory receipt are reopened and rehashed here.

## Validation order and preservation

The frozen protocol lock and development request envelope are checked first.
The diagnostic verifies the stage receipt, part sizes and SHA-256 hashes,
Parquet schemas, source declarations, and every staged inventory receipt hash.
For the independent market, the current inventory receipt must be byte-identical
to the staged snapshot. Its preserved source must match the declared byte count
and SHA-256 and use a safe relative path within that inventory. Traversal paths
and symbolic links in consumed relative paths are refused.

A complete pass through every projected date and provenance record follows.
Each source's CSV record ordinals must advance consecutively from record 2 across
the ordered parts; the header is record 1. This verifies record completeness and
uniqueness without constructing a global table containing millions of source
record keys. The independent market then receives its own complete date pass.
Only after both passes and the provenance checks succeed does any benchmark text
become a number.

Any source date after the last permitted development-return date is refused.
Independent-market dates must be unique, even when duplicated rows would contain
the same value. Every requested projected daily date must have an independent
market record; missing matches cause refusal. Required projected raw fields
cannot be null. Expected exchange-session gaps and unexpected requested dates
are reported in aggregate and prevent full-window numerical reconciliation.

File identity checks continue between processing phases. All input stage parts,
the stage receipt, consumed inventory receipts, and the actual independent-market
source are rehashed before publication. Copied receipt hashes are checked again.
Work occurs in a temporary private directory, and the completed bundle is moved
to the requested output only after validation. A failure does not publish a
successful output bundle or alter the original inputs.

## Private output bundle

| File | Contents |
| --- | --- |
| `source_stage_receipt.json` | Exact bytes of the bound upstream stage receipt. |
| `input_receipts/daily-001.json`, and subsequent numbered daily receipts | Exact inventory receipt snapshots for every daily source. |
| `input_receipts/market-001.json` | Exact receipt bound to the preserved independent-market source. |
| `mismatches.parquet` | Private, exact discrepancy evidence at the date/source/raw-text-group level. An exact-match run still writes an empty table with the declared schema. |
| `receipt.json` | Input bindings, output table hash and size, aggregate counts, comparison rules, coverage, processing limits, and unapproved status. |

Final directories use mode 0700 and files use mode 0400. The mismatch table
contains licensed benchmark values and dates and must remain private. It has no
PERMNO, PERMCO, ticker, CUSIP, or individual-stock-return columns.

### Mismatch table fields

Each row represents one requested date, one daily source and inventory receipt,
and one exact attached `vwretd` text spelling. Repeated stock records contribute
to `daily_rows_affected`; they are not discarded or treated as independent
benchmark observations. Two numerically equal spellings remain distinct groups
when that shared numeric value differs from the independent source.

The table records:

- `date`, `daily_source_sha256`, and `daily_inventory_receipt_sha256`;
- `market_source_sha256`, `market_inventory_receipt_sha256`, and the independent
  source's `market_source_csv_record`;
- `daily_raw_text` and `market_raw_text`, without replacing their source spelling;
- `daily_minus_independent_exact`, a Decimal difference stored as exact text,
  and `daily_rows_affected`;
- each literal's decimal quantum exponent, coefficient digit count under the
  `*_literal_significant_digits` field names, and scientific-notation indicator;
- the coarser source quantum exponent and whether separately rounding both
  values to that quantum makes them equal;
- equality indicators after separately rounding both values to 4, 5, 6, 7, 8,
  10, and 12 decimal places.

The sign convention is always **attached daily benchmark minus independent
market benchmark**. Positive and negative counts use that convention.

Different numeric attached benchmark values on the same date are refused,
whether they occur within one source file or across different source files.
The tool does not choose a representative from conflicting values. Numerically
equal spellings are counted separately from exact text equality.

## Decimal and memory bounds

Benchmark parsing uses Decimal directly, without a binary floating-point
intermediate. After surrounding whitespace is stripped for interpretation, the
literal must use ASCII decimal or scientific notation. Raw text is preserved.
Both sources must supply finite values at least -1.

| Bound | Implementation |
| --- | --- |
| Numeric source text | At most 256 characters, including any surrounding whitespace. |
| Decimal exponent | Absolute literal exponent and adjusted exponent each at most 1,000. |
| Decimal working precision | At most 2,500 digits. Exact subtraction selects sufficient precision and traps an inexact result. |
| DuckDB | 1 GB memory limit, two threads, local spill directory. |
| SQLite market lookup | 16 MiB configured page cache and file-backed temporary storage. |
| Benchmark-group reader and mismatch writer | Batches of at most 4,096 rows, with bounded numeric text per group. |

Values outside these bounds are explicitly refused; they are not silently
rounded or coerced. Every independent-market value is validated, including rows
outside the requested window. Attached daily benchmark values are interpreted
only within the requested window. Extra early daily rows remain untouched in the
bound source stage.

DuckDB groups the requested date, source/receipt hashes, and attached benchmark
text. It does not build a Python data frame containing all stock rows or group
by full stock records. Consecutive provenance verification is part of the
streaming date pass. The mismatch counts account for every repeated requested
daily row.

## Reading the aggregate report

Successful CLI output is restricted to aggregate coverage, equality and mismatch
counts, mismatches by year and daily-source hash, difference sign counts, exact
minimum and maximum absolute differences, and rounding diagnostics. It prints
no raw source values, per-date mismatch rows, security identifiers, or local
input paths. Failure output contains a fixed failure status and the error class;
underlying CSV, SQL, Arrow, and operating-system exception text is suppressed
because it can contain private cells or paths.

Distinct mismatch dates, mismatching date/source pairs, raw-text groups, and
affected daily rows are different quantities. A discrepancy repeated for many
stocks on one trading day is one discrepant date. By-source date counts can sum
to more than the union of mismatch dates when source batches overlap.

Fixed-decimal rounding counts cover exactly mismatching requested dates and
their affected daily rows. The source-quantum diagnostic instead counts
date/source/raw-text groups and affected rows, because different literal
spellings can imply different displayed precision. A literal such as `0.0100`
has exponent -4; scientific notation applies its exponent before identifying the
quantum. These are properties of the exported text, not verified vendor storage
precision.

All rounding diagnostics use `ROUND_HALF_EVEN`, separately on the two exact
values. Agreement after rounding is **not an acceptance rule**. A small exact
difference, or even agreement at every reported rounded precision, leaves exact
reconciliation false whenever the original numeric values differ. The tool does
not attribute the discrepancy to CSV formatting, underlying storage precision,
source revisions, or different query views without additional source evidence.
The cause remains unresolved.

The receipt always keeps `model_ready: false`, `source_approvals: 0`, and
`final_period_opened: false`. It records no tolerance acceptance, fallback,
source replacement, filled values, approved returns, or change to the prior
arithmetic review. An exact numerical match is only a comparison result and
does not supply the remaining source, historical-identity, availability, or
terminal-event approvals required by the project.

This exact-comparison flag is not a separate frozen research requirement that
both export views must agree. The [protocol](../protocol.md) requires a declared,
documented value-weighted total-return benchmark over the identical label
sessions. A later source-backed, reviewed benchmark decision must preserve the
discrepancy evidence and state any unresolved limitation; it need not change
this diagnostic's exact result. This tool makes no such decision. See the
[completion and review path](research_completion_gates.md#2-obtain-the-missing-historical-facts-and-decide-normalization).

The implementation has focused synthetic tests for exact arithmetic beyond
binary-float and default Decimal precision, ordering of date checks, source
conflicts, market uniqueness, hash and receipt binding, mutation detection,
private output, and non-approving rounding. This document makes no claim that a
production benchmark-audit run has completed or that any real discrepancy has
been explained.
