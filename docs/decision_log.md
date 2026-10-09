# Decision log

## 2026-10-09 - Initial protocol freeze

- Keep the annual Risk Factors / 20-session question as an extension of Lazy Prices.
- Reserve 2022-2025 for the primary untouched evaluation. Earlier 2019-2021 pilot
  observations are explicitly development data.
- Use raw market-adjusted returns as target, avoiding monthly rank maturity problems.
- Use three simple text features; fit TF-IDF/scaling in each training fold. Whole-year
  cross-sectional feature ranking is prohibited because it uses future filings.
- Select ridge penalties separately for the controls and augmented models from four
  values. Fix all three text features for the primary model, reducing model-search
  freedom; feature ablations are secondary diagnostics.
- Use second-session timing and SGML acceptance headers where retrievable, retaining
  API raw values and a separate public-availability uncertainty field.
- Bootstrap consecutive reference-month blocks, retaining both models' paired
  losses and all firms. Use three months, with six months as a declared sensitivity.
- Preregister the embedding comparison before opening holdout outcomes. Its exact
  checkpoint/chronology/chunking audit is pending and remains an access gate.
- Added-versus-removed risks and the 2020 disclosure-rule transition enter the
  interpretation/audit plan. A thematic or 2026 extension needs a separate protocol.
- Begin with five issuers as extraction fixtures. They do not establish membership
  of the historical investment universe or provide performance evidence.

## 2026-10-09 - Implementation choices

- Python package with uv dependency lock; lxml for conservative extraction, Parquet
  and DuckDB for local tables, scikit-learn for baselines, XNYS exchange calendar.
- Cache SEC response bytes and provenance; do not retry forbidden responses.
- Keep partial extraction failures visible. No silent pairing past a failed prior
  year and no return gap imputation.
- Build and test label arithmetic against invented examples while account/data
  entitlements remain unverified. The 144-row demo is synthetic throughout.
- No remote repository was supplied. This milestone is a local git project plus a
  portable source package; publishing to a GitHub repository is a later connection.

Implementation was co-developed with Codex. Human audit and independent explanation
of the study remain pending. No financial predictive finding is claimed.

## 2026-10-09 - Live-source and edge-case review

- The live sample contains disagreements between API timestamps and SGML headers.
  Preserve both, use the explicit header interpretation for timing, and record the
  difference for manual review. All 20 smoke filings supplied header evidence.
- A zero TF-IDF vector has undefined cosine, not a distance of one. Keep this value
  missing and use only the model's training-fitted imputation; expose its count.
- Remove stale generated tables after an empty ingestion result. A prior successful
  output must not appear to belong to a new failed run.
