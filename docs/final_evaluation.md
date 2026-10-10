# Development freeze and final evaluation

The primary protocol is `configs/protocol.json`, version 1.0.0. Its locked
SHA-256 is `3951be086ed9a74ec69a304004ebcb5aed63bac161e043ff92ae4f51b8e325d9`.
The older planning document is superseded where it differs from this protocol.

## Development first

Build an audited development bundle with `build-dataset`, then run:

```bash
uv run --locked disclosure develop \
  --bundle data/processed/development --output outputs/development
```

The command validates source evidence and reviews before using the model data.
It fits separate controls-only and controls-plus-all-three-text ridge models.
Each model selects alpha from 0.1, 1, 10 and 100 by pooled development MSE over
2016–2021. Training begins in 2010; each annual fold excludes labels that have
not matured strictly before the first validation prediction.

No separate validation-year vocabulary, scaling, industry fit or final-year
hyperparameter tuning is permitted. The freeze reproduces the development
selection to check supplied predictions and penalties.

## Prerequisite request

[configs/examples/development_prerequisites.json](../configs/examples/development_prerequisites.json)
lists the required paths. These are placeholders, not an approved receipt.
Supply the development dataset, its manifest/exclusions, predictions, selection,
source-bound audit evidence, and completed secondary specification.

The audit evidence names these checks:

- `source_provenance`
- `historical_universe`
- `security_links`
- `filing_extraction`
- `availability_timing`
- `labels_and_controls`

Each empirical pass needs a named human reviewer, valid completion time, notes
and hashed evidence references. The record must bind the actual dataset,
manifest and exclusions. Boolean flags, future-dated reviews, assistant reviews,
stale fingerprints and unresolved reviews cannot substitute for this evidence.
These records are attestations; the software does not authenticate people.

`configs/secondary_analysis.json` deliberately remains pending. Complete the
declared ablation selections, subgroup scheme, semantic chronology/manual
evidence and other fixed secondary choices using development data before access.

## Stage final features separately

`ingest-universe --partition holdout` and `build-dataset --partition holdout`
require `--prerequisites-request` and revalidate it before final input access.
The final bundle contains separate `features.parquet` and `targets.parquet`.
Feature/exclusion schemas are inspected before any potentially outcome-bearing
columns are deserialized. The final dataset's source-bound evidence must pass too.

`load_dataset(..., partition="holdout", features_only=True)` checks the final
source evidence without reading target bytes. Optional semantic feature work
requires the same completed development prerequisites; see
[semantic_analysis.md](semantic_analysis.md).

## Create and use the freeze

Commit the verified source before an empirical freeze. The snapshot binds the
Git commit, all research Python files, the dependency lock, protocol, development
artifacts, review documents, secondary specifications, and final input hashes.

```bash
uv run --locked disclosure freeze-development \
  --request configs/examples/freeze_request.json \
  --output outputs/development-freeze

uv run --locked disclosure evaluate-final \
  --freeze outputs/development-freeze --output outputs/final-evaluation
```

Populate the example paths first. A pending template fails rather than creating
an empirical authorization. Final targets are read only after prerequisites,
schema and artifact checks. The exact target byte snapshot is hash-verified
before parsing; identifiers and event clocks must match the frozen features.

The fixed empirical ledger is `outputs/final-access-ledger/`. It records access
intent before opening targets, retains failure evidence, and rejects a changed
freeze after access. Reproducing the same freeze is allowed in a new output
directory. Keep the ledger with the private study archive; copying or deleting
it is not a scientifically valid way to obtain a new holdout.

## Outputs and interpretation

| Artifact | Content |
|---|---|
| `final_predictions.parquet` | Matched IDs, clocks, true targets and both frozen-model predictions |
| `fold_diagnostics.json` | Four annual refits, training counts, maturity cutoffs and preprocessing provenance |
| `final_summary.json` | Paired incremental R-squared and declared three-/six-month uncertainty intervals |
| `access_receipt.json` | Freeze identity, input hashes, access/run provenance and artifact fingerprints |

Each 2022–2025 model uses earlier acceptance years and only matured labels.
Earlier final-year labels may enter a later annual refit automatically under the
frozen rule; the researcher cannot retune the procedure after seeing them.

The primary score is `1 - SSE(text + controls) / SSE(controls)`. Negative values
are valid. Zero baseline SSE makes that ratio undefined. Sparse or invalid
bootstrap situations retain predictions and an explicit unavailable reason.
Intervals use 2,000 paired contiguous reference-month draws, three months
primary and six months sensitivity, with empty calendar months retained.

The final metrics remain approximate conditional summaries of four evaluation
years. Forecast accuracy is not a transaction-cost-adjusted trading result.

## Synthetic verification

`make reproduce-full` creates visibly invented inputs, a synthetic-only freeze
and a separate synthetic ledger. It does not mark source reviews complete or
authorize the real study. Test cases cover changed sources, wrong identities,
outcome columns in feature files, future information, label maturity, exact
target snapshots, changed freezes and final labels extending into 2026.
