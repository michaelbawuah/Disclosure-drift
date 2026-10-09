# Experiment log

There are no experiments using actual market returns yet.

## Synthetic engineering run, 2026-10-09

- Data: 144 invented events, 2010-2021; identifiers start with SYNTHETIC.
- Goal: verify annual fold construction, eligible-label filtering, eight declared
  model/grid configurations and reproducible output files.
- Outputs: `outputs/demo/selection.json` and `development_predictions.parquet`.
- Interpretation: software integration check only. These selected penalties and
  scores are not the study's empirical model choices or findings.

## SEC extraction smoke run

- Data: original 2018-2021 filings for the five configured issuers.
- Goal: verify download, caching, acceptance parsing, Item 1A extraction and pairing.
- Evidence: `reports/milestone_01.json` after the run completes.
- Human boundary/timing audit: pending. Automated extraction success is not a
  claim of independently measured extraction accuracy.

For real development experiments, append dataset hashes, protocol/code versions,
folds, configuration, exclusion counts, predictions, scores, interpretation and
whether an idea was specified before outcomes were examined.
