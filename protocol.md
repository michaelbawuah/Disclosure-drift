# Disclosure changes and return forecasting: protocol v1.0.0

Locked 9 October 2026 before any return-model comparisons. This is a new investigation
inspired by Cohen, Malloy and Nguyen's *Lazy Prices*, not a direct replication.
The machine-readable primary rules are in `configs/protocol.json`; the lock contains
its SHA-256. Amendments require a dated decision and a new version; original results
must remain available.

## Question and target

Does adding three annual Risk Factors text-change features improve 20-session
market-adjusted return forecasts for a historically selected large, liquid U.S.
common-stock universe during 2022-2025?

Use original 10-Ks only, excluding 10-K/A. Pair by CIK with the immediately preceding
original annual report. Require distinct consecutive report periods; flag changes
of year-end, missing sections, ambiguities and transition periods for review.
Do not impute absent risk sections as empty disclosures. No cross-issuer pairing.

The reference session is the second XNYS session strictly after the SEC acceptance
date in America/New_York. Forecast before its open with controls through the
preceding session close. Acceptance is not proof of public dissemination; preserve
the source header, raw API timestamp and availability evidence/assumption. Exclude
known violations and report unverified timing. Primary delays remain fixed.

The label is compounded stock total return from the reference close through the
close 20 sessions later, minus compounded value-weighted market return over exactly
the same sessions. Thus the reference day's close-to-close return is excluded.
Include dividends and delisting once. After a terminal event, carry proceeds as
zero-return cash through the remaining horizon. Missing delisting returns or
unexplained price gaps are errors, not zero returns. The normalized market input
must explicitly document whether delisting is already included (e.g., a modern
combined return field) or was combined from legacy fields.

## Universe

At each year-start, use historical listings and prior 60-session mean dollar volume,
requiring at least 40 valid observations, to select up to 500 U.S. common-stock
issuers. Resolve CIK/security mappings with dated link intervals. For multiple
eligible classes choose the most liquid, and count the issuer once. Retain later
delistings. The five-company smoke fixture is a parser check, not this universe.

## Development, tuning and primary evaluation

- Initial training: 2010-2015.
- Development: expanding annual folds 2016-2021. The labeled 2019-2021 pilot belongs here.
- Untouched primary evaluation: 2022-2025.
- Use acceptance year to assign filing events to years. Collect prices through each
  label end, including 2026 for late-2025 events.
- Before each evaluation year's first prediction, refit on prior events with labels
  fully matured before that prediction. Automatically including prior test-year
  labels in subsequent annual refits is allowed under the frozen algorithm. Human
  tuning after opening the test is not allowed.
- Fit vocabulary, missing-value imputation, scaling and industry encoding only on
  each fold's eligible training observations. No full-year ranks or target ranks.
- Controls: previous 20/60-session compounded momentum, 20-session standard deviation
  of daily returns (sample standard deviation, unannualized), log positive market cap,
  and historical industry category; all known by the preceding close.
- Text: log(1 + token count) change, token-set Jaccard distance, TF-IDF cosine distance.
  Lowercase alphabetic tokens of at least two letters, unigrams, no stop-word removal,
  maximum 20,000 TF-IDF terms selected in training; min_df=1. Empty texts are excluded.
- The primary augmented model uses all three text features. Tune ridge penalties
  separately for baseline and augmented model on the same four-value grid using
  pooled development MSE. Eight model/grid configurations in total; six annual folds.
- Freeze selected penalties, code commit, preprocessing, observations/exclusions and
  manifests before opening final scores. Text-feature ablations are secondary.
- Primary score: 1 - SSE(controls + text) / SSE(controls), on identical observations.
  Jointly resample consecutive reference-month blocks with all firms retained;
  2,000 bootstrap draws, seed 20261009, three-month blocks and a six-month sensitivity.
  Recompute the SSE ratio each draw. Four years provide limited independent time
  information; the interval is approximate and conditional on this fitted procedure.

The final evaluator is intentionally gated until market data, extraction audits,
development selection and the secondary specification are complete. A config hash
is an audit aid, not an access-control guarantee. No actual return data or holdout
results have been inspected in this build milestone.

## Secondary analyses decided before test access

1. Year-by-year scores, monthly rank correlation, text-feature ablations and reference
   delays of 1 and 5 sessions, compared with the primary 2-session delay. Preserve
   public-availability constraints for every delay.
2. Added versus removed paragraphs: manually distinguish additions, deletions,
   rewording and relocation. This remains a descriptive audit until the matching
   rule, thresholds and forecast feature construction are frozen.
3. Semantic-distance comparison: preregister checkpoint/hash, release date, training
   and fine-tuning cutoff evidence, chunking/aggregation, development tuning and
   model comparison before the holdout opens. Validate unchanged/reworded/new-risk
   examples manually. If chronology cannot be established, label the analysis
   retrospective or validate prospectively. Never silently truncate long sections.
4. Inspect the 2020 disclosure-rule transition; prespecify any exclusion sensitivity
   on development evidence, accounting for headings and risk summaries.
5. A 2026 validation cohort and any thematic or trading analysis require separate
   frozen protocols. These are not additional ways to choose the primary result.

## Interpretation and completion

A null under this specification does not prove universal signal decay or that
publication caused decay. Report effect sizes and intervals; wide intervals may
be inconclusive. Predictive performance is not a trading-profit claim.

Complete the study when provenance, timing, links, labels and extraction have been
audited; development and holdout tables are distinct; all declared results and
failures are reported; and another person can rebuild permitted public examples.
Fix all identified extraction errors. A 27/30 pilot boundary check is a debugging
gate, not a final accuracy certificate. Publish code and permitted examples while
keeping restricted market data local.

## Sources

- Cohen, Malloy, Nguyen, *Lazy Prices*, Journal of Finance 75(3), 2020: https://doi.org/10.1111/jofi.12885
- SEC API: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- SEC access: https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
- SEC 2020 disclosure amendments: https://www.sec.gov/newsroom/press-releases/2020-192
- Chronologically Consistent Large Language Models: https://arxiv.org/abs/2502.21206
- Cornell WRDS access: https://johnson.library.cornell.edu/database/wharton-research-data-services-wrds/
