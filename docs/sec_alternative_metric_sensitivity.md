# SEC-only disclosure-drift metric sensitivity

**12 October 2026 — exploratory, source-audited, non-predictive follow-up.**

This extends the [separate SEC-only descriptive study](sec_only_descriptive_study.md),
not the frozen equity-return forecasting protocol. The baseline comprises
**215 original source-audited SEC 10-K filings from 35 purposely sampled issuers**,
yielding **180 consecutive year-on-year Item 1A Risk Factors comparisons**
accepted in 2015–2021. Only **34 issuers** have every 2019, 2020 and 2021
annual comparison; they form the fixed balanced panel. Original source
feature and SEC filing manifests were checked by SHA and source-to-prior-year
links. No CRSP, WRDS, market returns or holdout data were loaded.

## Three distinct descriptive measures

- **Jaccard token-set distance**: lexical vocabulary turnover between
  adjacent-year original Item 1A disclosures, ignoring repeated term frequency.
- **Log document-length change**:
  `log(1 + current_token_count) - log(1 + previous_token_count)`.
  This describes the relative annual change in extracted Risk Factors length,
  not necessarily new vocabulary.
- **TF-IDF cosine distance**: the original pipeline's frequency-weighted
  lexical distance. **Its training vocabulary grows using earlier acceptance
  years, so comparisons across years do not use a fixed feature space**.
  This is directional sensitivity, not a controlled fixed-vocabulary replication
  or a claim of semantic change.

Each within-issuer 2019→2021 contrast compares that issuer's 2021
year-over-year change (relative to 2020) against its 2019 year-over-year
change (relative to 2018). The 34 issuers and original text features remain
unchanged. These metrics were assessed **after seeing the earlier
exploratory Jaccard result**, not under a preregistered confirmatory plan.

| Metric, balanced 34 issuers | Mean 2019→2021 paired difference | Positive / negative issuers | Conditional issuer-bootstrap 95% interval |
| --- | ---: | ---: | ---: |
| Jaccard distance | **+0.04602** | **27 / 7** | **+0.02371 to +0.07236** |
| TF-IDF cosine distance (changing historical vocabulary) | **+0.00569** | **29 / 5** | **+0.00353 to +0.00828** |
| Log annual extracted-text length change | **+0.04348** | **24 / 10** | **−0.02703 to +0.10060** |

The conditional interval is produced by **5,000 bootstrap resamplings of
the 34 fixed observed issuers**, not by resampling the U.S. corporate
population or the years. It is **not a population confidence interval** and
does not supply causal or preregistered significance. For additional
source-sample sensitivity, the audit also recomputes 10%-trimmed paired
means and all 34 leave-one-issuer-out means.

The *rank association* between 2019→2021 Jaccard changes and TF-IDF changes
is approximately **0.713** (Spearman), compared with approximately **0.345**
for the Jaccard-vs-length-change association. Rank inputs are rounded to
12 decimal places **solely for tie handling** to prevent meaningless
floating-point subtraction noise. When all source changes have exactly the
same rank, the correlation is reported **undefined**, not fabricated as zero
or high correlation.

**Interpretation:** Jaccard and TF-IDF exhibit consistent *directional*
increases for many of these issuers. Annual text-length changes are
more heterogeneous, and the conditional length interval includes zero.
A changed year-specific TF-IDF vocabulary prevents interpreting that
metric as fixed-lexicon confirmation of any historical event effect.
No result shows that disclosures forecast returns.

## Source and independent verification

The [source-bound sensitivity implementation](../src/disclosure_research/sec_only_metric_sensitivity.py)
validates the earlier [SEC-only original-source checkpoint](../reports/sec_only_descriptive_checkpoint.json),
reuses the identical 34 balanced issuer CIKs, computes all nine measure/
year-contrast combinations and preserves each of the 306 issuer-metric
changes privately. Source metadata verifies the year and issuer of each
original 10-K, fixed earlier-year-only TF-IDF vocabulary and lack of
market data or human review approvals.

A [separately written verifier](../src/disclosure_research/sec_metric_sensitivity_verifier.py)
independently reparses the original SEC feature CSV with Python `csv`/
`Decimal` rather than the primary Pandas joins. It reconstructs all
**306** individual deltas, their signs, nine mean/median/trimmed/leave-one-out
comparisons, fixed-seed issuer-bootstrap intervals, original source-token
length arithmetic, and manually computed average-tie Spearman ranks.
The verifier refuses revised source bytes, forged significance/source
approval, future-year leakage, changing previous baselines or fabricated
per-issuer/metric results.

The [public aggregate data](../reports/sec_metric_sensitivity_checkpoint.json)
and [independent source check](../reports/sec_metric_sensitivity_independent.json)
contain no individual licensed market-security rows. The exact original
per-issuer feature changes, audit receipts and source notes stay
private under ignored `outputs/sec-metric-sensitivity-20261012-v2/`.
The source-only input files and balanced panel have been deliberately
held unchanged; no model-ready or sealed-final assertions were created.

## Reproduce offline

```bash
uv run --locked --python 3.12 python scripts/audit_sec_metric_sensitivity.py \
  --sources reports/pilot_expansion \
  --baseline outputs/sec-only-descriptives-20261012-v2 \
  --output outputs/sec-metric-sensitivity-NEW
```

```bash
uv run --locked --python 3.12 python scripts/verify_sec_metric_sensitivity.py \
  --sources reports/pilot_expansion \
  --baseline outputs/sec-only-descriptives-20261012-v2 \
  --sensitivity outputs/sec-metric-sensitivity-NEW \
  --output reports/independent-metric-sensitivity-NEW.json
```

No network requests or WRDS account are required.
The [original forecasting research completion gates](research_completion_gates.md)
and actual 2022–2025 final evaluation remain untouched.

## Final repeat-run result

The [final source-sensitivity reproducibility report](../reports/sec_sensitivity_reproduction.json)
binds **1,245 passing tests**, Ruff, and the complete synthetic
study software pipeline. Two fresh executions of the original
alternative-metric audit produced **byte-identical public summaries
and private 306 issuer-level metric changes**, and two independent
source verifications produced **byte-identical aggregate verification
reports**. Rank tie handling was tested against numerically identical
synthetic differences to prevent spurious correlations. The actual
real-source ranks and reported correlations were unchanged.

The accompanying source-diagnostic recheck also reread all 16 locally
preserved current SEC HTMLs without additional network requests, and
a second verifier produced a **byte-identical** independent report.
The frozen forecasting protocol remains separated and closed.
