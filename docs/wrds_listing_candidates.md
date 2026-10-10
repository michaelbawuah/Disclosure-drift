# Dated Names listing candidates

This offline tool creates annual classification evidence for the frozen
**2010–2021 development years**. It does not create the historical universe,
an approved `listings` table, CIK mappings, ranks, or a model dataset. Candidate
outputs remain `model_ready: false` with zero new source approvals; the completed
20-case arithmetic review is unchanged.

## Run from the repository on the machine holding the inventory

```bash
uv run --locked --python 3.12 python scripts/wrds_manual_listing_candidates.py \
  --names-inventory data/private/NAMES_INVENTORY \
  --output data/private/NEW_LISTING_CANDIDATES
```

The input is the existing directory made by `wrds_manual_metadata.py inventory
--role names`, containing `receipt.json` and its preserved CSV/gzip source.
The optional `--protocol` argument defaults to `configs/protocol.json`.
There is no year override or holdout mode. The command makes no network request
and prints only bounded aggregate counts, known flag-code counts, and hashes.
Run it locally with the licensed files; do not upload the Parquet results.

Output must be a new directory beneath `data/` or `outputs/`. It contains:

- `receipt.json`: source, protocol, candidate policy, output hashes and counts.
- `input_receipts/names.json`: the exact input receipt bytes, hash-bound.
- `candidates/part-000001.parquet`, and subsequent bounded parts as needed.

Directories are private (`0700`); generated receipt snapshots, receipts, and
Parquet parts are read-only (`0400`). Existing outputs are never overwritten.
The full original Names source stays in its inventory directory; it is not
copied again or edited.

## Date and provenance rules

The tool verifies the inventory role/status/schema, frozen protocol, source
path, actual source SHA-256, byte count, exact delivered header and record width,
source record count, and inventory date-bound counts and extrema. It recognizes
gzip from the byte signature rather than the extension.

A complete source pass validates all four Names interval fields before any
classification. This candidate implementation requires finite ISO dates and
nonreversed intervals for both `secinfostartdt`/`secinfoenddt` and
`securitybegdt`/`securityenddt`. A blank, `B`, `E`, malformed, or reversed bound
refuses candidate generation. The raw inventory remains intact; no open or
missing bound is replaced with a date. Finite historical metadata extending
past 2021 remains permitted and preserved. It creates no 2022–2025 snapshots.

Each source record whose **inclusive `SecInfo` interval covers January 1** gets
one snapshot for that development year. A record can therefore create several
annual snapshots. Records covering no requested January 1 remain in the source
and are counted separately. `SecurityBegDt` and `SecurityEndDt` do not extend the
classification interval. They describe the extent of security daily data;
security-information start/end dates represent the descriptor history ranges.
See the official [CRSP file-key definitions][file-keys] and [cross-reference
guide][cross-reference].

Every snapshot includes all 24 Names values as unchanged strings in canonical
field order, source SHA-256, input-receipt SHA-256, and CSV record ordinal. The
header is record 1 and the first data record is record 2; a newline inside a
quoted value does not create another CSV record. The original header case/order
is separately retained in the receipt.

The snapshot records `selection_asof`, the first selection-year session, and
the preceding year's final XNYS close as `information_cutoff`, using the frozen
`year_start_window` implementation. **That calendar cutoff is not `known_at`.**
Every output `known_at` is null. Neither a Names validity date, a download time,
nor the security lifetime establishes historical information availability.
The [historical dataset contract](historical_dataset.md) still requires evidence
before these candidates can be consumed as approved historical listings.

## Explicit narrow candidate policy

The following exact source codes define an ordinary-corporate candidate:

| Field | Required candidate values | Official interpretation |
|---|---|---|
| `securitytype` | `EQTY` | Equity |
| `securitysubtype` | `COM` | Common |
| `sharetype` | `NS` | No special share designation |
| `issuertype` | `ACOR`, `CORP` | Assumed corporation or corporation |
| `primaryexch` | `A`, `B`, `I`, `N`, `Q`, `R` | NYSE American, BATS, IEX, NYSE, NASDAQ, NYSE ARCA |
| `tradingstatusflg` | `A` | Active |

Definitions come from CRSP's direct appendices for [security type][security],
[security subtype][subtype], [share type][share], [issuer type][issuer],
[primary exchange][exchange], and [trading status][trading]. Code values are
compared exactly; they are not silently uppercased, trimmed, or substituted.

This is an engineering candidate subset, not a decision that every other
common-equity form is outside the frozen study. REIT, beneficial-interest, ADR,
certificate, unit, and unknown common forms receive explicit `SCOPE_REVIEW_*`
classification statuses. Fund/derivative and other recognized non-common
classifications are distinguished from unknown security classifications. These
are source classifications, not final research exclusions.

`USIncFlg` is retained without an eligibility filter. Incorporation does not
establish listing country. The official [share-code crosswalk][share-crosswalk]
includes common corporate shares with non-U.S. incorporation; the project must
not silently become a domestic-incorporation-only study.

`TradingStatusFlg` values `D`, `H`, and `S` remain delisted, halted, and suspended
statuses. The direct appendix labels `X` unknown/unavailable, so this tool
withholds it as unresolved. It does not interpret an unknown value as active.
The 24-field Names source omits `ConditionalType`; no regular-way-only trading
filter or equivalence to a legacy exchange-code screen is claimed.

Header exchange and SIC fields, `SecurityActiveFlg`, and security lifetime
coverage are diagnostics only. They cannot override the dated `primaryexch`,
`siccd`, or trading status. The generic [yes/no flag dictionary][yes-no] does not
establish the temporal lineage of `SecurityActiveFlg` in this WRDS view; requiring
today's active flag would risk discarding earlier histories of later delistings.
The receipt therefore leaves historical field lineage and source vintage
unverified. The public code definitions are not claimed to be a version-matched
vendor dictionary for the downloaded release.

## Ambiguity, duplicates, and output meaning

Grouping uses exact raw `PERMNO` text and year. A malformed, blank, or zero
identifier remains unresolved; leading zeros are preserved, without identifier
coercion or an inferred CIK. If multiple source records cover the same security
and January 1, **all records remain in the output**, their ambiguity flag is true,
and `ordinary_candidate` is false. This includes exact repeated source records.
The tool does not choose a latest row, merge ranges, or silently deduplicate.

Duplicate equality compares the complete parsed text of all **24 canonical Names
fields**. Counts distinguish repeated equal projections from groups with
different projections. A differing header diagnostic is therefore a different
full projection, even if the classification fields agree. The source record
ordinals keep every copy identifiable. The independent `classification_status`
is retained when `candidate_status` becomes `AMBIGUOUS_DATED_RECORDS`.

The receipt includes each year's snapshot/status/classification counts, overlap
counts, exact-projection duplicate excess, and bounded known-code counts. Unknown
or arbitrary flag text is counted without reproducing it in the aggregate output.
Issuer names, security identifiers, tickers, CUSIPs, and raw classification rows
remain in the private Parquet/source files.

An `ordinary_candidate: true` row passes only this narrow, retrospective source
predicate. It still has unknown `known_at`, no historical CIK evidence, no
liquidity qualification, no issuer ranking, no source approval, and no authority
to open the final period. Current institutional access did not supply the
separately requested historical CIK download; this feature does not replace it
with a current company header.

[security]: https://www.crsp.org/wp-content/uploads/appendix/FlagType_S3.html
[subtype]: https://www.crsp.org/wp-content/uploads/appendix/FlagType_S2.html
[share]: https://www.crsp.org/wp-content/uploads/appendix/FlagType_S4.html
[issuer]: https://www.crsp.org/wp-content/uploads/appendix/FlagType_IT.html
[exchange]: https://www.crsp.org/wp-content/uploads/appendix/FlagType_EC.html
[trading]: https://www.crsp.org/wp-content/uploads/appendix/FlagType_TS.html
[yes-no]: https://www.crsp.org/wp-content/uploads/appendix/FlagType_YN.html
[file-keys]: https://www.crsp.org/wp-content/uploads/appendix/FlagType_FK.html
[share-crosswalk]: https://www.crsp.org/wp-content/uploads/ShareCode.html
[cross-reference]: https://www.crsp.org/crsp_pdf/crsp-us-stock-indexes-databases-siz-to-ciz-cross-reference-guide/
