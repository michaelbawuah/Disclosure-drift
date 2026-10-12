# SEC-backed pilot without new WRDS access — conditional, NOT empirically approved

**11 October 2026 checkpoint.** This independent *exploratory development* route
runs on earlier manually preserved SEC disclosure features and provisional
CRSP arithmetic. It does **not** require a new WRDS query, an individual WRDS
account, or browser automation to reproduce. There is no claim of historical
issuer identity approval, forecast improvement, full-universe coverage, completed
filing review, or opened 2022–2025 evaluation.

## What is genuinely available today

The earlier fixed **20-issuer SEC parser sample** contains **135 year-over-year
Item 1A filing comparisons** from acceptance years 2015–2021. The saved
provisional market arithmetic contains 135 source-bound calculations. The
original SEC IDs and ten-digit issuer CIKs match **one-to-one** for all 135
pairs. The original purpose of this sample was parser validation, not a
historically selected large/liquid US-stock universe. The source audit still
marks all 135 company-security links *unapproved*, all open link ends
*unresolved*, and the filing sample *not human reviewed*. Seven company-header
CIKs differ in the arithmetic packet; they remain evidence problems to review,
not automatic exclusions.

Our independently reviewed **20/20 arithmetic** checks remain complete, but
that does not repair the separate issuer, source-release, available-at, and
full-filing audit gates. The approved future reference convention is still the
frozen second XNYS session after SEC acceptance. Filing acceptance and source
availability are not interchangeable. Preserve all prior evidence and review
statuses.

## Conditional expanding-year pilot

Implemented in [`exploratory_sec_pilot.py`](../src/disclosure_research/exploratory_sec_pilot.py)
with [this read-only source wrapper](../scripts/run_exploratory_sec_pilot.py).
This **does not invoke the frozen primary study**. It is a documented
feasibility check with the following distinct choices:

| Element | Observed / conditional choice |
| --- | --- |
| Sources | Saved `market-pilot-m5-v1/candidate_calculations.parquet` and SEC `pilot_checkpoint/text_features.csv`, each verified against its preserved receipt SHA-256 |
| Warmup | 2015 original filing comparisons, 19 unapproved candidate events |
| Test years | 2016–2021, 19 + 19 + 19 + 19 + 20 + 20 = **116** event predictions for each candidate model |
| Timing | For each test year, training uses earlier acceptance years **only**; every training label ends *before the earliest test-year reference session* |
| Controls | 20/60-session momentum, 20-session volatility, log capitalization, candidate dated SIC industry |
| Text | Log-length change, Jaccard distance, TF-IDF cosine distance. Saved TF-IDF vocabulary metadata requires strictly earlier acceptance years; 2015 lacks TF-IDF and receives model-fold-only imputation |
| Models | Ridge controls-only and ridge controls + three text features, both **fixed alpha 10.0** from the existing grid; identical training/testing events |
| Model preparation | Numeric imputation and scaling fit on each training fold only; unknown industries handled by the existing one-hot pipeline |
| Diagnostic | Paired candidate MSE and conditional SSE ratio, with 2,000 issuer-cluster bootstrap draws using the frozen reproducibility seed |
| Source boundary | Does **not** load any 2022–2025 filing or target returns; late-2021 development label tail may extend to **2022-02-02** |
| Publication | Full provisional predictions and numeric comparison stay **private, ignored by Git**. Public receipt reports counts and limitations only. |

The fixed model comparison produced valid *software outputs* and private
conditional metrics. Its initial result did **not** show lower error with text.
It is **not a statistically validated or population-representative finding**.
The fixed alpha is not a hyperparameter selection and must not be adjusted to
chase a positive conditional outcome. Those choices differ from the locked
2010–2021 primary development grid search. The original primary question and
final period are unchanged.

From the checked out repository root, reproduce with a **fresh output path**:

```bash
uv run --locked --python 3.12 python scripts/run_exploratory_sec_pilot.py \
  --market-candidates data/reviews/market-pilot-m5-v1 \
  --text-features reports/pilot_checkpoint \
  --output outputs/sec-exploratory-recheck-NEW-NAME
```

`candidate_predictions_private.csv`, `conditional_metrics_private.json`,
`public_summary.json`, and `receipt.json` are private and hash-bound.
A source-hash mismatch, missing or duplicate SEC ID, CIK/year disagreement,
future filing year, erroneous target arithmetic, future-dated control, rehashed
feature-date anomaly, non-earlier-year vocabulary count or unexpected approved
input is rejected rather than repaired.

This experiment cannot be cited as evidence that disclosure drift improves
forecasts. Source and human review remain mandatory, even when numerical
outputs are finite and reproducible.

A second, separate execution into fresh private directories produced
**byte-identical** exported candidate predictions, conditional-metrics JSON,
SEC pilot public summary and public-market comparison summary. Its
[aggregate reproducibility record](../reports/alternative_pilot_reproduction.json)
also binds the passing Ruff / **1,054-test** full software reproduction.
Matching bytes establish deterministic processing of the same preserved inputs,
**not** source vintage accuracy, mapping approval or empirical significance.

## Independent public-market sensitivity source

The [Kenneth French Data Library](https://mba.tuck.dartmouth.edu/pages/Faculty/ken.french/data_library.html)
publishes the daily Fama–French `Mkt-RF` and `RF` factors; both are **daily
percentage-point values**, so their sum divided by 100 gives a daily market
return in decimals. The downloaded 2026 CSV preamble says it used the **202608
CRSP database**. That public historical series is updated retrospectively; it
is *not* evidence of what a researcher could have known in the original year.

A separate strict offline check lives in
[`public_benchmark_check.py`](../src/disclosure_research/public_benchmark_check.py),
with [the standalone CLI](../scripts/compare_public_market.py). We preserved
the public ZIP locally, verified the original CRSP market CSV against its
source inventory receipt, compared dates and exact decimal values, and stopped
before reading numeric factor values later than the permitted development tail.

The first source-bound check found **3,103 of 3,103** CRSP development sessions
covered by the public series, but only **four exactly matching daily values**.
The median absolute daily difference was **0.000436**, or **4.36 basis points**;
the maximum was **0.005826**, or **58.26 basis points**. These differences are
between **different underlying market definitions and potentially different
revisions**. No conversion or tolerance can turn them into equal series.

Original real-data run:

```bash
uv run --locked --python 3.12 python scripts/compare_public_market.py \
  --public-zip outputs/public-benchmark-alternative-20261011/fama_french_daily_original.zip \
  --market-csv data/private/wrds-intake/market-v1/source.csv \
  --market-receipt data/private/wrds-intake/market-v1/receipt.json \
  --output outputs/ff-recheck-NEW-NAME
```

The comparator performs **coverage and source-definition diagnostics only**.
It does not change the primary CRSP benchmark, replace any individual-stock
return, infer a data release time, normalize source timestamps, create model
labels, or establish forecast performance. The preserved primary CRSP view's
52 within-vendor discrepancies remain separately unresolved.

## Research gates still pending

Before a standalone empirical conclusion, independently validate historical
CIK/PERMNO/class links and their period validity; historical availability of
listing, liquidity and mapping facts; source release and return conventions;
full original SEC filing boundaries and acceptance; issuer population and
selection/exclusion coverage; and a written human audit. The published
[completion gates](research_completion_gates.md) remain in force. A rigorously
reviewed, smaller-scope pilot could be reported with its own restricted estimand
and limits. **This code execution alone does not create that approval.**

For applications, it is accurate to describe the implemented financial
research, audited arithmetic, 20-issuer SEC sample, training-time safeguards,
automated reproducibility and independent source comparisons. It is inaccurate
to claim predictive uplift, peer-reviewed discovery, production market
signals, or completion of the originally frozen 2022–2025 final test.
