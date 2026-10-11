# Reconcile saved historical identity and liquidity evidence

The foundation consumer combines the completed annual Names/CCM and liquidity
bundles with the pinned original-SEC identity report. Its purpose is to quantify
which identity and source gaps affect otherwise usable securities and preserve
the original evidence for each filing candidate. It produces private evidence
tables and an aggregate report; it does not construct a forecasting dataset.

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
