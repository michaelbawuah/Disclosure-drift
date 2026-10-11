# Reconcile saved historical identity and liquidity evidence

The foundation consumer combines the completed annual Names/CCM and liquidity
bundles with the pinned original-SEC identity report. Its purpose is to quantify
which identity and source gaps affect otherwise usable securities and preserve
the original evidence for each filing candidate. It produces private evidence
tables and an aggregate report; it does not construct a forecasting dataset.

## Measured development result

The actual Mac execution completed on **October 11, 2026 at 10:38:20 UTC** in
**48.393520 seconds**, using code commit
`710fa6833055c13224805bf28dbb445f24af976d`. It retained **87,405 annual security
observations**, comprising all **86,064 identity rows** and **1,341 additional
liquidity-only rows**. Of those additional rows, **490** meet the numerical
liquidity minimum; an inner join would have hidden this coverage gap.

The [aggregate results](../reports/historical_foundation_aggregate.json) and
[execution record](../reports/historical_foundation_execution.json) bind the
actual inputs, output hashes, row counts, code and protected prior reviews.
The existing **100,261 Names/CCM relationships** and **110,124 CCM source
occurrences** were verified. No relationships were silently replaced.

Among **50,230 provisionally rank-eligible annual observations**:

| Existing identity evidence | Annual observations |
|---|---:|
| One candidate with a usable current-header CIK; historical confirmation still needed | 46,359 |
| One candidate with missing or unsupported header CIK | 1,315 |
| Multiple or ambiguous candidate evidence | 2,489 |
| Dated context only; no January 1 candidate | 37 |
| No related CCM record | 30 |
| **Total** | **50,230** |

The last four categories total **3,871 (7.71%)**. The remaining 46,359 are not
historically approved. Across the entire eligible group, **21,315** have only
finite candidate bounds, **28,848** have unresolved candidate bounds, and **67**
have no January 1 candidate. Even the **19,091** observations combining a single
usable header CIK with finite bounds still require the missing historical facts.

All **215 original filings** remain accounted for: **207 existing discoveries**
are bound to original SEC report evidence and **eight original Exxon filings**
remain unmatched. The [discovery diagnostics](../reports/historical_foundation_discovery_diagnostics.json)
show that **15 of 207** saved January 1 Names descriptors do not cover the later
filing acceptance date. All 207 CCM acceptance-date relations are candidates
with unresolved open-end markers; date compatibility does not establish a
resolved interval.

The class analysis retains **627 class-observation records**, including **130
explicit no-inline-fact placeholders** and **59** records with literal ticker
support (eight also have a matching explicit class token). One record has a
literal ticker-text difference. These records are not approved security links.
Filing-level status counts and evidence-gap flags
can overlap. No absence of inline cover facts is treated as an identity exclusion.

The sole ticker-text difference is explained by a
[source-byte check of Tesla's original tag](../reports/tesla_symbol_clarification.json):
it contains one leading line feed before `TSLA`. The saved strict comparison
remains unchanged. This is a formatting explanation, not a new mapping decision.

The complete verification passed **949 tests**, Ruff, the frozen-protocol check
and the full synthetic study. The latter uses invented outcomes and supplies no
empirical score. See the [verification record](../reports/historical_foundation_verification.json).

## Inputs and reproducible execution

The development execution uses these exact saved inputs:

| Input | SHA-256 |
|---|---|
| Identity candidate receipt | `093605e17f0358bd6477899ea1a2e5995a6960124438c7fc5d0046c8ef784099` |
| Annual liquidity receipt | `0be9983b192e2d15a32abe5c29240638d75fcfd639e19cbacb12ed48d977ce20` |
| Compressed original-SEC report | `acdb65f51f0a4e72a2db7356c6093628c6c73dfd8d8d837d8f01d8c12583be1e` |
| SEC manifest | `2658b7adfa03ea3c1800afd4107fa74c5348387533abde87cc30c0472b670fb1` |

Run from the repository containing the saved private bundles:

```bash
uv run --locked --python 3.12 python scripts/build_historical_foundation.py \
  --identity data/private/wrds-identity-candidates/development-v1 \
  --identity-receipt-sha256 093605e17f0358bd6477899ea1a2e5995a6960124438c7fc5d0046c8ef784099 \
  --liquidity data/private/wrds-liquidity-candidates/development-v1 \
  --liquidity-receipt-sha256 0be9983b192e2d15a32abe5c29240638d75fcfd639e19cbacb12ed48d977ce20 \
  --sec-evidence reports/sec_identity_evidence.json.gz \
  --sec-evidence-sha256 acdb65f51f0a4e72a2db7356c6093628c6c73dfd8d8d837d8f01d8c12583be1e \
  --sec-manifest reports/pilot_expansion/filing_sources.csv \
  --sec-manifest-sha256 2658b7adfa03ea3c1800afd4107fa74c5348387533abde87cc30c0472b670fb1 \
  --output data/private/historical-foundation/development-v1
```

Choose a new output directory for each execution. The consumer checks the
frozen protocol and all SEC development dates before opening vendor bundles.
It verifies receipt snapshots, exact part hashes/schemas/counts, source-row
lineage, relationship accounting and the common Names input. Schema-bearing
zero-row parts remain valid. Inputs are rechecked before atomic publication;
private directories use mode `0700` and completed files use `0400`.

## Evidence tables and interpretation

| Private table | What each row represents |
|---|---|
| `annual_foundation` | One exact raw security identifier and development year from the full outer join of annual identity and liquidity evidence. Identity-only and liquidity-only observations remain visible. |
| `liquidity_only_coverage` | The subset with annual liquidity metadata but no annual Names identity row. It is a diagnostic subset of the full union, not additional population members. |
| `filing_candidate_corroboration` | One existing SEC discovery relationship, bound to its exact Names/CCM source occurrences and original SEC primary/header hashes, with context-specific class observations retained as JSON. |
| `filing_coverage` | One row per original SEC manifest entry, including filings without an existing candidate discovery. |

The aggregate cross-tab uses identity status, numerical liquidity qualification,
the **stored eligibility boolean**, finite/unresolved candidate-link bounds and
original-SEC discovery coverage. These are annual observations, not a count of
distinct companies. The consumer does not decode the liquidity mean, numerical
security rank or daily return values. It checks the stored eligibility flag
against the existing policy and published annual totals.

Each class observation retains its own context and facts. Exact ticker text and
an explicit class token can agree or disagree; whitespace, punctuation, share
classes and co-filers are not silently merged. Local namespace, context,
continuation, nil and transformation issues remain visible. Routine global HTML
recovery diagnostics do not by themselves invalidate a local text comparison;
neither a positive lexical status nor a title phrase constitutes interpreted
XBRL, legal-entity mapping or security-class approval.

A saved January 1 Names descriptor can end before its same-year filing. The
consumer records that limitation instead of extending the descriptor. Likewise,
same-year SEC observations occur after the preceding year-end selection cutoff;
their acceptance dates and XBRL context periods do not fill historical knowledge
or availability timestamps.

## Related source findings

The [seven original cover cases](sec_cover_cases.md) explain concrete class and
co-filer traps. The [availability assessment](historical_availability_evidence.md)
records the published historical revision, its comparison with four saved annual
snapshots, and the exact historical-CIK/version evidence still needed.

All candidate `known_at` and `available_at` values remain null. No historical
security links, source approvals, human reviews, issuer grouping, 500-issuer
selection or actual final-period evaluation are created by this consumer.
