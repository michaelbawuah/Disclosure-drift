# Annual WRDS product label confirmed; export definition still needed

The October 11, 2026 follow-up established one additional source fact:
WRDS's [public CRSP catalog](https://wrds-www.wharton.upenn.edu/pages/about/data-vendors/center-for-research-in-security-prices-crsp/)
identifies `crsp_a_stock` as **CRSP Stock (Annual)** and describes its update
frequency as annual. The catalog's displayed July 16, 2026 update time has no
stated timezone and is not evidence of the preserved export's release.

The [exact follow-up record](../reports/benchmark_source_followup.json) binds
the retrieved catalog, a migration announcement, the observed dictionary
sign-in response, and a read-only recheck of the preserved source packet.
The annual dictionary required authentication; its contents were not read.
No new WRDS data query or external message was sent.

## What remains unresolved

The original 260-byte SQL still selects `DlyCalDt` and `vwretd` from
`crsp_a_stock.wrds_dailyindexret_query`. It contains neither `1000200` nor
`DlyTotRet`. The verified SQL, inventory snapshot and source-evidence record
remain bound to the existing packet. The market inventory receipt is
`d06ea38c6b8a75eb41af7a7ecfc46c7f30987262d97090d08572b01ad7356ed8`.
This recheck did not reopen the original market CSV or discrepancy rows.

The [native CRSP manuals](benchmark_primary_definitions.md) identify the intended
index and return convention. Searches of the complete extracted text of all
three manuals found no exact WRDS view or schema names. Consequently, this
follow-up supplies no applicable view expression, alias definition, export
vintage or CSV rounding rule. **Zero of the 52 discrepancy causes were resolved.**

The remaining source question is now precise: what base relation, native index
identifier, return field, typed expression and transformations underlie
`crsp_a_stock.wrds_dailyindexret_query.vwretd`, and which definition and release
apply to the saved CSV? Explaining the differences also requires the stock
view's corresponding benchmark expression and the two export/revision paths.

The [proposed benchmark decision](benchmark_source_decision.md) remains pending.
An annual product label cannot certify the saved query's computation. This
follow-up changes no source approval, historical availability value, frozen
protocol setting or final-evaluation gate.
