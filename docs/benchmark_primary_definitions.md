# Native CRSP benchmark definitions recovered

**Status: primary-document verification, 11 October 2026. No source selection or
approval enacted.** The current public manuals now identify the native index,
return field and weighting convention precisely. They do not establish that
either saved WRDS export implements that definition or explain the 52 previously
audited differences.

## What is new

The earlier [source proposal](benchmark_source_decision.md) relied on WRDS macros
and an older guide because the replacement PDF had not been retrieved. This
review downloaded three complete manuals from PDF asset URLs embedded in the
official [Morningstar document library](https://indexes.morningstar.com/research-data-products/document-library).
The [current CIZ guide page](https://indexes.morningstar.com/docs/guide/crsp-us-stock-databases-guide-for-flat-file-format-2-0?isRdp=true)
also exposed an iframe URL whose PDF bytes match the library's guide asset.
Selected pages were rendered and visually inspected; the identifiers and table
columns below were checked against the images.

The [retrieval record](../reports/benchmark_primary_definitions.json) contains
exact URLs, UTC retrieval times, byte counts, SHA-256 hashes, page locators and
image hashes. It reports assistant source inspection, not a human judgment or
an independent empirical reproduction. Complete manuals and page images remain
outside Git.

| Document | Library date | Bytes | Inspected PDF pages |
| --- | --- | ---: | --- |
| [CIZ user guide](https://assets.contentstack.io/v3/assets/bltabf2a7413d5a8f05/bltb7f7b7bd614e55a3/6a71c517e35d02a71403136d/CRSP_US_Stock_Databases_Guide_for_Flat_File_Format_2_0.pdf) | 2026-07-31 | 10,795,671 | 11, 17, 18, 25, 37 |
| [Calculation and index methodology guide](https://assets.contentstack.io/v3/assets/bltabf2a7413d5a8f05/blt948fb9dd4aff01a3/6a454f3183e511651648cf28/CRSP_US_Stock_Databases_Calculations_and_Index_Methodologies_Guide.pdf) | 2026-06-30 | 405,499 | 9, 10, 15 |
| [Legacy-to-CIZ cross-reference guide](https://assets.contentstack.io/v3/assets/bltabf2a7413d5a8f05/blt7a9098fa790aa8f4/6a454f57b1784a7d6e01a787/CRSP_US_Stock_Databases_Cross_Reference_Guide_for_Legacy_FIZ_SIZ_to_CIZ.pdf) | 2026-06-30 | 2,598,818 | 19 |

All pages use one-based PDF numbering, matching the printed page numbers.
Library dates describe documents; they are not the saved data's vintage.

## A precise native benchmark to verify

The guide's page 37 identifies **`INDNO = 1000200`** for the combined NYSE,
NYSE American, NASDAQ and Arca market, with value weighting. The daily and
monthly identifier columns agree; this index is listed for both stock-only and
stock-plus-index products. Page 25 places **`DlyTotRet`** and **`DlyCalDt`** in
**`IndDlySeriesData`**: the return includes distributions and the date identifies
a trading day. [CIZ guide, pp. 25 and 37](https://assets.contentstack.io/v3/assets/bltabf2a7413d5a8f05/bltb7f7b7bd614e55a3/6a71c517e35d02a71403136d/CRSP_US_Stock_Databases_Guide_for_Flat_File_Format_2_0.pdf#page=25)

The methodology combines security returns using market-capitalization weights
from the preceding trading period. Its market-index description requires
usable price and share observations and excludes ADRs. This documents a broad
market benchmark; it does not redefine the project's separately selected
research universe. [Methodology guide, pp. 9–10 and 15](https://assets.contentstack.io/v3/assets/bltabf2a7413d5a8f05/blt948fb9dd4aff01a3/6a454f3183e511651648cf28/CRSP_US_Stock_Databases_Calculations_and_Index_Methodologies_Guide.pdf#page=9)

**Inference for this project:** this native identifier/field pair is a defensible
specification to check when binding the proposed independent `vwretd` series to
the [frozen benchmark contract](market_data_contract.md#returns-and-benchmark).
It is not a verified mapping from `crsp_a_stock.wrds_dailyindexret_query` or
`wrds_dsfv2_query` to that native series. No new query was executed, no vendor
return was recalculated, and no downloaded value was replaced.

## What the manuals do not settle

The cross-reference guide maps legacy `SFZ_DIND.tret` to the native daily total
return field. Its index chapter also describes legacy-system results carried
into CIZ, which can differ from a fresh calculation using CIZ inputs.
[Cross-reference guide, p. 19](https://assets.contentstack.io/v3/assets/bltabf2a7413d5a8f05/blt7a9098fa790aa8f4/6a454f57b1784a7d6e01a787/CRSP_US_Stock_Databases_Cross_Reference_Guide_for_Legacy_FIZ_SIZ_to_CIZ.pdf#page=19)
That document-level statement does not establish which calculation path either
saved WRDS view used or when its text became applicable. It cannot assign a
cause to the [52 exact discrepancies](wrds_benchmark_audit.md).

The user guide's general numeric-category table is also not a specification of
WRDS CSV rounding. Its technical metadata reference is useful for obtaining the
actual column and export definitions, but the observed six-decimal CSV literals
remain insufficient to reconstruct pre-export precision.
[CIZ guide, p. 11](https://assets.contentstack.io/v3/assets/bltabf2a7413d5a8f05/bltb7f7b7bd614e55a3/6a71c517e35d02a71403136d/CRSP_US_Stock_Databases_Guide_for_Flat_File_Format_2_0.pdf#page=11)

The next source check is now specific: obtain a dated definition for each saved
WRDS view, its native index identifier and expression, library mapping, release,
numeric type, and export formatting. Bind that evidence to the preserved query
and CSV hashes before normalization. A documented native series can establish
the intended convention without inventing a vintage; verifying that the saved
export follows it remains a separate requirement.

The [source proposal](benchmark_source_decision.md#evidence-needed-for-a-decision)
and review requirements remain in force. This review reads public documentation
only: zero new source approvals, no tolerance acceptance, no new human reviews,
and no opening of final-period filing outcomes.
