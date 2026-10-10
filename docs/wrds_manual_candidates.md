# Provisional numerical candidates from manual WRDS sources

Run this local consumer after the [source projection stage](wrds_manual_stage.md):

```bash
uv run --locked --python 3.12 python scripts/wrds_manual_candidates.py \
  --stage data/private/wrds-source-stage/development-v1 \
  --output data/private/wrds-candidates/development-v1
```

The new bundle is a source-review aid. It does not satisfy the approved market,
universe, or model-dataset schemas. Candidate numeric columns carry a
`_candidate` suffix; the receipt always records `model_ready: false`, zero new
source approvals, no event labels and final-period access closed.

## Integrity and bounded processing

The consumer verifies the locked protocol, development request bounds, upstream
receipt contract, actual Parquet hashes, schemas, row counts and source-record
provenance. Every projected date is inspected before numeric conversion. The
raw stage's receipt is copied exactly into the new bundle and bound by SHA-256.
Original multi-gigabyte CSVs are not copied or reopened by this consumer; their
hash verification is the responsibility of the bound upstream source stage.

DuckDB uses a 1 GB memory limit, two threads and local spill files to deduplicate
the complete requested source projection. Python reader batches adapt to the
largest observed row, with an estimated 32 MiB byte budget. A row exceeding that
budget is refused. Bounded batches stream into Parquet parts of at most 250,000
rows. Final directories have mode 0700 and files mode 0400.

Exact repetitions of all 13 raw fields become one candidate projection, with
the original record count and distinct-source-file count. Every distinct
projection for a conflicting security/date is retained, but all of its numeric
candidates are withheld. The source stage retains the provenance for every
original record; each candidate also carries a deterministic representative
source hash, inventory-receipt hash and CSV record number, selected together as
one tuple. A projection fingerprint binds the canonical 13-field JSON array.

This is projection equality only. The wider export's additional fields remain
in the original source; their full-row equality has not been established.
Extra early rows remain in the source stage and are counted explicitly as
outside the requested candidate window.

## Explicit candidate rules

The rationale and primary source references are in
[WRDS source conventions](wrds_source_conventions.md).

| Candidate | Conditions and conversion |
|---|---|
| Daily total return | Literal `NA`; supported `N`/`Y` delisting flag; finite `DlyRet >= -1`; unchanged, with no additional `DLRET` |
| USD capitalization | Strictly positive `DlyCap * 1000`, using the proposed USD convention |
| Closing-price-volume proxy | `DlyPrcFlg` of `TR` or `BA`, positive price and nonnegative raw volume; `DlyPrc * DlyVol` |

Identifiers must be positive integer source strings and dates must be XNYS
sessions. Numeric text is limited to 256 ASCII decimal/scientific-notation
characters without whitespace. Nonzero results that overflow or underflow to
zero during float conversion are withheld. Missing returns are never filled,
negative CIZ prices are never made positive, and recorded zero volume remains
valid only when the price conditions are satisfied.

Each projection has return, capitalization and liquidity status fields. `MV`
and other unresolved return flags retain their original values in private
records. Aggregate flag counts use a bounded documented-code set and an
`__UNRECOGNIZED__` bucket, so malformed source text cannot enter CLI output.

`DlyDelFlg = Y` remains `PAYOFF_AND_TERMINATION_REVIEW_REQUIRED`. It does not
create a `terminal_event`, a payoff approval, a continuation row, or a label.
The independent-market reconciliation result is carried from the bound source
receipt and can remain false; creating candidates does not resolve that issue.

The bundle supplies no historical CIKs, dated industry, eligible listings,
historical `known_at`/`available_at`, selected annual universe or approved
research evidence. Those remain separate source-bound tasks. The previously
completed 20/20 arithmetic review is preserved without being relabeled as
approval of these new sources or candidate policies.
