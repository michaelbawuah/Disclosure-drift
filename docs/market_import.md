# Market imports and event-label staging

This milestone accepts **already normalized Parquet files**. It does not download
WRDS data, infer CRSP column meanings, prove an account entitlement, select the
historical universe, or prepare a model-ready dataset. Actual vendor mapping must
wait for a small export and its exact release dictionary.

## Try the engineering example

```bash
make market-demo
```

This invents three securities: one continuing, one delisting, and one missing a
return inside the label window. It imports the files, queries validated tables in
DuckDB, and stages two labels plus one explicit exclusion. Independent compound
return calculations check both valid targets. The reference date follows a Friday
filing and Monday exchange holiday. Reference-day returns are intentionally large
to expose accidental inclusion in the target.

The generated `outputs/market-demo/summary.json` and `synthetic_labels.csv` are
software checks only. Temporary invented source files are regenerated on each run.
No stock-market result is implied. `make reproduce` also runs this example.

## Import a mapped development sample

Start with [the schema contract](market_data_contract.md) and copy
`configs/market_manifest.template.json` beside the three normalized Parquet files.
Blank fields intentionally fail validation. Fill in the actual provider, dataset,
release, timestamp with timezone, source documentation, raw-export hashes,
normalization-code hash, and a source field or derivation for every required column.
Record the delisting convention and missing-code treatment in normalization notes.

Only after verifying the source dictionary, set `stock_return_convention` to
`dividends_and_delisting_exactly_once` and `benchmark_convention` to
`value_weighted_total_return`. State which benchmark was used. These declarations
are preserved; the program cannot independently establish their truth or detect
all upstream look-ahead. In particular, a finite but already double-counted
delisting payoff cannot be discovered from the normalized return alone.

```bash
uv run disclosure import-market \
  --manifest data/source_exports/development/manifest.json \
  --output data/market/development-v1
```

The importer requires:

- String permanent security IDs; zero-padded, nonzero 10-digit CIKs.
- ISO session dates without time components, present in the XNYS calendar.
- Finite numeric decimal returns, at least -1; genuine boolean terminal flags.
- Unique return keys, one terminal event at most, no rows after that event.
- Inclusive, nonoverlapping identity intervals with a documented share-class rule.
  Links must already select one eligible class; current tickers are insufficient.
- SHA-256 hashes matching the three input files and paths inside the manifest folder.

Dates are checked before return columns are loaded. Data beyond the latest label
end allowed by a December 31, 2021 acceptance are rejected, never silently trimmed.
Some early-2022 returns are needed for late-2021 events; no 2022 filing event is
accepted. Missing sessions are detected when an event needs them, not filled in.

The new directory contains unchanged source Parquet bytes, the source manifest,
an import receipt, and queryable copies in `market.duckdb`. Validation finishes
before the directory is published. Existing imports are preserved; choose a new
versioned directory for changes. The importer currently loads the normalized sample
in memory. A full-scale import will need a measured memory/storage budget.

## Export filing events and stage labels

Rebuild an offline source audit before exporting an event queue:

```bash
uv run disclosure export-label-events \
  --filings data/processed/pilot-resolved/filings.parquet \
  --pairs data/processed/pilot-resolved/filing_pairs.parquet \
  --audit outputs/audit-pilot-resolved \
  --output data/processed/pilot-resolved/label_events.parquet

uv run disclosure prepare-labels \
  --events data/processed/pilot-resolved/label_events.parquet \
  --market data/market/development-v1 \
  --output data/processed/labels-pilot-v1
```

The export verifies the audit's hashes for filings, pairs and evidence, and requires
passing automated evidence for both filings in each pair. It carries current and
prior evidence fingerprints and the still-separate human review status. The source
pilot remains a purposive engineering sample, not the investment universe.

The thin input contract for `prepare-labels` is `event_id`, `cik`,
`acceptance_timestamp` with timezone, and `data_kind`. Real events use
`REAL_FILING_EVENTS`; invented events and market bundles must both use
`SYNTHETIC_ENGINEERING_FIXTURE`. The source export supplies additional audit fields
which are retained in the labels. Arbitrary event files do not establish a filing audit.

The label command recalculates exchange timing, resolves the security as of the
reference session, and compounds exactly the next 20 stock and benchmark returns.
After a terminal payoff, remaining proceeds earn zero return. Missing identity,
entry record, required stock return, or benchmark session produces a recorded
exclusion with a missing target. The command writes the evidence and exits with
status 1 if any event was excluded, so omissions cannot pass unnoticed.

Outputs are `event_labels.parquet`, `exclusions.csv`, and `label_summary.json`, with
input/bundle/output hashes. They contain no text predictors or market controls and
**are not accepted as model-ready development data**. Complete the human filing
audit, verify vendor mapping, build the historical universe, and audit controls
and labels before constructing the separate development table. Hashes detect
changed inputs; they are not cryptographic signatures or proof of source correctness.
