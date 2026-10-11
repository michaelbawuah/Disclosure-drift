# Actual 2020 issuer-corroboration results

The new reconciliation ran successfully on the Mac at commit
`5a96224662bdb77c06361516a4dc84db0a4eaf7a` in **12.761 seconds**. It retained
every one of the **4,122 rank-eligible 2020 security observations** from the
pinned historical foundation and all **38,145 original SEC ownership-form
occurrences** from 2019 Q4. The original **191,048-row Names history** supplied
dated descriptors and complete-source collision checks.

The [actual execution record](../reports/sec_ownership_execution.json) and
[exact aggregate](../reports/sec_ownership_aggregate.json) bind the inputs,
code, outputs and unchanged protocol/review evidence. These are historical
issuer observations and candidate comparisons. They do not approve a historical
security crosswalk, universe membership or availability timestamp.

## Complete cohort accounting

The 2020 foundation contains 7,773 annual security observations. All 4,122
already marked rank-eligible by the saved provisional policy were retained;
the new consumer did not calculate liquidity, ranks, issuer groups or a top-500
selection. Securities without this quarter's SEC evidence remain in the output.

| Exclusive observed result | Securities |
|---|---:|
| At least one unambiguous earlier literal match, with one earlier issuer CIK observed | 3,098 |
| At least one unambiguous earlier literal match, with multiple earlier issuer CIKs observed | 7 |
| Earlier literal matches exist, but none is unambiguous | 16 |
| Matches occur only on the cutoff day, with no clock in the quarterly extract | 14 |
| No exact usable symbol/date observation in this quarter | 987 |
| **Entire eligible 2020 cohort** | **4,122** |

Thus **3,105 securities** have at least one unambiguous earlier literal
observation. The seven multiple-CIK cases remain unresolved even though an
individual ticker/descriptor match can be unambiguous. The earlier date is the
SEC extract's reported filing date, not a certified historical public-availability
time. All **446 cutoff-day SEC occurrences** remain separate from the **37,699
earlier-date occurrences**. The consumer preserves all **907 SEC occurrences
with unresolved symbol literals**, including placeholders and combined or spaced
text, without creating
aliases from them.

The full Names history is searched, including securities outside the cohort.
The code also checks simultaneous descriptors for the same security comparison
key, even if they use different tickers. Both matching fields are retained when
`ticker` and `tradingsymbol` agree with the SEC literal; one source relationship
is not counted twice merely because both fields match.

## What changed for unsupported current-header cases

The original cohort has **3,801** observations with one usable current-header
CIK and **321** with missing, ambiguous or other unresolved candidate evidence.
The latter comprise 111 missing/unsupported header cases, 205 multiple/ambiguous
cases, three without related CCM records, and two with dated context only.

**47 of the 111 missing/unsupported header cases now have one earlier issuer
CIK observed through unambiguous literal matches.** A separate source follow-up
checked one original ownership filing for every one of those 47 cases. It chose
the earliest qualifying filing per security, with deterministic accession and
source-ordinal tie breaks. The [complete original-filing audit](sec_ownership_original_followup.md)
confirmed all 47 original header issuer CIK/name and XML issuer CIK/name/symbol
against their selected quarterly occurrences, with zero literal differences.
All 47 acceptance dates precede the 2020 selection cutoff.

The remaining 64 missing/unsupported header cases comprise 63 with no usable
quarterly observation and one with only cutoff-day evidence. Absence from the
quarter does not justify exclusion. The original-filing audit confirms issuer
observations; it does not independently certify the Names-to-security relation,
share class, continuous validity or historical source availability.

Across the whole cohort, **3,005 securities** have at least one unambiguous
earlier comparison agreeing with a current-header candidate and **60** have at
least one disagreeing comparison. **Eight securities appear in both counts.**
These are pairwise comparison flags; disagreement with one candidate does not
mean the observed issuer is outside every candidate in that security's set.
Every candidate relationship remains preserved, including unresolved bounds,
unsupported CIKs and records supplying dated context only.

## Exxon: a concrete reason current headers can miss historical issuers

The [separate Exxon diagnostic](exxon_candidate_diagnostic.md) established that
the saved header refers to CIK `0002115436`, the later successor registrant
documented in an original July 2026 filing. The original 2014–2021 issuer is
CIK `0000034088`. The source value, rather than a dropped relationship or CIK
parsing error, explains why the original header-based discovery missed all
eight pilot filings.

Eight original historical SEC observations report the same common-stock CUSIP.
A declared literal CUSIP projection finds one original Names record at all
**656 required filing/control/reference/label date points** and all **eight
January selections**, with no raw identifier disagreement or saved lifetime
failure. These are descriptor candidates. **379 of the 656 points precede their
paired same-year SEC corroboration acceptance date**, and the 2026 successor
filing supplies later explanatory context only. Neither result establishes
contemporaneous historical CIK knowledge or a continuous interval.

The original foundation remains 207 discoveries plus eight unmatched filings,
covering all 215 pilot filings. This additional evidence is preserved separately;
the old discovery accounting has not been rewritten to make the gaps disappear.

## Reproduction and evidence retained

The [consumer contract](sec_ownership_corrob.md) defines the exact source and
receipt requirements. The actual command, including every supplied pin, is in
the execution record. Its immutable private output is
`data/private/sec-ownership-corrob/development-v1`.

| Private output | Rows |
|---|---:|
| Original cohort and one summary per cohort security | 4,122 each |
| Original SEC occurrences, with all 13 delivered fields | 38,145 |
| Original Names records retained with collision and date context | 4,524 |
| Original cohort relationships and their CCM source records | 5,141 each |
| Dated issuer/symbol/Names observations | 31,466 |
| Comparisons against all original related CCM records | 36,822 |
| Original-source follow-ups, including unmatched cohort placeholders | 32,453 |

The 48 Parquet parts total 7,104,141 bytes. The bundle also retains the exact
original TSV and input-receipt snapshots. Private vendor rows and raw security
identifiers are not included in the public aggregate.

| Binding | SHA-256 |
|---|---|
| Completed Mac receipt | `85358e4f928687ed9fc3da3813e87980321bbd155b24c952f7a955c5c92a8442` |
| Exact Mac aggregate | `94044c0b9b96593207713421dd1b4af92b664944d077e0f6bde4a0740c8301c5` |
| Implementation module | `5ee8435e933fd1906bc9d2818c7d200e047afc371e238d168b8e412799a6cd7f` |
| CLI | `6ed8541f93ea5ae20105c927dbffda8cc7e84bd96c00f6182be78a38758ee519` |

## Independent verification

A separate verifier rebuilt the original annual Names projection, all 100,261
Names/CCM relationships, all 86,064 annual identity summaries and all 87,405
foundation observations from the original source bytes. It then reconstructed
all nine new output tables. Every row and typed schema matched, including the
complete 4,122-row cohort, all 38,145 SEC occurrences, all 31,466 observations
and the 32,453-row follow-up queue. The successful verification took **16.423
seconds** and rehashed 313 consumed files at completion.

A second independent check rebuilt all **656 Exxon role/date points** plus
eight January selections. All 664 global literal CUSIP matches were unique,
used the same raw security identifier and fell within the recorded security
lifetime. It independently confirmed the 379 earlier paired-SEC date count.
This second check inspected the full CCM assertions and spot-checked original
records; it did not repeat the entire 110,124-row CCM absence audit.

The [verification record](../reports/sec_ownership_verification.json) binds
both independent checks, the original-filing checks, source preservation and
implementation evidence. The exact-code [GitHub Actions run](https://github.com/michaelbawuah/Disclosure-drift/actions/runs/38152628371)
passed **995 tests**, Ruff and the full synthetic study. The synthetic results
validate software behavior; they contain no empirical market findings.

These results advance the source work for milestones 6 and 7. Historical identity
intervals, class decisions, source availability and the reviewed benchmark choice
remain open. The [benchmark follow-up](benchmark_source_followup.md) established
the current annual product label but resolved none of the 52 discrepancy causes.
Empirical milestones 5–11 remain pending; the frozen protocol, prior numerical
review, completed assistant filing reviews and closed final period are preserved.
