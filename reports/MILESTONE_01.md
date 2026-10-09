# Milestone 01: working research foundation

Completed 9 October 2026. The primary protocol is locked as version 1.0.0 and tagged
in the local git history. The project is executable with `uv sync --locked`.

## Implemented and verified

- Official SEC submission-history and document ingestion, including older history pages.
- Polite requests, bounded retry/backoff, immutable cached response bytes and hashes.
- Item 1A section extraction, table-of-contents handling, hidden-text removal and
  explicitly flagged ambiguous/missing sections.
- Consecutive original annual filing pairs, without skipping over failed prior reports.
- XNYS holiday/session timing, source-header acceptance evidence and raw API values.
- Training-only TF-IDF, Jaccard distance and log-length change. Undefined cosine
  values remain missing for training-fitted imputation.
- Historical-link ambiguity checks and exact 20-session normalized-return labels,
  with dividends/delisting handled upstream and proceeds carried in cash afterward.
- Six chronological development folds, two ridge models, a four-penalty grid, and
  paired moving-month-block uncertainty calculations.
- A fully synthetic end-to-end demo, local test suite and a GitHub Actions workflow.

## Live source check

20 original filings (2018-2021) were downloaded for five companies. All 20 produced
substantive bounded sections under the automatic parser, resulting in 15 annual
2019-2021 pairs. All 20 provided original SGML acceptance headers. The cached rerun
made zero network requests and reproduced identical tables.

The source API and SGML header timestamps disagree for some filings. Both are
retained and the difference is flagged; manual timing review remains necessary.
See `sec_smoke_manifest.csv` and `milestone_01.json` for exact evidence.

The text-feature smoke check fits vocabulary on 2019-2020 pairs, then transforms
the five 2021 pairs. It uses no return labels. `text_feature_smoke.csv` contains
those descriptive values; they are not a forecast result.

## Verification

36 tests passed, with no failures or errors. Ruff passed. The environment emits
four upstream exchange-calendar/NumPy deprecation warnings; the tested dependency
versions are locked. Local checks passed; remote GitHub CI has not been run because
no remote repository has been connected.

## Remaining gates

1. Human audit of document boundaries, source timestamps and annual pairs.
2. Verify Cornell WRDS access and the precise export schema, including historical
   identifiers, inactive stocks and delisting conventions.
3. Build the point-in-time full-universe selector and verified market/control join
   against that actual data schema; expand to 100-150 pilot pairs.
4. Run real development experiments and freeze selected penalties.
5. Specify and audit the semantic checkpoint, paragraph matching and chronology.
6. Open the primary final test only after those gates are complete.

No actual market-return data has been loaded. No 2022-2025 predictive score exists.
The synthetic demo is a software fixture only. This milestone does not constitute
completion of the empirical study or the required human research review.
